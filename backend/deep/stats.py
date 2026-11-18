"""Statistics helpers: class profiles (for explanations) and ensemble weighting."""
import numpy as np


def build_class_profiles(feature_dicts, labels, classes, feature_keys):
    """Mean/std/p10/p90 of each interpretable feature, per class and overall.

    Computed on the TRAINING split only. The explanation module compares a new
    recording against these numbers, so reasons are grounded in real data.
    """
    labels = np.asarray(labels)
    arr = np.array([[fd.get(k, np.nan) for k in feature_keys] for fd in feature_dicts], dtype=float)
    out = {"classes": {}, "global": {}}

    for j, k in enumerate(feature_keys):
        col = arr[:, j]
        col = col[~np.isnan(col)]
        if len(col) >= 3:
            out["global"][k] = {"mean": float(col.mean()), "std": float(col.std())}

    for ci, cname in enumerate(classes):
        sel = labels == ci
        prof = {"n": int(sel.sum())}
        for j, k in enumerate(feature_keys):
            col = arr[sel, j]
            col = col[~np.isnan(col)]
            if len(col) >= 3:
                prof[k] = {
                    "mean": float(col.mean()), "std": float(col.std()),
                    "p10": float(np.percentile(col, 10)), "p90": float(np.percentile(col, 90)),
                    "n": int(len(col)),
                }
        out["classes"][cname] = prof
    return out


def expand_proba(p, model_classes, n_classes):
    """Place predict_proba columns into a full (N, n_classes) matrix
    (a class can be missing from a small training split)."""
    full = np.zeros((p.shape[0], n_classes), dtype=np.float64)
    for col, cls in enumerate(model_classes):
        full[:, int(cls)] = p[:, col]
    return full


def tune_fusion(dl_probs, ml_probs, y_true, grid=None, prefer=0.6):
    """Pick the deep-learning weight that maximises macro-F1 on validation data."""
    from sklearn.metrics import f1_score

    grid = list(np.round(np.arange(0.0, 1.01, 0.1), 2)) if grid is None else grid
    best_w, best_f1 = prefer, -1.0
    for w in sorted(grid, key=lambda v: abs(v - prefer)):      # ties -> closest to `prefer`
        fused = w * dl_probs + (1 - w) * ml_probs
        f1 = f1_score(y_true, fused.argmax(1), average="macro", zero_division=0)
        if f1 > best_f1 + 1e-9:
            best_w, best_f1 = float(w), float(f1)
    return best_w, best_f1
