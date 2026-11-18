"""Audio -> cry-unit segments -> the SAME 19 acoustic features that the training CSV contains.

CSV columns reproduced: Duration, Min_F0, Max_F0, Mean_F0, Std_F0, HNR, MFCC_1..MFCC_13.
Only numpy + scipy are needed (no librosa), so the app runs on a plain Python install.

How each column is computed (conventions inferred from the CSV, see HANDOFF.md):
  * F0   : YIN-style pitch tracker, 200-1200 Hz, over voiced 10 ms frames of the unit.
  * HNR  : autocorrelation harmonics-to-noise (dB) per frame, unvoiced frames = -200 (Praat-style
           convention - this is why the CSV has values down to -195), averaged over the unit.
  * MFCC : librosa-compatible (Slaney mel, 128 bands, n_fft 2048, hop 512, power->dB, DCT-II ortho),
           13 coefficients, mean over the unit, computed at 8 kHz like the Donate-a-Cry corpus.
`python -m ml.calibrate_features` compares this extractor with the CSV on real audio.
"""
import numpy as np
from scipy import signal
from scipy.fft import dct

SR_PITCH = 16000
SR_MFCC = 8000
F0_MIN, F0_MAX = 200.0, 1200.0
FEATURE_COLUMNS = ["Duration", "Min_F0", "Max_F0", "Mean_F0", "Std_F0", "HNR"] + [f"MFCC_{i}" for i in range(1, 14)]


# ----------------------------------------------------------------------------- helpers
def resample(y, sr_from, sr_to):
    if sr_from == sr_to:
        return y.astype(np.float32)
    g = np.gcd(int(sr_from), int(sr_to))
    return signal.resample_poly(y, int(sr_to) // g, int(sr_from) // g).astype(np.float32)


def frame_signal(y, size, hop):
    if len(y) < size:
        y = np.pad(y, (0, size - len(y)))
    n = 1 + (len(y) - size) // hop
    idx = np.arange(size)[None, :] + hop * np.arange(n)[:, None]
    return y[idx]


# ----------------------------------------------------------------------------- segmentation
def frame_rms_db(y, sr, win=0.025, hop=0.010):
    fr = frame_signal(y, int(win * sr), int(hop * sr))
    rms = np.sqrt((fr ** 2).mean(1) + 1e-12)
    return 20 * np.log10(rms + 1e-9), hop


def segment_cry_units(y, sr=SR_PITCH, thresh_db=-32.0, min_len=0.25, max_len=1.6, merge_gap=0.15, max_units=12):
    """Split a recording into cry units (voiced bursts) the way the dataset rows were cut.
    Returns [(start_s, end_s), ...] in time order."""
    if len(y) < sr * 0.3:
        return []
    db, hop = frame_rms_db(y, sr)
    ref = np.percentile(db, 98)
    act = db > ref + thresh_db
    runs, start = [], None
    for i, a in enumerate(list(act) + [False]):
        if a and start is None:
            start = i
        elif not a and start is not None:
            runs.append([start * hop, i * hop]); start = None
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= merge_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    units = []
    for s, e in merged:
        if e - s < min_len:
            continue
        n = int(np.ceil((e - s) / max_len))           # split very long bursts evenly
        step = (e - s) / n
        units += [(s + k * step, s + (k + 1) * step) for k in range(n)]
    if len(units) > max_units:                       # keep the loudest ones
        def loud(u):
            seg = y[int(u[0] * sr):int(u[1] * sr)]
            return float(np.mean(seg ** 2))
        units = sorted(sorted(units, key=loud, reverse=True)[:max_units])
    return [(round(s, 3), round(e, 3)) for s, e in units]


# ----------------------------------------------------------------------------- pitch + HNR
def pitch_hnr(seg, sr=SR_PITCH, win=0.032, hop=0.010, thresh=0.25):
    """Per-frame F0 (nan if unvoiced) and HNR (dB, -200 if unvoiced, nan if silent)."""
    W = int(win * sr); H = int(hop * sr)
    tmin, tmax = int(sr / F0_MAX), int(sr / F0_MIN) + 1
    fr = frame_signal(seg, W + tmax + 1, H).astype(np.float64)
    fr = fr - fr.mean(1, keepdims=True)
    a = fr[:, :W]
    e0 = (a ** 2).sum(1) + 1e-12
    d = np.zeros((len(fr), tmax + 1)); r = np.zeros_like(d)
    for tau in range(1, tmax + 1):
        b = fr[:, tau:tau + W]
        cross = (a * b).sum(1)
        eb = (b ** 2).sum(1) + 1e-12
        d[:, tau] = e0 + eb - 2 * cross
        r[:, tau] = cross / np.sqrt(e0 * eb)
    cm = np.cumsum(d[:, 1:], axis=1) / np.arange(1, tmax + 1)[None, :]
    dn = np.ones_like(d); dn[:, 1:] = d[:, 1:] / (cm + 1e-12)
    f0 = np.full(len(fr), np.nan); hnr = np.full(len(fr), -200.0)
    loud = (e0 / W) > 1e-7
    for i in range(len(fr)):
        if not loud[i]:
            hnr[i] = np.nan; continue
        cand = np.where(dn[i, tmin:tmax] < thresh)[0]
        if len(cand) == 0:
            continue
        tau = tmin + cand[0]
        while tau + 1 < tmax and dn[i, tau + 1] < dn[i, tau]:
            tau += 1
        y0, y1, y2 = dn[i, tau - 1], dn[i, tau], dn[i, min(tau + 1, tmax)]
        den = (y0 - 2 * y1 + y2)
        shift = 0.5 * (y0 - y2) / den if abs(den) > 1e-9 else 0.0
        f = sr / (tau + float(np.clip(shift, -1, 1)))
        if F0_MIN * 0.98 <= f <= F0_MAX * 1.02:
            f0[i] = f
            rr = float(np.clip(r[i, tau], 1e-4, 1 - 1e-4))
            hnr[i] = 10 * np.log10(rr / (1 - rr))
    return f0, hnr


# ----------------------------------------------------------------------------- MFCC (librosa-compatible)
def _hz_to_mel(f):
    f = np.asarray(f, dtype=float); lin = f / (200.0 / 3); logstep = np.log(6.4) / 27.0
    return np.where(f >= 1000, 15 + np.log(np.maximum(f, 1e-9) / 1000.0) / logstep, lin)


def _mel_to_hz(m):
    m = np.asarray(m, dtype=float); logstep = np.log(6.4) / 27.0
    return np.where(m >= 15, 1000.0 * np.exp(logstep * (m - 15)), (200.0 / 3) * m)


_FB = {}
def mel_filterbank(sr, n_fft, n_mels=128):
    key = (sr, n_fft, n_mels)
    if key not in _FB:
        fft_f = np.linspace(0, sr / 2, 1 + n_fft // 2)
        mel_f = _mel_to_hz(np.linspace(_hz_to_mel(0), _hz_to_mel(sr / 2), n_mels + 2))
        fdiff = np.diff(mel_f)
        ramps = mel_f[:, None] - fft_f[None, :]
        lower = -ramps[:-2] / fdiff[:-1, None]; upper = ramps[2:] / fdiff[1:, None]
        w = np.maximum(0, np.minimum(lower, upper))
        w *= (2.0 / (mel_f[2:n_mels + 2] - mel_f[:n_mels]))[:, None]
        _FB[key] = w.astype(np.float32)
    return _FB[key]


def mel_power(y, sr, n_fft=2048, hop=512, n_mels=128):
    yp = np.pad(y, n_fft // 2, mode="reflect") if len(y) > n_fft // 2 else np.pad(y, n_fft // 2)
    fr = frame_signal(yp, n_fft, hop) * np.hanning(n_fft + 1)[:-1][None, :]
    S = np.abs(np.fft.rfft(fr, axis=1)) ** 2
    return mel_filterbank(sr, n_fft, n_mels) @ S.T            # (n_mels, frames)


def mfcc_mean(y8k, n_mfcc=13):
    M = mel_power(y8k, SR_MFCC)
    db = 10 * np.log10(np.maximum(M, 1e-10))
    db = np.maximum(db, db.max() - 80.0)
    return dct(db, axis=0, type=2, norm="ortho")[:n_mfcc].mean(1)


# ----------------------------------------------------------------------------- one unit -> feature vector
def unit_features(y16, start, end):
    s, e = int(start * SR_PITCH), int(end * SR_PITCH)
    seg = y16[s:e]
    f0, hnr = pitch_hnr(seg)
    voiced = f0[~np.isnan(f0)]
    if len(voiced) < 3:
        return None
    hv = hnr[~np.isnan(hnr)]
    seg8 = resample(seg, SR_PITCH, SR_MFCC)
    vec = [end - start, voiced.min(), voiced.max(), voiced.mean(), voiced.std(), float(hv.mean()) if len(hv) else -200.0]
    vec += list(mfcc_mean(seg8))
    return np.array(vec, dtype=np.float64)


def extract_units(y16):
    """Full pipeline for one recording -> list of dicts {start,end,vector}. Silent/unvoiced units are dropped."""
    out = []
    for s, e in segment_cry_units(y16):
        v = unit_features(y16, s, e)
        if v is not None and np.all(np.isfinite(v)):
            out.append({"start": s, "end": e, "vector": v})
    return out


def waveform_envelope(y, sr, n=240):
    """Down-sampled peak envelope for drawing the waveform in the UI."""
    if len(y) == 0:
        return []
    k = max(1, len(y) // n)
    m = len(y) // k
    return [round(float(v), 3) for v in np.abs(y[:m * k]).reshape(m, k).max(1)]


def mel_spectrogram_db(y8k, n_mels=64):
    M = mel_power(y8k, SR_MFCC, n_fft=512, hop=80, n_mels=n_mels)
    db = 10 * np.log10(np.maximum(M, 1e-10))
    return np.maximum(db, db.max() - 80.0)
