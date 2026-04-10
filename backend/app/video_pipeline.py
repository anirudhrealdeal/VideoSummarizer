import os
import subprocess
import tempfile
import base64
from pathlib import Path
from typing import List, Dict, Tuple

from openai import OpenAI


def _get_client():
    """Get OpenAI client, loading key from environment on demand."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is required in environment")
    return OpenAI(api_key=api_key)


def _run_cmd(cmd: List[str]):
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\nstderr: {completed.stderr}\nstdout: {completed.stdout}")
    return completed.stdout


def download_youtube(youtube_url: str, out_dir: str) -> str:
    out_template = os.path.join(out_dir, "video.%(ext)s")
    cmd = ["yt-dlp", "-f", "bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best", "-o", out_template, youtube_url]
    _run_cmd(cmd)

    files = list(Path(out_dir).glob("video.*"))
    if not files:
        raise FileNotFoundError("Downloaded video not found")
    return str(files[0])


def extract_audio(video_path: str, out_dir: str) -> str:
    audio_path = os.path.join(out_dir, "audio.wav")
    _run_cmd(["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", audio_path])
    return audio_path


def extract_keyframes(video_path: str, out_dir: str, scene_thresh: float = 0.22, max_frames: int = 8) -> List[str]:
    keyframes_dir = os.path.join(out_dir, "frames")
    os.makedirs(keyframes_dir, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"select='gt(scene,{scene_thresh})',scale=240:-1",
        "-q:v", "8",
        "-frames:v", str(max_frames),
        os.path.join(keyframes_dir, "frame_%03d.jpg"),
    ]
    _run_cmd(cmd)
    frames = sorted([str(p) for p in Path(keyframes_dir).glob("*.jpg")])

    if not frames:
        # fallback to evenly spaced frames in long videos
        duration = video_duration(video_path)
        step = max(10, int(duration / max_frames))
        for i in range(max_frames):
            ts = i * step
            frame_path = os.path.join(keyframes_dir, f"fallback_{i:03d}.jpg")
            _run_cmd(["ffmpeg", "-y", "-ss", str(ts), "-i", video_path, "-frames:v", "1", "-vf", "scale=240:-1", "-q:v", "8", frame_path])
            frames.append(frame_path)

    return frames


def video_duration(video_path: str) -> float:
    out = _run_cmd(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path])
    return float(out.strip())


def caption_frame(frame_path: str) -> str:
    client = _get_client()
    
    with open(frame_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe the visual content of this image in 1-2 sentences, focusing on people, text on slides, activity, and cues for summary reels."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ],
        max_tokens=120,
    )
    return response.choices[0].message.content.strip()


def speech_to_text(audio_path: str) -> str:
    client = _get_client()
    
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(file=f, model="whisper-1")
    return result.text


def chunk_transcript(transcript: str, chunk_size: int = 1200) -> List[str]:
    words = transcript.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i : i + chunk_size]))
    return chunks


def summarize_transcript(transcript_chunks: List[str], frame_captions: List[str]) -> Dict:
    client = _get_client()
    
    bullet_chunks = []
    for idx, chunk in enumerate(transcript_chunks):
        prompt = (
            "You are a concise educational summarizer. "
            "Given this transcript chunk, produce 3 bullet points that capture the key ideas and actionable insights.\n"
            f"Transcript chunk #{idx+1}:\n{chunk}\n"
        )
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=250)
        bullet_chunks.append(resp.choices[0].message.content)

    all_bullets = "\n".join(bullet_chunks)
    full_prompt = (
        "Combine the following information into a single structured summary. "
        "Include a 10-minute summary narrative, 6 clip ideas with timestamps placeholders, and a short text overlay script for each clip. "
        "Use the frame captions as visual reference points for clip hooks.\n\n"
        "Frame captions:\n" + "\n".join([f"- {c}" for c in frame_captions]) + "\n\n"
        "Transcript bullets:\n" + all_bullets
    )

    summary_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": full_prompt}], max_tokens=800)
    summary_text = summary_resp.choices[0].message.content

    return {
        "full_summary": summary_text,
        "clip_ideas": [
            {"title": f"Clip {i+1}", "note": "Extract around the key idea and add visual hook"}
            for i in range(6)
        ],
    }


def generate_clips(video_path: str, working_dir: str, clip_count: int = 6, clip_duration: int = 15) -> List[Dict]:
    duration = video_duration(video_path)
    section = max(10, int(duration // clip_count))
    clips = []
    for i in range(clip_count):
        start = min(i * section, max(0, duration - clip_duration))
        outfile = os.path.join(working_dir, f"clip_{i+1:02d}.mp4")
        _run_cmd(["ffmpeg", "-y", "-ss", str(start), "-i", video_path, "-t", str(clip_duration), "-c", "copy", outfile])
        clips.append({"clip_index": i + 1, "start": start, "duration": clip_duration, "path": outfile})
    return clips


def generate_storyboard_images(frame_paths: List[str], out_dir: str) -> List[str]:
    storyboard = []
    for frame in frame_paths:
        storyboard.append(frame)
    return storyboard


def process(video_path: str, working_dir: str) -> Dict:
    audio_path = extract_audio(video_path, working_dir)
    transcript = speech_to_text(audio_path)

    frames = extract_keyframes(video_path, working_dir, scene_thresh=0.28, max_frames=4)
    frame_captions = [caption_frame(p) for p in frames]

    transcript_chunks = chunk_transcript(transcript, chunk_size=900)
    summary_results = summarize_transcript(transcript_chunks, frame_captions)

    clips = generate_clips(video_path, working_dir, clip_count=6, clip_duration=18)
    storyboard = generate_storyboard_images(frames, working_dir)

    return {
        "source_video": video_path,
        "duration_seconds": video_duration(video_path),
        "transcript": transcript,
        "frame_captions": frame_captions,
        "summary": summary_results.get("full_summary"),
        "clip_ideas": summary_results.get("clip_ideas"),
        "generated_clips": clips,
        "storyboard_images": storyboard,
        "text_overlay_script": "(Generated inside summary content above)",
    }
