"""Phase 4: train and honestly evaluate the ML stack (RF -> AdaBoost -> Logistic Regression) on the unified dataset.

Reads the per-unit features from featurize_ml.py. Trains on the `train` split (real + augmented units), evaluates on the
held-out `test` split at the RECORDING level (average the unit probabilities of a clip, then decide) - the same way the
app serves a result. Reports every model side by side plus a majority baseline, and a grouped 5-fold CV on the real
clips as a second, augmentation-free estimate.

    python -m ml.train_unified --features ../data/features_ml.npz
writes backend/model/stack.joblib and backend/model/metrics.json
"""
import argparse
import json
import time
import warnings
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, classification_report,
                             confusion_matrix, f1_score)
from sklearn.model_selection import StratifiedGroupKFold

from ml.features import FEATURE_COLUMNS
from ml.stack import CascadeStack, add_engineered, expand_proba
from config import MODEL_DIR

LABELS = {"hu": "Hungry", "ti": "Tired", "dc": "Discomfort", "bp": "Belly Pain", "bu": "Needs Burping"}


def per_clip(prob_units, clip_ids):
    """Average unit probabilities within each clip. Returns (clip_id[], prob[n_clips, C]) in first-seen order."""
    order, acc, cnt = [], defaultdict(lambda: 0.0), defaultdict(int)
    for p, c in zip(prob_units, clip_ids):
        if c not in cnt:
            order.append(c)
        acc[c] = acc[c] + p; cnt[c] += 1
    return order, np.array([acc[c] / cnt[c] for c in order])


def clip_truth(y_units, clip_ids):
    d = {}
    for yy, c in zip(y_units, clip_ids):
        d[c] = yy
    return d


def scores(ytrue, ypred, nC):
    return dict(accuracy=round(accuracy_score(ytrue, ypred), 4),
                balanced_accuracy=round(balanced_accuracy_score(ytrue, ypred), 4),
                macro_f1=round(f1_score(ytrue, ypred, labels=list(range(nC)), average="macro", zero_division=0), 4))


def fit_single(name, X, y, nC, seed=42):
    cs = CascadeStack(n_classes=nC, seed=seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = cs._fit_base(name, X, y)
    return lambda Z: expand_proba(m.predict_proba(Z), m.classes_, nC)


def eval_on(predict, Xte_units, clip_ids_te, truth, nC):
    P = predict(Xte_units)
    cids, cp = per_clip(P, clip_ids_te)
    yt = np.array([truth[c] for c in cids]); yp = cp.argmax(1)
    return scores(yt, yp, nC), yt, yp


def class_profiles(X_real_units, y_real_units, groups, codes):
    prof = {"n_rows": int(len(X_real_units)), "classes": {}, "global": {}}
    for j, col in enumerate(FEATURE_COLUMNS):
        v = X_real_units[:, j]
        prof["global"][col] = {"mean": float(v.mean()), "std": float(v.std() or 1.0),
                               "p1": float(np.quantile(v, .01)), "p99": float(np.quantile(v, .99))}
    for ci, code in enumerate(codes):
        sub = X_real_units[y_real_units == ci]
        g = groups[y_real_units == ci]
        p = {"n": int(len(sub)), "recordings": int(len(np.unique(g)))}
        if len(sub) >= 3:
            for j, col in enumerate(FEATURE_COLUMNS):
                v = sub[:, j]
                p[col] = {"mean": float(v.mean()), "std": float(v.std() or 1e-6),
                          "p10": float(np.quantile(v, .1)), "p90": float(np.quantile(v, .9))}
        prof["classes"][code] = p
    return prof


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", required=True)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    t0 = time.time()
    d = np.load(a.features, allow_pickle=True)
    X, y, groups, split, clip_id, is_aug = d["X"], d["y"], d["groups"], d["split"], d["clip_id"], d["is_aug"]
    codes = list(d["codes"]); classes = list(d["classes"]); nC = len(codes)
    Xe = add_engineered(X)

    tr = split == "train"; te = split == "test"
    Xtr, ytr, gtr = Xe[tr], y[tr], groups[tr]
    truth_te = clip_truth(y[te], clip_id[te])

    # ---- compare each model at the recording level on the held-out test set
    comparison = {}
    single = {}
    for name, disp in [("rf", "Random Forest"), ("ada", "AdaBoost")]:
        pred = fit_single(name, Xtr, ytr, nC, a.seed)
        sc, _, _ = eval_on(pred, Xe[te], clip_id[te], truth_te, nC)
        comparison[disp] = {"recording_level": sc}
        single[name] = pred
    # LR on raw features (stage-3 learner alone, for reference)
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, class_weight="balanced", random_state=a.seed)).fit(Xtr, ytr)
    sc_lr, _, _ = eval_on(lambda Z: expand_proba(lr.predict_proba(Z), lr[-1].classes_, nC), Xe[te], clip_id[te], truth_te, nC)
    comparison["Logistic Regression"] = {"recording_level": sc_lr}

    # ---- the served stack
    print("training stack...", flush=True)
    stack = CascadeStack(n_classes=nC, seed=a.seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        stack.fit(Xtr, ytr, gtr)
    sc_stack, yt, yp = eval_on(lambda Z: stack.predict_proba(Z), Xe[te], clip_id[te], truth_te, nC)
    comparison["Stack RF>Ada>LR"] = {"recording_level": sc_stack}

    # ---- majority baseline (recording level)
    maj = np.bincount(ytr, minlength=nC).argmax()
    n_test_clips = len(truth_te)
    maj_acc = round(np.mean([v == maj for v in truth_te.values()]), 4)

    # ---- grouped 5-fold CV on REAL clips only (augmentation-free second estimate)
    real = (is_aug == 0)
    Xr, yr, gr, cr = Xe[real], y[real], groups[real], clip_id[real]
    cv_macro = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for k, (tri, tei) in enumerate(StratifiedGroupKFold(5, shuffle=True, random_state=a.seed).split(Xr, yr, gr)):
            m = CascadeStack(n_classes=nC, seed=a.seed).fit(Xr[tri], yr[tri], gr[tri])
            _, cp = per_clip(m.predict_proba(Xr[tei]), cr[tei])
            cids, _ = per_clip(m.predict_proba(Xr[tei]), cr[tei])
            tc = clip_truth(yr[tei], cr[tei]); ytc = np.array([tc[c] for c in cids])
            cv_macro.append(f1_score(ytc, cp.argmax(1), labels=list(range(nC)), average="macro", zero_division=0))
            print(f"  cv fold {k}: macro-F1 {cv_macro[-1]:.3f}", flush=True)

    # ---- leaky (unit-level random) reference, to show what leakage would inflate the number to
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_predict
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        leak_pred = cross_val_predict(RandomForestClassifier(200, class_weight="balanced_subsample", n_jobs=-1, random_state=a.seed),
                                      Xr, yr, cv=5)
    leaky_macro = round(f1_score(yr, leak_pred, labels=list(range(nC)), average="macro", zero_division=0), 4)

    # ---- report + per-class on test
    rep = classification_report(yt, yp, labels=list(range(nC)), target_names=[LABELS[c] for c in codes],
                                output_dict=True, zero_division=0)
    cm = confusion_matrix(yt, yp, labels=list(range(nC))).tolist()
    print("\n" + classification_report(yt, yp, labels=list(range(nC)), target_names=[LABELS[c] for c in codes], zero_division=0))

    # ---- save bundle
    prof = class_profiles(X[real], y[real], groups[real], codes)
    present = sorted({int(v) for v in truth_te.values()} | set(np.unique(ytr)))
    absent = [codes[i] for i in range(nC) if i not in present]
    bundle = {"model": stack, "codes": codes, "labels": LABELS, "feature_columns": FEATURE_COLUMNS,
              "profiles": prof, "absent_codes": absent, "trained_rows": int(tr.sum())}
    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(bundle, MODEL_DIR / "stack.joblib", compress=3)

    class_counts = {LABELS[codes[i]]: int((y[real] == i).sum()) for i in range(nC)}
    metrics = {
        "mode": "unified_subjectwise_split",
        "model_name": "Stack RF>Ada>LR",
        "task": "cry_reason",
        "classes": [LABELS[c] for c in codes],
        "test": sc_stack, "per_class": rep, "confusion_matrix": cm, "labels": [LABELS[c] for c in codes],
        "comparison": comparison,
        "majority_baseline_accuracy": maj_acc,
        "majority_class": LABELS[codes[maj]],
        "grouped_cv_macro_f1": {"mean": round(float(np.mean(cv_macro)), 4), "std": round(float(np.std(cv_macro)), 4),
                                "folds": [round(float(v), 4) for v in cv_macro]},
        "leaky_split_reference": {"unit_level_random_cv_macro_f1": leaky_macro,
                                  "note": "random unit-level split lets a recording appear in train and test; the gap to the "
                                          "grouped score is leakage, not skill"},
        "n_test_clips": n_test_clips, "n_train_units": int(tr.sum()), "class_counts": class_counts, "n_rows": int(real.sum()),
        "trained_seconds": round(time.time() - t0, 1),
    }
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print("\nTEST (recording level):", sc_stack)
    print("majority baseline acc:", maj_acc, "| grouped CV macro-F1:", metrics["grouped_cv_macro_f1"]["mean"],
          "| leaky ref:", leaky_macro)
    print("saved model/stack.joblib + metrics.json in", metrics["trained_seconds"], "s")


if __name__ == "__main__":
    main()
