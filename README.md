# Σarize

End-to-end AI pipeline that turns long educational videos into a narrated summary video, reference slide deck, 6 key moment clips, full transcript, and a spaced-repetition review reminder.

## Stack
- **Backend:** FastAPI + OpenAI (Whisper, GPT-4o-mini, TTS) + ffmpeg + yt-dlp + APScheduler
- **Frontend:** Vite + React + Axios
- **Infra:** Docker + docker-compose

## Quick start (Docker)
```bash
git clone https://github.com/anirudhrealdeal/VideoSummarizer.git
cd VideoSummarizer
cp .env.example backend/.env   # fill in your keys
docker compose up --build
```
Frontend → http://localhost:3000  
Backend → http://localhost:8000

## Local setup

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env        # fill in your keys
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Required environment variables
See `.env.example` for the full list. Minimum to run:
- `OPENAI_API_KEY`
- `SMTP_USER` + `SMTP_PASS` (Gmail App Password) — for summary and review emails

## How it works
1. Video ingested via YouTube URL or file upload
2. Audio extracted with ffmpeg → transcribed with Whisper (parallel chunks)
3. GPT-4o-mini runs 6 parallel tasks: executive summary, key points, clip moment detection, slide content, SEO metadata, narration script
4. TTS (tts-1-hd) generates narration audio
5. ffmpeg cuts key moment clips and assembles the summary video
6. python-pptx + Pillow render the reference slide deck as PPTX and PDF
7. APScheduler sends a review reminder email after 7 days

## Dependencies
- Python 3.11+, Node.js 18+
- `ffmpeg` and `yt-dlp` (included in Docker image; install via Homebrew locally)
