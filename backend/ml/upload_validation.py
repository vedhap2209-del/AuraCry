"""Server-side upload validation (Phase 9). Never trusts the file extension or the browser's MIME type.

Order of checks (cheap -> expensive), each raising AudioError (safe, localized via an `error` code) on failure:
  1. size: not empty, within the limit
  2. magic bytes: the real file signature must be an audio container - a JPEG/PDF/MP4-video renamed to .wav is rejected
  3. ffprobe: there must be a real, decodable AUDIO stream; read its codec, sample rate, channels, duration
  4. duration bounds
Then, on the decoded waveform, non-blocking quality signals are returned as warning codes (silence, clipping, noise,
and a heuristic "this may not be a baby cry"). A valid audio file is NOT proof of a newborn cry - the app says so.
"""
import json
import shutil
import struct
import subprocess

import numpy as np

from ml.audio_io import AudioError

# minimum seconds of real audio, maximum accepted length
MIN_SECONDS = 1.0
MAX_SECONDS = 60.0

# audio container signatures (offset, bytes). webm/mkv share the EBML header.
_AUDIO_SIGS = [
    (0, b"RIFF", "wav"), (8, b"WAVE", "wav"),
    (0, b"ID3", "mp3"), (0, b"\xff\xfb", "mp3"), (0, b"\xff\xf3", "mp3"), (0, b"\xff\xf2", "mp3"),
    (0, b"OggS", "ogg"), (0, b"fLaC", "flac"), (0, b"\x1a\x45\xdf\xa3", "webm"),
]
# signatures that are definitely NOT the audio the user claims - used for a precise error message
_BAD_SIGS = [
    (0, b"\xff\xd8\xff", "a JPEG image"), (0, b"\x89PNG", "a PNG image"), (0, b"GIF8", "a GIF image"),
    (0, b"%PDF", "a PDF document"), (0, b"PK\x03\x04", "a ZIP/Office file"), (0, b"\x1f\x8b", "a GZIP archive"),
    (0, b"\x89HDF", "a data file"), (0, b"<!DOCTYPE", "an HTML page"), (0, b"<html", "an HTML page"),
]


def _starts(buf, offset, sig):
    return buf[offset:offset + len(sig)] == sig


def sniff(path):
    """Return ('audio', fmt) | ('bad', human_description) | ('mp4', brand) | ('unknown', None)."""
    with open(path, "rb") as fh:
        buf = fh.read(64)
    for off, sig, _desc in _BAD_SIGS:
        if _starts(buf, off, sig):
            return "bad", _desc
    for off, sig, fmt in _AUDIO_SIGS:
        if _starts(buf, off, sig):
            return "audio", fmt
    # ISO-BMFF (mp4/m4a/mov): '....ftyp<brand>' - brand tells audio (M4A) from video (mp4/mov/avc1)
    if buf[4:8] == b"ftyp":
        brand = buf[8:12].decode("latin1", "replace")
        return ("audio", "m4a") if brand.startswith(("M4A", "M4B", "mp4a")) else ("mp4", brand)
    return "unknown", None


def ffprobe(path):
    if shutil.which("ffprobe") is None:
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,codec_name,sample_rate,channels:format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return {"streams": [], "format": {}}
    return json.loads(r.stdout or "{}")


def validate_file(path, size_bytes, max_mb):
    """Raise AudioError(code=...) if the upload is not usable audio. Returns probe info on success."""
    if size_bytes == 0:
        raise AudioError("This file is empty.", code="empty_file")
    if size_bytes > max_mb * 1024 * 1024:
        raise AudioError(f"File is too large (max {max_mb} MB).", code="too_large")

    kind, info = sniff(path)
    if kind == "bad":
        raise AudioError(f"This looks like {info}, not an audio recording. Please upload a real audio file.", code="not_audio")
    if kind == "mp4":
        raise AudioError("This looks like a video file. Please upload an audio-only recording.", code="has_video")

    pr = ffprobe(path)
    if pr is not None:
        streams = pr.get("streams", [])
        audio = [s for s in streams if s.get("codec_type") == "audio"]
        video = [s for s in streams if s.get("codec_type") == "video"
                 and s.get("codec_name") not in ("mjpeg", "png", "bmp")]      # ignore cover art
        if not audio:
            if video:
                raise AudioError("This looks like a video file. Please upload an audio-only recording.", code="has_video")
            raise AudioError("No audio could be found in this file. It may be corrupted or not a real recording.", code="not_audio")
        a = audio[0]
        try:
            dur = float(pr.get("format", {}).get("duration") or 0)
        except (TypeError, ValueError):
            dur = 0.0
        if dur and dur < MIN_SECONDS:
            raise AudioError("Audio is too short. Please provide at least 1 second of crying.", code="too_short")
        if dur > MAX_SECONDS:
            raise AudioError(f"Audio is too long (max {int(MAX_SECONDS)} seconds). Please upload a shorter clip.", code="too_long")
        return {"codec": a.get("codec_name"), "sample_rate": a.get("sample_rate"), "channels": a.get("channels"), "duration": dur}
    # ffprobe unavailable: sniff passed, decoding (next step) is the remaining guard
    if kind == "unknown":
        raise AudioError("This file is not a recognised audio format. Use WAV, MP3, M4A, OGG or FLAC.", code="not_audio")
    return {"codec": None, "sample_rate": None, "channels": None, "duration": None}


def quality_warnings(y, sr=16000):
    """Non-blocking signals computed on the decoded, pre-denoise waveform. Returns a list of {code, detail}."""
    out = []
    y = np.asarray(y, np.float32)
    if y.size == 0:
        return out
    peak = float(np.max(np.abs(y)))
    rms = float(np.sqrt(np.mean(y ** 2)) + 1e-12)
    rms_db = 20 * np.log10(rms)
    if peak < 5e-3 or rms_db < -50:
        out.append({"code": "silent", "detail": "The recording is almost silent."})
    silent = bool(out)
    clip = float(np.mean(np.abs(y) > 0.98))
    if clip > 0.01:
        out.append({"code": "clipped", "detail": f"{clip*100:.0f}% of samples are clipped (too loud/distorted)."})
    # noisiness: a real cry is bursty (loud bursts over near-silence), so a HIGH noise floor relative to the peaks
    # suggests constant background noise. Only meaningful on a clip that isn't silent.
    if not silent:
        win = max(1, int(0.03 * sr))
        fr = np.array([np.sqrt(np.mean(y[i:i + win] ** 2) + 1e-12) for i in range(0, max(1, len(y) - win), win)])
        if len(fr) >= 8:
            floor = np.quantile(fr, 0.1); loud = np.quantile(fr, 0.9)
            if loud > 1e-3 and floor / loud > 0.62:
                out.append({"code": "noisy", "detail": "High background noise - the result may be less reliable."})
    # heuristic "is this a cry": a newborn cry sits mostly in ~250-700 Hz with strong voicing
    try:
        import librosa
        seg = y if len(y) <= sr * 4 else y[np.argmax([np.sum(y[i:i+sr*2]**2) for i in range(0, len(y)-sr*2, sr)]) * sr:][:sr * 4]
        f0, vflag, _ = librosa.pyin(seg, fmin=120, fmax=1200, sr=sr, frame_length=2048, hop_length=512)
        voiced = float(np.nan_to_num(vflag.astype(float)).mean())
        med = float(np.nanmedian(f0)) if np.any(vflag) else 0.0
        if voiced < 0.12 or not (220 <= med <= 750):
            out.append({"code": "maybe_not_cry",
                        "detail": "This may not be a newborn cry (pitch/voicing outside the usual cry range). The result is unreliable."})
    except Exception:
        pass
    return out
