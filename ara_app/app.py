"""
Σarize Ara Agent
Triggered by the Σarize backend after a lecture is processed.
Does three things in parallel:
  1. Organizes all output files into ~/Desktop/Ara/<Subject>/<Topic>/
  2. Sends a summary email to the student
  3. Schedules a 7-day review reminder email
"""

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from ara_sdk import App, fastapi_endpoint, Secret

app = App("sumarize-agent")


# ── Tools ──────────────────────────────────────────────────────────────────

@app.tool()
def organize_files(subject: str, topic: str, run_id: str) -> dict:
    """
    Copy all generated files from the tmp run directory into
    ~/Desktop/Ara/<subject>/<topic>/ with clean names.
    """
    src_dir = Path(f"/tmp/vlm_summ/{run_id}")
    if not src_dir.exists():
        return {"ok": False, "reason": f"Run directory not found: {src_dir}"}

    # Sanitize folder names
    safe_subject = "".join(c if c.isalnum() or c in " _-" else "_" for c in subject).strip()
    safe_topic   = "".join(c if c.isalnum() or c in " _-" else "_" for c in topic).strip()

    dest_dir = Path.home() / "Desktop" / "Ara" / safe_subject / safe_topic
    dest_dir.mkdir(parents=True, exist_ok=True)

    file_map = {
        "summary_slides.pdf":     "Slides.pdf",
        "summary_slides.pptx":    "Slides.pptx",
        "transcript.txt":         "Transcript.txt",
        "summary_video.mp4":      "Summary_Video.mp4",
        "summary_narration.mp3":  "Narration_Audio.mp3",
        "storyboard.json":        "Storyboard.json",
    }

    copied = []
    for src_name, dest_name in file_map.items():
        src = src_dir / src_name
        if src.exists():
            shutil.copy2(src, dest_dir / dest_name)
            copied.append(dest_name)

    # Copy clips into a Clips/ subfolder
    clips_dir = dest_dir / "Clips"
    clips_dir.mkdir(exist_ok=True)
    for clip in src_dir.glob("clip_*.mp4"):
        shutil.copy2(clip, clips_dir / clip.name)
        copied.append(f"Clips/{clip.name}")

    return {
        "ok": True,
        "destination": str(dest_dir),
        "files_copied": copied,
    }


@app.tool()
def send_summary_email(
    to_email: str,
    subject: str,
    topic: str,
    summary: str,
    key_points: list,
    dest_folder: str,
    review_date: str,
) -> dict:
    """
    Send a summary email to the student with the executive summary,
    key points, file location, and a note about the 7-day review reminder.
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        return {"ok": False, "reason": "SMTP credentials not configured"}

    points_html = "".join(f"<li>{p}</li>" for p in key_points)

    body = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:auto;color:#222">
      <h2 style="color:#0099ff">Lecture Summary: {topic}</h2>
      <p><strong>Subject:</strong> {subject}</p>

      <h3>Executive Summary</h3>
      <p>{summary}</p>

      <h3>Key Points</h3>
      <ul>{points_html}</ul>

      <h3>Your Files</h3>
      <p>All files have been organized at:<br>
      <code style="background:#f4f4f4;padding:4px 8px;border-radius:4px">{dest_folder}</code></p>

      <hr style="margin:24px 0">
      <p style="color:#888;font-size:13px">
        You have a 7-day review reminder scheduled for <strong>{review_date}</strong>.
        You'll receive an email asking if you'd like to revisit this lecture.
      </p>
      <p style="color:#888;font-size:13px">Organized by Σarize + Ara</p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Σarize] {topic} — Lecture Summary & Files Ready"
    msg["From"]    = smtp_user
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_email, msg.as_string())

    return {"ok": True, "sent_to": to_email}


@app.tool()
def schedule_review_email(
    to_email: str,
    subject: str,
    topic: str,
    review_date: str,
) -> dict:
    """
    Schedule a 7-day review reminder email asking the student
    if they'd like to revisit the lecture.
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")

    if not smtp_user or not smtp_pass:
        return {"ok": False, "reason": "SMTP credentials not configured"}

    body = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:auto;color:#222">
      <h2 style="color:#0099ff">Time to review: {topic}</h2>
      <p>It's been 7 days since you studied <strong>{topic}</strong> ({subject}).</p>
      <p>Research shows revisiting material after 7 days significantly improves long-term retention.</p>

      <p>Would you like to revisit this lecture?</p>
      <p>Your files are still saved and ready to review.</p>

      <hr style="margin:24px 0">
      <p style="color:#888;font-size:13px">Sent by Σarize + Ara</p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Σarize] 7-day review: {topic} — ready to revisit?"
    msg["From"]    = smtp_user
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "html"))

    # This tool is called by the scheduler 7 days later
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_email, msg.as_string())

    return {"ok": True, "review_email_sent_to": to_email}


# ── Coordinator Tool (no LLM needed — pure Python execution) ──────────────

@app.tool()
@fastapi_endpoint(method="POST", path="/organize", auth="header")
def coordinator(input: dict) -> dict:
    """
    Organizes lecture files, sends summary email, and schedules 7-day review.
    Called directly by the Σarize backend — no LLM reasoning needed.
    """
    from concurrent.futures import ThreadPoolExecutor
    payload    = input.get("input", input)
    subject    = payload.get("subject", "General")
    topic      = payload.get("topic", "Lecture")
    email      = payload.get("email", "")
    summary    = payload.get("summary", "")
    key_points = payload.get("key_points", [])
    run_id     = payload.get("run_id", "")
    action     = payload.get("action", "")

    # 7-day review trigger — called by scheduler
    if action == "send_review_email":
        review_date = datetime.now().strftime("%A, %B %d %Y")
        return schedule_review_email(
            to_email=email, subject=subject, topic=topic, review_date=review_date
        )

    review_date = (datetime.now() + timedelta(days=7)).strftime("%A, %B %d %Y")
    review_iso  = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%dT09:00:00")

    # Step 1: organize files
    org_result = organize_files(subject=subject, topic=topic, run_id=run_id)
    dest_folder = org_result.get("destination", "~/Desktop/Ara")

    # Steps 2 & 3 in parallel: send email + register 7-day scheduler
    def _send_email():
        return send_summary_email(
            to_email=email, subject=subject, topic=topic,
            summary=summary, key_points=key_points,
            dest_folder=dest_folder, review_date=review_date,
        )

    def _schedule_review():
        # Use Ara's automation_create to fire this tool again in 7 days
        import httpx, os
        ara_app_id   = "app_b088d7594745435e9bd4f6c49428bad1"
        runtime_key  = os.getenv("ARA_RUNTIME_KEY", "")
        if not runtime_key:
            return {"ok": False, "reason": "no runtime key"}
        payload = {
            "automation": {
                "agent_id": "coordinator",
                "at": review_iso,
                "input": {
                    "subject": subject, "topic": topic,
                    "email": email, "action": "send_review_email",
                },
            }
        }
        resp = httpx.post(
            f"https://api.ara.so/v1/apps/{ara_app_id}/automations",
            json=payload,
            headers={"Authorization": f"Bearer {runtime_key}"},
            timeout=10,
        )
        return resp.json()

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_email    = ex.submit(_send_email)
        f_schedule = ex.submit(_schedule_review)
        email_result    = f_email.result()
        schedule_result = f_schedule.result()

    return {
        "ok": True,
        "files": org_result,
        "email": email_result,
        "review_scheduled": schedule_result,
        "review_date": review_date,
    }
