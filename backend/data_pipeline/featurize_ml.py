"""Phase 3 (ML side): turn every manifest clip into the 19 acoustic features the ML stack uses.

Consistency with inference: the app segments a recording into cry units and extracts 19 features PER UNIT, then
averages the per-unit predictions. Training mirrors that exactly - each unit is one training row, labelled with its
clip's class and grouped by its clip's subject - so there is no train/serve skew.

Device-bias guard (Phase 3): every clip is low-pass filtered to 4 kHz before feature extraction, because Donate-a-Cry
Android clips are 8 kHz (no content above 4 kHz) while iOS/DBL clips reach higher; without this a model can separate
classes by recording device instead of by cry. The MFCC path already runs at 8 kHz, so this only removes a leak.

    python -m data_pipeline.featurize_ml --manifest ../data/manifest.csv --out ../data/features_ml.npz
"""
import argparse
import csv
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from ml import features as F
from data_pipeline.labels import CLASSES

CODE = {"hungry": "hu", "tired": "ti", "discomfort": "dc", "belly_pain": "bp", "burping": "bu"}


def lowpass_4k(y, sr=F.SR_PITCH):
    if sr <= 8000:
        return y
    sos = signal.butter(8, 4000, "low", fs=sr, output="sos")
    return signal.sosfiltfilt(sos, y).astype(np.float32)


def load_16k(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1:
        y = y.mean(1)
    if sr != F.SR_PITCH:
        y = F.resample(y, sr, F.SR_PITCH)
    return lowpass_4k(y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    root = Path(a.manifest).resolve().parent
    rows = list(csv.DictReader(open(a.manifest, newline="")))
    rows = [r for r in rows if r["task"] == "cry_reason"]

    X, y, groups, split, clip_id, is_aug = [], [], [], [], [], []
    no_units = 0
    for i, r in enumerate(rows):
        try:
            yy = load_16k(root / r["audio_path"])
        except Exception:
            no_units += 1
            continue
        units = F.extract_units(yy)
        if not units:                              # fall back to the single loudest 1.5 s window
            n = int(1.5 * F.SR_PITCH)
            s = 0 if len(yy) <= n else int(np.argmax([np.sum(yy[k:k + n] ** 2) for k in range(0, len(yy) - n, n // 2)]) * (n // 2))
            v = F.unit_features(yy, s / F.SR_PITCH, min(s + n, len(yy)) / F.SR_PITCH)
            units = [{"vector": v}] if v is not None and np.all(np.isfinite(v)) else []
        if not units:
            no_units += 1
            continue
        for u in units:
            X.append(u["vector"]); y.append(CLASSES.index(r["label"])); groups.append(r["subject_id"])
            split.append(r["split"]); clip_id.append(r["sample_id"]); is_aug.append(int(r["is_augmented"]))
        if i % 300 == 0:
            print(i, "/", len(rows), flush=True)

    np.savez_compressed(a.out, X=np.array(X, dtype=np.float64), y=np.array(y),
                        groups=np.array(groups), split=np.array(split), clip_id=np.array(clip_id),
                        is_aug=np.array(is_aug), classes=np.array(CLASSES), codes=np.array([CODE[c] for c in CLASSES]))
    print(f"clips={len(rows)} units={len(X)} no_units_dropped={no_units}")
    for s in ("train", "val", "test"):
        m = np.array(split) == s
        print(s, "units", int(m.sum()), "clips", len({c for c, k in zip(clip_id, split) if k == s}))


if __name__ == "__main__":
    main()
