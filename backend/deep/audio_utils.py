"""Audio preprocessing + feature extraction used by BOTH training and inference."""
import io

import librosa
import numpy as np

from . import config as C

# Interpretable features (used for the ML model AND for the "why" explanation).
NAMED_FEATURES = [
    "f0_mean", "f0_min", "f0_max", "f0_std", "f0_slope",
    "voiced_ratio", "jitter", "shimmer", "harmonic_ratio_db",
    "spectral_centroid", "spectral_flatness",
    "rms_db_mean", "rms_db_range", "active_seconds",
    "burst_count", "mean_pause",
]


# ----------------------------------------------------------------------------
# Loading / preparing
# ----------------------------------------------------------------------------
def load_audio_bytes(data: bytes) -> np.ndarray:
    """Decode audio held in memory (mic recording or upload). Nothing touches disk."""
    y, _ = librosa.load(io.BytesIO(data), sr=C.SR, mono=True)
    return y.astype(np.float32)


def load_audio_file(path: str) -> np.ndarray:
    y, _ = librosa.load(path, sr=C.SR, mono=True)
    return y.astype(np.float32)


def prepare_waveform(y: np.ndarray) -> np.ndarray:
    """Remove DC offset, peak-normalise (mic gain independent), trim edge silence."""
    y = np.asarray(y, dtype=np.float32)
    if y.size == 0:
        return y
    y = y - float(y.mean())
    peak = float(np.abs(y).max())
    if peak < 1e-6:
        return y
    y = y / peak * 0.95
    trimmed, _ = librosa.effects.trim(y, top_db=35, frame_length=1024, hop_length=C.HOP)
    return trimmed if len(trimmed) >= int(0.5 * C.SR) else y


def fix_length(y: np.ndarray, n: int) -> np.ndarray:
    if len(y) >= n:
        return y[:n]
    return np.pad(y, (0, n - len(y)))


def _window_energies(y: np.ndarray, n: int, step: int):
    cs = np.concatenate([[0.0], np.cumsum(y.astype(np.float64) ** 2)])
    starts = np.arange(0, max(len(y) - n, 0) + 1, step)
    energies = cs[np.minimum(starts + n, len(y))] - cs[starts]
    return starts, energies


def best_window(y: np.ndarray, sr: int = C.SR, duration: float = C.DURATION) -> np.ndarray:
    """The loudest `duration`-second window (most likely to contain crying)."""
    n = int(sr * duration)
    if len(y) <= n:
        return fix_length(y, n)
    starts, energies = _window_energies(y, n, step=sr // 4)
    s = int(starts[int(np.argmax(energies))])
    return y[s:s + n]


def windows_for_inference(y: np.ndarray, sr: int = C.SR, duration: float = C.DURATION,
                          max_windows: int = C.MAX_WINDOWS):
    """Up to `max_windows` distinct windows, loudest first. Averaging predictions
    over several windows is more reliable than trusting a single crop."""
    n = int(sr * duration)
    if len(y) <= n:
        return [fix_length(y, n)]
    starts, energies = _window_energies(y, n, step=sr // 2)
    order = np.argsort(-energies)
    chosen = []
    for i in order:
        s = int(starts[i])
        if all(abs(s - c) >= sr for c in chosen):   # at least 1 s apart
            chosen.append(s)
        if len(chosen) >= max_windows:
            break
    return [y[s:s + n] for s in chosen]


# ----------------------------------------------------------------------------
# Spectrogram
# ----------------------------------------------------------------------------
def logmel(y: np.ndarray, sr: int = C.SR) -> np.ndarray:
    """Log-mel spectrogram, standardised per sample. Shape: (N_MELS, frames)."""
    S = librosa.feature.melspectrogram(
        y=y, sr=sr, n_fft=C.N_FFT, hop_length=C.HOP,
        n_mels=C.N_MELS, fmin=C.FMIN, fmax=C.FMAX)
    S = librosa.power_to_db(S, ref=np.max, top_db=80.0)
    return ((S - S.mean()) / (S.std() + 1e-6)).astype(np.float32)


def mel_group_ranges_hz(n_groups: int = 16):
    """Hz range covered by each of the CNN's `n_groups` frequency rows."""
    centers = librosa.mel_frequencies(n_mels=C.N_MELS, fmin=C.FMIN, fmax=C.FMAX)
    per = C.N_MELS // n_groups
    return [(float(centers[g * per]), float(centers[min(g * per + per - 1, C.N_MELS - 1)]))
            for g in range(n_groups)]


# ----------------------------------------------------------------------------
# Interpretable acoustic features
# ----------------------------------------------------------------------------
def _runs(mask, min_len):
    runs, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                runs.append([start, i])
            start = None
    if start is not None and len(mask) - start >= min_len:
        runs.append([start, len(mask)])
    return runs


def _merge_close(runs, max_gap):
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= max_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    return merged


def analyze_acoustics(y: np.ndarray, sr: int = C.SR) -> dict:
    """Return interpretable features, an ML feature vector and plot series.

    jitter / shimmer / harmonic_ratio_db are frame-level APPROXIMATIONS of the
    Praat measures (good for relative comparison, not clinical values).
    """
    hop = C.HOP
    dt = hop / sr
    y = np.asarray(y, dtype=np.float32)
    f = {k: np.nan for k in NAMED_FEATURES}

    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    f0, vflag, _ = librosa.pyin(y, fmin=150, fmax=1000, sr=sr, frame_length=2048, hop_length=hop)
    m = min(len(rms), len(f0))
    rms, f0, vflag = rms[:m], f0[:m], vflag[:m]

    ref = max(float(rms.max()), 1e-8)
    rms_db = 20.0 * np.log10(np.maximum(rms, 1e-8) / ref)
    active = rms_db > -30.0

    # -- energy & timing ------------------------------------------------------
    f["active_seconds"] = float(active.sum() * dt)
    if active.any():
        f["rms_db_mean"] = float(rms_db[active].mean())
    if active.sum() >= 5:
        f["rms_db_range"] = float(np.percentile(rms_db[active], 95) - np.percentile(rms_db[active], 5))
    runs = _merge_close(_runs(active, 3), max_gap=6)
    f["burst_count"] = float(len(runs))
    gaps = [(runs[i + 1][0] - runs[i][1]) * dt for i in range(len(runs) - 1)]
    f["mean_pause"] = float(np.mean(gaps)) if gaps else 0.0

    # -- pitch ----------------------------------------------------------------
    voiced = np.asarray(vflag, dtype=bool) & ~np.isnan(f0)
    f["voiced_ratio"] = float(voiced.mean() * 100.0)
    if voiced.sum() >= 5:
        fv = f0[voiced]
        tv = np.arange(m)[voiced] * dt
        f["f0_mean"], f["f0_min"], f["f0_max"], f["f0_std"] = (
            float(fv.mean()), float(fv.min()), float(fv.max()), float(fv.std()))
        f["f0_slope"] = float(np.polyfit(tv, fv, 1)[0])
        pair = voiced[:-1] & voiced[1:]
        if pair.sum() >= 3:
            T = 1.0 / np.where(np.isnan(f0), 1.0, f0)
            f["jitter"] = float(np.mean(np.abs(np.diff(T))[pair]) / (np.mean(T[voiced]) + 1e-9) * 100.0)
            f["shimmer"] = float(np.mean(np.abs(np.diff(rms))[pair]) / (np.mean(rms[voiced]) + 1e-9) * 100.0)

    # -- spectrum / voice quality --------------------------------------------
    sel = active if active.any() else np.ones(m, dtype=bool)
    cent = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=C.N_FFT, hop_length=hop)[0][:m]
    flat = librosa.feature.spectral_flatness(y=y, n_fft=C.N_FFT, hop_length=hop)[0][:m]
    f["spectral_centroid"] = float(cent[sel[:len(cent)]].mean())
    f["spectral_flatness"] = float(flat[sel[:len(flat)]].mean())
    y_h, y_p = librosa.effects.hpss(y)
    f["harmonic_ratio_db"] = float(10 * np.log10((np.sum(y_h ** 2) + 1e-9) / (np.sum(y_p ** 2) + 1e-9)))

    # -- ML vector = interpretable + MFCC summary -----------------------------
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, n_fft=C.N_FFT, hop_length=hop)
    names = list(NAMED_FEATURES) + [f"mfcc{i}_mean" for i in range(13)] + [f"mfcc{i}_std" for i in range(13)]
    vector = np.array([f[k] for k in NAMED_FEATURES] + list(mfcc.mean(1)) + list(mfcc.std(1)), dtype=np.float64)

    series = {
        "t": [round(i * dt, 3) for i in range(m)],
        "f0": [None if not voiced[i] else float(f0[i]) for i in range(m)],
        "rms_db": [float(v) for v in rms_db],
    }
    return {"features": f, "vector": vector, "names": names, "series": series}
