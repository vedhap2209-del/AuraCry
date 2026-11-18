# AuraCry - single container that serves BOTH the web app and the API (Flask serves the frontend).
# Includes ffmpeg (audio decode/validation) and libsndfile (soundfile).
FROM python:3.11-slim

# system libs: ffmpeg/ffprobe for audio, libsndfile for soundfile, libgomp for sklearn/scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libsndfile1 libgomp1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# app code (frontend is served by Flask from ../frontend; models + data ship in the image)
COPY . .

ENV PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    COOKIE_SECURE=1 \
    OTP_DEV_ECHO=1 \
    RATELIMIT_ENABLED=1

EXPOSE 8000
# init the SQLite DB (and an admin if ADMIN_* env is set), then serve with gunicorn
CMD ["bash", "start.sh"]
