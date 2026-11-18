"""Decode an uploaded file to a mono float32 waveform at 16 kHz. WAV is read natively (scipy);
other formats use ffmpeg if installed (the web app already converts recordings/uploads to WAV in the browser)."""
import os
import shutil
import subprocess
import tempfile

import numpy as np
from scipy.io import wavfile

from ml.features import SR_PITCH, resample


class AudioError(Exception):
    """Message is safe to show to the user. `code` lets the frontend show a localized message."""
    def __init__(self, message, code="invalid_audio"):
        super().__init__(message)
        self.code = code


def _read_wav(path):
    sr, data = wavfile.read(path)
    if data.dtype == np.uint8:
        y = (data.astype(np.float32) - 128) / 128
    elif data.dtype == np.int16:
        y = data.astype(np.float32) / 32768
    elif data.dtype == np.int32:
        y = data.astype(np.float32) / 2147483648
    else:
        y = data.astype(np.float32)
    if y.ndim > 1:
        y = y.mean(1)
    return y, int(sr)


def _ffmpeg_to_wav(path):
    if shutil.which("ffmpeg") is None:
        raise AudioError("This audio format needs ffmpeg on the server. Please upload a WAV file instead.")
    fd, tmp = tempfile.mkstemp(suffix=".wav"); os.close(fd)
    try:
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", tmp],
                           capture_output=True, timeout=60)
        if r.returncode != 0:
            raise AudioError("This file is not a valid audio file.")
        return _read_wav(tmp)
    except subprocess.TimeoutExpired:
        raise AudioError("Audio took too long to decode.")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def load_audio(path, min_seconds=0.5):
    """Returns (y16k float32 normalised, original_duration_s)."""
    try:
        y, sr = _read_wav(path)
    except Exception:
        y, sr = _ffmpeg_to_wav(path)
    y = np.nan_to_num(y.astype(np.float32))
    dur = len(y) / sr
    if dur < min_seconds:
        raise AudioError("Audio is too short. Please provide at least 1 second of crying.")
    if float(np.max(np.abs(y))) < 1e-4:
        raise AudioError("The audio appears to be silent.")
    y = y - y.mean()
    y = resample(y, sr, SR_PITCH)
    peak = float(np.max(np.abs(y)))
    return (y / peak * 0.95).astype(np.float32), dur
