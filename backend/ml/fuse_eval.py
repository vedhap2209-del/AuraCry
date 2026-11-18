"""Phase 6: fuse the ML stack and the CNN+BiGRU, tune the weight on VALIDATION, report ML/DL/fused on TEST.

Both models now output the same 5 classes in the same order, so fusion is a plain weighted average per clip:
    fused = w * DL + (1 - w) * ML          (w = deep-branch weight, tuned on validation only)

    cd backend && python -m ml.fuse_eval --manifest ../data/manifest.csv --features ../data/features_ml.npz
writes backend/model/fusion.json and backend/model/fusion_report.json
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, f1_score

from config import MODEL_DIR
from ml.stack import add_engineered
from deep import config as DC
from deep.audio_utils import load_audio_file, prepare_waveform, best_window, logmel

ORDER = DC.LABEL_ORDER            # [hungry, tired, discomfort, belly_pain, burping]


def ml_clip_probs(features_npz, stack):
    d = np.load(features_npz, allow_pickle=True)
    X = add_engineered(d["X"]); clip = d["clip_id"]; split = d["split"]; y = d["y"]
    P = stack.predict_proba(X)
    acc, cnt, lab, sp = defaultdict(lambda: 0.0), defaultdict(int), {}, {}
    for p, c, yy, s in zip(P, clip, y, split):
        acc[c] += p; cnt[c] += 1; lab[c] = int(yy); sp[c] = s
    return {c: acc[c] / cnt[c] for c in cnt}, lab, sp


def dl_clip_probs(manifest, model):
    import torch
    root = Path(manifest).resolve().parent
    rows = [r for r in csv.DictReader(open(manifest, newline="")) if r["task"] == "cry_reason" and not int(r["is_augmented"])]
    out = {}
    model.eval()
    with torch.no_grad():
        for r in rows:
            if r["label"] not in ORDER:
                continue
            try:
                y = prepare_waveform(load_audio_file(str(root / r["audio_path"])))
            except Exception:
                continue
            S = torch.from_numpy(logmel(best_window(y))).unsqueeze(0).unsqueeze(0)
            out[r["sample_id"]] = torch.softmax(model(S), 1).numpy()[0]
    return out


def metrics(y, P, nC):
    yp = P.argmax(1)
    return dict(accuracy=round(accuracy_score(y, yp), 4), balanced_accuracy=round(balanced_accuracy_score(y, yp), 4),
               macro_f1=round(f1_score(y, yp, labels=list(range(nC)), average="macro", zero_division=0), 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True); ap.add_argument("--features", required=True)
    a = ap.parse_args()
    nC = len(ORDER)
    bundle = joblib.load(MODEL_DIR / "stack.joblib")
    ml_p, lab, sp = ml_clip_probs(a.features, bundle["model"])

    import torch
    from deep.model import CryCNNGRUModel
    ck = torch.load(MODEL_DIR / "cry_model.pt", map_location="cpu", weights_only=False)
    model = CryCNNGRUModel(**ck["arch"]); model.load_state_dict(ck["state_dict"])
    dl_p = dl_clip_probs(a.manifest, model)

    common = [c for c in ml_p if c in dl_p]
    def arrs(split):
        ids = [c for c in common if sp[c] == split]
        return (np.array([ml_p[c] for c in ids]), np.array([dl_p[c] for c in ids]), np.array([lab[c] for c in ids]))
    ml_va, dl_va, y_va = arrs("val"); ml_te, dl_te, y_te = arrs("test")
    print(f"aligned clips: val={len(y_va)} test={len(y_te)} (of {len(common)} common)")

    grid = np.round(np.arange(0, 1.001, 0.05), 3)
    curve = [f1_score(y_va, (w * dl_va + (1 - w) * ml_va).argmax(1), labels=list(range(nC)), average="macro", zero_division=0) for w in grid]
    w = float(grid[int(np.argmax(curve))]); val_f1 = round(float(max(curve)), 4)

    comp = {}
    for name, wk in [("ml_only", 0.0), ("dl_only", 1.0), (f"fused_w{w}", w)]:
        comp[name] = metrics(y_te, wk * dl_te + (1 - wk) * ml_te, nC)
    fixed = {f"w={ww}": metrics(y_te, ww * dl_te + (1 - ww) * ml_te, nC)["macro_f1"] for ww in (0.0, 0.25, 0.35, 0.5, 0.65, 1.0)}

    fused_te = w * dl_te + (1 - w) * ml_te
    rep = classification_report(y_te, fused_te.argmax(1), labels=list(range(nC)),
                                target_names=DC.CLASSES, output_dict=True, zero_division=0)
    (MODEL_DIR / "fusion.json").write_text(json.dumps(
        {"method": "weighted_average", "dl_weight": w, "classes": DC.CLASSES, "label_order": ORDER,
         "val_macro_f1": val_f1, "tuned_on": "validation split (never the test set)"}, indent=2))
    out = {"dl_weight": w, "val_macro_f1": val_f1, "weight_grid": list(grid), "val_curve": [round(c, 4) for c in curve],
           "test": comp, "test_macro_f1_by_weight": fixed, "fused_per_class": rep,
           "n_val": len(y_va), "n_test": len(y_te)}
    (MODEL_DIR / "fusion_report.json").write_text(json.dumps(out, indent=2))

    print(f"\ntuned deep weight w={w} (val macro-F1 {val_f1})")
    for k, v in comp.items():
        print(f"  {k:14s} acc {v['accuracy']:.3f} | bal_acc {v['balanced_accuracy']:.3f} | macro-F1 {v['macro_f1']:.3f}")
    print("  test macro-F1 by weight:", fixed)
    print("\nFused per-class (test):")
    print(classification_report(y_te, fused_te.argmax(1), labels=list(range(nC)), target_names=DC.CLASSES, zero_division=0))


if __name__ == "__main__":
    main()
