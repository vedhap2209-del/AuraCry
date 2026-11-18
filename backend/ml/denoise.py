"""Phase 10: audio quality + noise reduction (scipy/numpy only, no extra dependency).

Two uses, kept separate on purpose:
  * quality_score(): a 0-100 indicator + SNR estimate shown to the user.
  * denoise(): band-pass to the cry band (250-4000 Hz, which also enforces the 4 kHz device-bias cap) plus light
    spectral gating of stationary background noise, used to produce the "cleaned" playback and spectrogram.

The trained models are fed the SAME preprocessing they were trained on (band-limit to 4 kHz, no spectral gating), so
denoising is a display/quality aid and does not create train/serve skew. We do not claim perfect noise cancellation.
"""
import numpy as np
from scipy import signal

SR = 16000
LO, HI = 250, 4000


def bandpass(y, sr=SR, lo=LO, hi=HI):
    hi = min(hi, sr // 2 - 1)
    sos = signal.butter(6, [lo, hi], btype="band", fs=sr, output="sos")
    return signal.sosfiltfilt(sos, y).astype(np.float32)


def spectral_gate(y, sr=SR, n_fft=512, hop=128, reduction=0.8):
    """Estimate a noise magnitude profile from the quietest 10% of frames and subtract it (soft gate)."""
    f, tt, Z = signal.stft(y, fs=sr, nperseg=n_fft, noverlap=n_fft - hop)
    mag, phase = np.abs(Z), np.angle(Z)
    frame_e = mag.sum(0)
    noise = np.quantile(mag[:, frame_e <= np.quantile(frame_e, 0.1)] if np.any(frame_e <= np.quantile(frame_e, 0.1)) else mag, 0.5, axis=1, keepdims=True)
    clean = np.maximum(mag - reduction * noise, 0.0)
    _, out = signal.istft(clean * np.exp(1j * phase), fs=sr, nperseg=n_fft, noverlap=n_fft - hop)
    return out.astype(np.float32)[: len(y)]


def denoise(y, sr=SR):
    y = np.nan_to_num(np.asarray(y, np.float32))
    z = spectral_gate(bandpass(y, sr), sr)
    peak = float(np.max(np.abs(z)) or 1.0)
    return (z / peak * 0.97).astype(np.float32)


def snr_db(y, sr=SR):
    """Rough SNR: energy of the loud (voice) frames vs the quiet (noise) frames, in dB."""
    win = max(1, int(0.03 * sr))
    fr = np.array([np.sqrt(np.mean(y[i:i + win] ** 2) + 1e-12) for i in range(0, max(1, len(y) - win), win)])
    if len(fr) < 8:
        return 20.0
    noise = np.quantile(fr, 0.1) + 1e-9
    sigv = np.quantile(fr, 0.9)
    return float(20 * np.log10(sigv / noise))


def quality_score(y, sr=SR):
    """0-100 quality indicator with a label. Combines level, clipping, and SNR."""
    y = np.asarray(y, np.float32)
    if y.size == 0:
        return {"score": 0, "label": "unusable", "snr_db": 0.0}
    rms_db = 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)
    clip = float(np.mean(np.abs(y) > 0.98))
    snr = snr_db(y, sr)
    score = 100.0
    score -= max(0, -(rms_db + 20)) * 1.5          # too quiet
    score -= min(40, clip * 1500)                  # clipping
    score -= max(0, (20 - snr)) * 2.5              # low SNR
    score = int(max(0, min(100, round(score))))
    label = "good" if score >= 75 else "fair" if score >= 45 else "poor"
    return {"score": score, "label": label, "snr_db": round(snr, 1), "clip_pct": round(clip * 100, 1), "rms_dbfs": round(float(rms_db), 1)}
