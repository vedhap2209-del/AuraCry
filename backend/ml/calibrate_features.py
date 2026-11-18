"""Check this project's audio feature extractor against the CSV, on the ORIGINAL audio.
    python -m ml.calibrate_features --audio_dir path/to/wavs [--csv dataset/test_dataset_clean.csv] [--limit 40]
For each CSV row whose Original_File is found in audio_dir, the unit [Start_sec, End_sec] is re-measured and compared.
Prints per-feature correlation and median difference. Large differences = the live app sees different numbers than the
model was trained on (then adjust ml/features.py: sample rate, pitch range, HNR/MFCC conventions)."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ml import features as F
from ml.audio_io import load_audio


def main(a):
    d = pd.read_csv(a.csv)
    files = {p.stem: p for p in Path(a.audio_dir).rglob("*") if p.suffix.lower() in (".wav", ".mp3", ".ogg", ".flac", ".m4a")}
    mine, ref, n = [], [], 0
    for _, r in d.iterrows():
        stem = Path(str(r["Original_File"])).stem
        if stem not in files:
            continue
        y, _ = load_audio(str(files[stem]), 0.1)
        v = F.unit_features(y, float(r["Start_sec"]), float(r["End_sec"]))
        if v is None:
            continue
        mine.append(v); ref.append(r[F.FEATURE_COLUMNS].to_numpy(float)); n += 1
        if n >= a.limit:
            break
    if not n:
        raise SystemExit("No CSV rows matched audio files in --audio_dir (match is on the Original_File name).")
    mine, ref = np.array(mine), np.array(ref)
    print(f"{n} units compared\n{'feature':10s} {'corr':>6s} {'median diff':>12s} {'CSV median':>11s}")
    for j, c in enumerate(F.FEATURE_COLUMNS):
        cor = np.corrcoef(mine[:, j], ref[:, j])[0, 1] if n > 2 else float("nan")
        print(f"{c:10s} {cor:6.2f} {np.median(mine[:, j] - ref[:, j]):12.2f} {np.median(ref[:, j]):11.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--audio_dir", required=True)
    ap.add_argument("--csv", default="dataset/test_dataset_clean.csv"); ap.add_argument("--limit", type=int, default=40)
    main(ap.parse_args())
