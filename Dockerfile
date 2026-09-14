FROM python:3.11-slim

# FFmpeg is required by the video pipeline (edge-tts + ffmpeg concat).
# Installed here in the image, so the runtime never needs root/apt.
RUN apt-get update -qq && apt-get install -y -qq ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# All source (pipeline files + webapp) lives in the repo root
COPY . /app

WORKDIR /app/webapp
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]