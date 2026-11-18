"""Central configuration shared by training and the backend.

Keeping every audio/feature setting here guarantees that training and inference
use exactly the same preprocessing (train/serve skew is a classic cause of
"good validation score, bad real-world accuracy").
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # = backend/
MODEL_DIR = ROOT / "model"

# Unified 5 classes, index-aligned with the ML stack's codes [hu, ti, dc, bp, bu] so fusion is a plain weighted average.
CLASSES = ["Hungry", "Tired", "Discomfort", "Belly Pain", "Needs Burping"]
LABEL_ORDER = ["hungry", "tired", "discomfort", "belly_pain", "burping"]   # manifest label -> index

# Donate-a-Cry corpus folder names -> your class names.
# NOTE: "discomfort" -> Fussy and "belly_pain" -> Distress are approximations.
# Change this mapping if you want a different grouping.
FOLDER_TO_CLASS = {
    "hungry": "Hungry",
    "tired": "Sleepy", "sleepy": "Sleepy",
    "discomfort": "Fussy", "fussy": "Fussy",
    "burping": "Burp", "burp": "Burp",
    "belly_pain": "Distress", "distress": "Distress",
}
# Two-letter codes at the end of Donate-a-Cry file names (fallback if no folders).
CODE_TO_CLASS = {"hu": "Hungry", "ti": "Sleepy", "dc": "Fussy", "bu": "Burp", "bp": "Distress"}

# Audio / spectrogram settings
SR = 16000
DURATION = 3.0          # seconds analysed per window
N_FFT = 1024
HOP = 256
N_MELS = 128            # must be divisible by 8 (three pooling stages)
FMIN = 50
FMAX = 4000          # band-limit to 4 kHz: Donate-a-Cry Android clips are 8 kHz, so anything above 4 kHz would let the
                     # model separate classes by recording device instead of by cry (Phase 3 device-bias guard)

# Inference behaviour
MAX_WINDOWS = 5         # up to N loudest 3-second windows are averaged
LOW_CONFIDENCE = 0.45   # below this -> "uncertain"
MIN_MARGIN = 0.08       # top1 - top2 below this -> "uncertain"
MIN_ACTIVE_SECONDS = 0.5  # less audible sound than this -> "no cry detected"
MAX_UPLOAD_MB = 15

# What each cry type usually sounds like (general description, NOT evidence from a recording)
DESCRIPTIONS = {
    "Hungry": "Rhythmic, repeated cries that build up in intensity, typically in the 250-600 Hz pitch range.",
    "Sleepy": "Softer, lower-energy whining with a long falling melody and little variation.",
    "Fussy": "Low-level, intermittent whimpering: mild protest, discomfort or wanting attention.",
    "Burp": "Strained, breathy sounds with a lower harmonic-to-noise ratio, linked to trapped air.",
    "Distress": "High-pitched, intense, unstable crying that signals pain or strong discomfort.",
}
