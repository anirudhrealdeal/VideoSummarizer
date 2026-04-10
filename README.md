# Summarize

End-to-end full stack project that turns long educational videos into:
- 10-min summary,
- short reel / clip scripts,
- generated MP4 clip segments,
- storyboard images,
- text overlay script hints.

## Architecture
- Backend: FastAPI + OpenAI + ffmpeg + yt-dlp
- Frontend: Vite + React + Axios

## Requirements
- Python 3.11+
- Node.js 18+
- ffmpeg
- yt-dlp
- OpenAI API key (set `OPENAI_API_KEY`)

## Setup Backend
```bash
cd /Users/anirudhchakravartykumar/Desktop/Work/VLM based educational/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY="your-key"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Local mode
Use the file uploader in frontend.

### Youtube mode
Paste a YouTube URL and process.

## Setup Frontend
```bash
cd /Users/anirudhchakravartykumar/Desktop/Work/VLM based educational/frontend
npm install
npm run dev
```

## How it works
1. Video ingestion (local or yt-dlp)
2. Audio extraction via ffmpeg
3. Whisper transcription (OpenAI)
4. Keyframe extraction + VLM caption (OpenAI GPT-4.1-mini)
5. Transcript chunk summarization + 10-min summary generation
6. Clip generation with ffmpeg segments via timestamps
7. Output JSON returned to UI

## Notes
- This is a hackathon MVP; production requires queueing, retries, auth, storage, and cost controls.
- On local Mac, install `ffmpeg` and `yt-dlp` via homebrew.
- In Colab, use the same Python code in a notebook with `!pip install -r requirements.txt` and load file with upload widget.

## VLM route
`video_pipeline.py` uses OpenAI multi-modal calls for image captions over keyframes (base64 encoded). If network or API limits, switch to text-only route by using the transcript content.
