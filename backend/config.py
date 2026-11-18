"""Central configuration: paths, limits, cookie settings."""
import os
from datetime import timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
SPECTROGRAM_DIR = BASE_DIR / "storage" / "spectrograms"
DATASET_DIR = BASE_DIR / "dataset"
MODEL_DIR = BASE_DIR / "model"
FRONTEND_DIR = BASE_DIR.parent / "frontend"
DB_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "auracry.db"))

ALLOWED_EXTENSIONS = {"wav", "mp3", "m4a", "ogg", "flac", "webm"}
MAX_AUDIO_MB = 15
MIN_SECONDS = 0.5


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    MAX_CONTENT_LENGTH = 80 * 1024 * 1024
