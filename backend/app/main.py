import os
import uuid
import shutil
from fastapi import FastAPI, UploadFile, Form, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from . import video_pipeline_v2 as video_pipeline

load_dotenv()

app = FastAPI(title="VLM Video ShortSage")

origins = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

class ProcessRequest(BaseModel):
    youtube_url: str | None = None

@app.post("/api/process")
async def api_process(
    youtube_url: str | None = Form(None),
    file: UploadFile | None = File(None),
    voice_style: str | None = Form("friendly"),
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
        
        # Add download URLs
        for clip in output.get("generated_clips", []):
            clip["download_url"] = f"http://localhost:8000/api/download/{run_id}/{os.path.basename(clip['path'])}"
        
        # Also add to publication_ready
        for i, clip in enumerate(output.get("publication_ready", {}).get("short_form_content", [])):
            if i < len(output["generated_clips"]):
                clip["download_url"] = output["generated_clips"][i]["download_url"]

        # Add narrated 10-min video, audio and storyboard download URLs
        base = f"http://localhost:8000/api/download/{run_id}"
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
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    finally:
        # for brevity in hackathon we keep artifacts; optionally delete old dirs periodically.
        pass

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
