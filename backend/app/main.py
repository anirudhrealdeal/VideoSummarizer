import os
import uuid
import shutil
from fastapi import FastAPI, UploadFile, Form, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from . import video_pipeline_v2 as video_pipeline

load_dotenv(override=True)

# Persistent scheduler backed by SQLite so jobs survive restarts
_jobstore_path = os.getenv("SCHEDULER_DB_PATH", os.path.join(os.path.expanduser("~"), ".vlm_scheduler.db"))
_scheduler = BackgroundScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{_jobstore_path}")},
    job_defaults={"misfire_grace_time": 3 * 24 * 3600},  # fire up to 3 days late if server was down
)
_scheduler.start()

app = FastAPI(title="VLM Video ShortSage")


def _send_review_email(to_email: str, subj: str, top: str, rev_date: str):
    """Module-level so APScheduler can pickle it."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        return
    body = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:auto;color:#222">
      <h2 style="color:#0099ff">Time to review: {top}</h2>
      <p>It's been 7 days since you studied <strong>{top}</strong> ({subj}).</p>
      <p>Research shows revisiting material after 7 days significantly improves long-term retention.</p>
      <p>Your files are still saved and ready to review.</p>
      <hr style="margin:24px 0">
      <p style="color:#888;font-size:13px">Sent by Σarize</p>
    </body></html>"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Σarize] 7-day review: {top} — ready to revisit?"
    msg["From"]    = smtp_user
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "html"))
    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
        srv.starttls()
        srv.login(smtp_user, smtp_pass)
        srv.sendmail(smtp_user, to_email, msg.as_string())

_extra_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
origins = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174", "http://localhost:3000", "http://127.0.0.1:3000"] + _extra_origins
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

class ProcessRequest(BaseModel):
    youtube_url: str | None = None

@app.post("/api/process")
async def api_process(
    youtube_url: str | None = Form(None),
    file: UploadFile | None = File(None),
    voice_style: str | None = Form("friendly"),
    subject: str | None = Form(None),
):
    # Need either youtube_url or file
    if not youtube_url and not file:
        raise HTTPException(status_code=400, detail="youtube_url or file upload required")

    run_id = str(uuid.uuid4())
    working_dir = os.path.join("/tmp", "vlm_summ", run_id)
    os.makedirs(working_dir, exist_ok=True)

    try:
        if youtube_url:
            input_source = video_pipeline.download_youtube(youtube_url, working_dir)
        else:
            local_path = os.path.join(working_dir, file.filename)
            with open(local_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            input_source = local_path

        output = video_pipeline.process(input_source, working_dir, voice_style=voice_style or "friendly")
        output["voice_style"] = voice_style or "friendly"
        output["run_id"] = run_id
        output["subject"] = subject or ""
        
        # Add download URLs
        _api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
        for clip in output.get("generated_clips", []):
            clip["download_url"] = f"{_api_base}/api/download/{run_id}/{os.path.basename(clip['path'])}"

        # Also add to publication_ready
        for i, clip in enumerate(output.get("publication_ready", {}).get("short_form_content", [])):
            if i < len(output["generated_clips"]):
                clip["download_url"] = output["generated_clips"][i]["download_url"]

        # Add narrated 10-min video, audio and storyboard download URLs
        base = f"{_api_base}/api/download/{run_id}"
        for key, field in [
            ("summary_video_url",      "summary_video_path"),
            ("summary_narration_url",  "summary_narration_audio"),
            ("highlight_reel_url",     "highlight_reel_path"),
            ("slides_url",             "slides_path"),
            ("pdf_url",                "pdf_path"),
            ("transcript_txt_url",     "transcript_txt_path"),
            ("storyboard_url",         "storyboard_path"),
        ]:
            if output.get(field):
                output[key] = f"{base}/{os.path.basename(output[field])}"

        return output

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    finally:
        # for brevity in hackathon we keep artifacts; optionally delete old dirs periodically.
        pass

@app.post("/api/organize")
async def api_organize(payload: dict):
    """Organize files, send summary email, schedule 7-day review."""
    import smtplib, shutil
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from datetime import datetime, timedelta
    from pathlib import Path

    subject    = payload.get("subject", "General")
    topic      = payload.get("topic", "Lecture")
    email      = payload.get("email", "")
    summary    = payload.get("summary", "")
    key_points = payload.get("key_points", [])
    run_id     = payload.get("run_id", "")

    _review_delta = timedelta(minutes=10)  # demo: 10 min; change to days=7 for production
    review_date = (datetime.now() + _review_delta).strftime("%A, %B %d %Y at %I:%M %p")
    review_iso  = (datetime.now() + _review_delta).strftime("%Y-%m-%dT%H:%M:%S")

    # ── 1. Organize files ──────────────────────────────────────────────────
    src_dir = Path(f"/tmp/vlm_summ/{run_id}")
    safe = lambda s: "".join(c if c.isalnum() or c in " _-" else "_" for c in s).strip()
    dest_dir = Path.home() / "Desktop" / "Ara" / safe(subject) / safe(topic)
    dest_dir.mkdir(parents=True, exist_ok=True)

    file_map = {
        "summary_slides.pdf": "Slides.pdf", "summary_slides.pptx": "Slides.pptx",
        "transcript.txt": "Transcript.txt", "summary_video.mp4": "Summary_Video.mp4",
        "summary_narration.mp3": "Narration_Audio.mp3",
    }
    copied = []
    if src_dir.exists():
        for src_name, dest_name in file_map.items():
            src = src_dir / src_name
            if src.exists():
                shutil.copy2(src, dest_dir / dest_name)
                copied.append(dest_name)
        clips_dir = dest_dir / "Clips"
        clips_dir.mkdir(exist_ok=True)
        for clip in src_dir.glob("clip_*.mp4"):
            shutil.copy2(clip, clips_dir / clip.name)
            copied.append(f"Clips/{clip.name}")

    # ── 2. Send summary email ──────────────────────────────────────────────
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    email_sent = False

    if smtp_user and smtp_pass and email:
        points_html = "".join(f"<li>{p}</li>" for p in key_points)
        body_html = f"""
        <html><body style="font-family:sans-serif;max-width:600px;margin:auto;color:#222">
          <h2 style="color:#0099ff">Lecture Summary: {topic}</h2>
          <p><strong>Subject:</strong> {subject}</p>
          <h3>Executive Summary</h3><p>{summary}</p>
          <h3>Key Points</h3><ul>{points_html}</ul>
          <h3>Your Files</h3>
          <p>Saved to: <code style="background:#f4f4f4;padding:4px 8px;border-radius:4px">{dest_dir}</code></p>
          <hr style="margin:24px 0">
          <p style="color:#888;font-size:13px">Review reminder scheduled for <strong>{review_date}</strong>.</p>
          <p style="color:#888;font-size:13px">Organized by Σarize + Ara</p>
        </body></html>"""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[Σarize] {topic} — Summary & Files Ready"
            msg["From"] = smtp_user
            msg["To"] = email
            msg.attach(MIMEText(body_html, "html"))
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, email, msg.as_string())
            email_sent = True
        except Exception as e:
            print(f"Email failed: {e}")

    # ── 3. Schedule 7-day review email via APScheduler ────────────────────
    review_scheduled = False
    if email and smtp_user and smtp_pass:
        try:
            from datetime import datetime as _dt
            run_date = _dt.now() + _review_delta
            _scheduler.add_job(
                _send_review_email,
                "date",
                run_date=run_date,
                args=[email, subject, topic, review_date],
                id=f"review_{run_id}",
                replace_existing=True,
            )
            review_scheduled = True
        except Exception as e:
            print(f"Scheduling failed: {e}")

    return {
        "status": "done",
        "files_organized": str(dest_dir),
        "files_copied": copied,
        "email_sent": email_sent,
        "review_scheduled": review_scheduled,
        "review_date": review_date,
    }


@app.get("/api/download/{run_id}/{filename}")
async def download_file(run_id: str, filename: str):
    file_path = os.path.join("/tmp", "vlm_summ", run_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    ext = os.path.splitext(filename)[1].lower()
    media_types = {
        ".mp4":  "video/mp4",
        ".mp3":  "audio/mpeg",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pdf":  "application/pdf",
        ".txt":  "text/plain; charset=utf-8",
        ".json": "application/json",
        ".srt":  "text/plain",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type, filename=filename)
