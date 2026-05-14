FROM python:3.13-slim

# ffmpeg + yt-dlp runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent volume mount point for scheduler DB and uploaded files
RUN mkdir -p /data

ENV SCHEDULER_DB_PATH=/data/vlm_scheduler.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
