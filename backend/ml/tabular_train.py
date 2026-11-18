"""Train the RF -> AdaBoost -> Logistic-Regression stack from the feature CSVs and write model/stack.joblib + metrics.

Usage (from backend/):
    python -m ml.tabular_train                                   # uses dataset/*.csv
    python -m ml.tabular_train --train dataset/balanced_full_dataset_clean.csv --test dataset/test_dataset_clean.csv

Two modes
  A) --train given AND non-empty: fit on the train CSV (the "balanced" file), evaluate on the test CSV.
     Rows from the test CSV whose Original_File also appears in train are reported as LEAKAGE.
  B) no usable train CSV: grouped 5-fold cross-validation on the test CSV. Every recording
     (Original_File) is kept entirely inside one fold, so no recording is ever in train and test.
     Reported numbers are out-of-fold predictions = honest estimates. The final model is then fitted on all rows.
Several model variants are compared with the SAME folds; the best by macro-F1 is saved.
"""
import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import AdaBoostClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix,
                             f1_score)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.features import FEATURE_COLUMNS                                   # noqa: E402
from ml.stack import CascadeStack, add_engineered, expand_proba, smote    # noqa: E402

BASE = Path(__file__).resolve().parent.parent
CODES = ["hu", "dk", "ti", "bp", "sc", "dc", "ch", "bu", "lo"]
LABELS = {"hu": "Hungry", "dk": "Unclear", "ti": "Tired", "bp": "Belly Pain", "sc": "Scared",
          "dc": "Discomfort", "ch": "Cold / Hot", "bu": "Needs Burping", "lo": "Lonely"}
SEED = 42


DROP = set()


def load(path):
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return None
    d = pd.read_csv(p)
    d = d[d["Reason"].isin(CODES) & ~d["Reason"].isin(DROP)].dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)
    return d if len(d) else None


def xy(d):
    return d[FEATURE_COLUMNS].to_numpy(float), d["Reason"].map({c: i for i, c in enumerate(CODES)}).to_numpy(int), \
        d["Original_File"].to_numpy()


# --------------------------------------------------------------------------- model variants compared
class Single:
    """Wraps one plain model with the same balanced treatment, for fair comparison with the stack."""
    def __init__(self, kind, use_smote=True):
        self.kind, self.use_smote, self.n = kind, use_smote, len(CODES)

    def fit(self, X, y, groups):
        Xt, yt = smote(X, y, seed=SEED) if self.use_smote else (X, y)
        if self.kind == "rf":
            self.m = RandomForestClassifier(250, min_samples_leaf=2, class_weight="balanced_subsample", n_jobs=-1, random_state=SEED)
            self.m.fit(Xt, yt)
        elif self.kind == "ada":
            self.m = AdaBoostClassifier(estimator=DecisionTreeClassifier(max_depth=3, class_weight="balanced", random_state=SEED),
                                        n_estimators=80, learning_rate=0.6, random_state=SEED)
            cnt = np.bincount(yt, minlength=self.n).astype(float)
            self.m.fit(Xt, yt, sample_weight=(1 / np.maximum(cnt[yt], 1)) * len(yt) / self.n)
        else:
            self.m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=3000, class_weight="balanced"))
            self.m.fit(Xt, yt)
        return self

    def predict_proba(self, X):
        return expand_proba(self.m.predict_proba(X), self.m.classes_, self.n)


def variants():
    n = len(CODES)
    return {
        "Random Forest": lambda: Single("rf"),
        "AdaBoost": lambda: Single("ada"),
        "Logistic Regression": lambda: Single("lr"),
        "Stack RF>Ada>LR (balanced meta)": lambda: CascadeStack(n, use_smote=False, seed=SEED),
        "Stack RF>Ada>LR (prior-aware meta)": lambda: CascadeStack(n, use_smote=False, meta_balanced=False, seed=SEED),
        "Stack + SMOTE (prior-aware meta)": lambda: CascadeStack(n, use_smote=True, meta_balanced=False, seed=SEED),
        "Stack + ExtraTrees (prior-aware meta)": lambda: CascadeStack(n, use_smote=False, extras=("et",), meta_balanced=False, seed=SEED),
    }


class WithEng:
    """Adds engineered columns before delegating (so every variant sees identical inputs)."""
    def __init__(self, inner): self.inner = inner
    def fit(self, X, y, g): self.inner.fit(add_engineered(X), y, g); return self
    def predict_proba(self, X): return self.inner.predict_proba(add_engineered(X))


def score(y, P):
    pred = P.argmax(1)
    return {"accuracy": float(accuracy_score(y, pred)), "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
            "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0))}


def recording_level(y, P, g):
    """Average the unit-level probabilities of each recording (what the app does) and score per recording."""
    df = pd.DataFrame(P); df["g"] = g; df["y"] = y
    agg = df.groupby("g").agg({**{c: "mean" for c in range(P.shape[1])}, "y": "first"})
    Pm = agg[list(range(P.shape[1]))].to_numpy()
    return score(agg["y"].to_numpy(), Pm), len(agg)


def leaky_reference(X, y):
    """Plain shuffled k-fold that IGNORES recordings: shows how much accuracy leakage would fake."""
    from sklearn.model_selection import StratifiedKFold
    oof = np.zeros((len(y), len(CODES)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=SEED).split(X, y):
            oof[te] = WithEng(Single("rf")).fit(X[tr], y[tr], None).predict_proba(X[te])
    return score(y, oof)


def cross_validate(X, y, g, make, n_splits=5):
    oof = np.zeros((len(y), len(CODES)))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for tr, te in StratifiedGroupKFold(n_splits, shuffle=True, random_state=SEED).split(X, y, g):
            m = WithEng(make()).fit(X[tr], y[tr], g[tr])
            oof[te] = m.predict_proba(X[te])
    return oof


def class_profiles(d):
    prof = {"n_rows": int(len(d)), "classes": {}, "global": {}}
    for c in FEATURE_COLUMNS:
        prof["global"][c] = {"mean": float(d[c].mean()), "std": float(d[c].std() or 1.0),
                             "p1": float(d[c].quantile(.01)), "p99": float(d[c].quantile(.99))}
    for code in CODES:
        sub = d[d["Reason"] == code]
        p = {"n": int(len(sub)), "recordings": int(sub["Original_File"].nunique())}
        for c in FEATURE_COLUMNS:
            if len(sub) >= 3:
                p[c] = {"mean": float(sub[c].mean()), "std": float(sub[c].std() or 1e-6),
                        "p10": float(sub[c].quantile(.1)), "p90": float(sub[c].quantile(.9))}
        prof["classes"][code] = p
    return prof


def main(args):
    t0 = time.time()
    DROP.update(c for c in (args.drop or "").split(",") if c)
    tr_df, te_df = load(args.train), load(args.test)
    if te_df is None:
        sys.exit(f"Test CSV not found / empty: {args.test}")
    notes = []
    if tr_df is None:
        mode = "grouped_cv_on_test_csv"
        if DROP:
            notes.append(f"Label codes {sorted(DROP)} were excluded from training (not a real cause: parents did not know).")
        notes.append(f"Training CSV '{args.train}' is missing or empty, so the {len(te_df)} real rows of the test CSV "
                     "were evaluated with grouped 5-fold cross-validation (a recording never appears in both train and test).")
        full = te_df
        X, y, g = xy(full)
    else:
        mode = "train_csv_vs_test_csv"
        leak = set(tr_df["Original_File"]) & set(te_df["Original_File"])
        if leak:
            notes.append(f"WARNING: {len(leak)} recordings appear in BOTH train and test CSV - test metrics are optimistic (leakage).")
        full = pd.concat([tr_df, te_df], ignore_index=True)
        X, y, g = xy(full)
    print(f"mode={mode}  rows={len(full)}  recordings={full['Original_File'].nunique()}")
    print(full["Reason"].value_counts().to_string())

    results, oofs = {}, {}
    todo = variants()
    if args.quick:
        todo = {k: v for k, v in todo.items() if k in ("Random Forest", "AdaBoost", "Logistic Regression", "Stack + SMOTE (prior-aware meta)", "Stack RF>Ada>LR (balanced meta)")}
    for name, make in todo.items():
        t = time.time()
        if mode == "grouped_cv_on_test_csv":
            oof = cross_validate(X, y, g, make)
            ytrue = y
        else:
            Xtr, ytr, gtr = xy(tr_df); Xte, yte, _ = xy(te_df)
            m = WithEng(make()).fit(Xtr, ytr, gtr)
            oof, ytrue = m.predict_proba(Xte), yte
        results[name] = score(ytrue, oof); oofs[name] = (ytrue, oof)
        if mode == "grouped_cv_on_test_csv":
            results[name]["recording_level"], results[name]["n_recordings"] = recording_level(ytrue, oof, g)
        print(f"{name:32s} acc {results[name]['accuracy']:.3f} | bal-acc {results[name]['balanced_accuracy']:.3f} | "
              f"macro-F1 {results[name]['macro_f1']:.3f}  ({time.time() - t:.0f}s)")
    leaky = leaky_reference(X, y) if mode == "grouped_cv_on_test_csv" else None
    if leaky:
        print(f"[reference] RF with a LEAKY random split (recordings mixed): acc {leaky['accuracy']:.3f} macro-F1 {leaky['macro_f1']:.3f}")
    majority = float(np.bincount(oofs['Random Forest'][0]).max() / len(oofs['Random Forest'][0]))
    print(f"majority-class baseline accuracy: {majority:.3f}")

    stack_names = [k for k in results if k.startswith("Stack")]
    best = max(stack_names, key=lambda k: results[k]["macro_f1"])
    print(f"\nSelected for serving: {best}")
    ytrue, P = oofs[best]
    pred = P.argmax(1)
    present = sorted(set(ytrue) | set(pred))
    rep = classification_report(ytrue, pred, labels=list(range(len(CODES))), target_names=[LABELS[c] for c in CODES],
                                output_dict=True, zero_division=0)
    cm = confusion_matrix(ytrue, pred, labels=list(range(len(CODES)))).tolist()
    print(classification_report(ytrue, pred, labels=list(range(len(CODES))), target_names=[LABELS[c] for c in CODES], zero_division=0))

    # final model on ALL available rows
    final = WithEng(variants()[best]()).fit(X, y, g)
    inner = final.inner
    imp = np.mean([m.feature_importances_ for n, m in inner.base_.items() if n == "rf"], axis=0)
    from ml.stack import ENG_COLUMNS
    importances = sorted(zip(ENG_COLUMNS, imp.tolist()), key=lambda t: -t[1])
    out = {
        "model": inner, "codes": CODES, "labels": LABELS, "feature_columns": FEATURE_COLUMNS,
        "profiles": class_profiles(full), "trained_rows": int(len(full)),
    }
    joblib.dump(out, BASE / "model" / "stack.joblib", compress=3)
    metrics = {
        "model_name": best, "mode": mode, "notes": notes, "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_rows": int(len(full)), "n_recordings": int(full["Original_File"].nunique()),
        "class_counts": {LABELS[c]: int((full["Reason"] == c).sum()) for c in CODES},
        "class_recordings": {LABELS[c]: int(full.loc[full["Reason"] == c, "Original_File"].nunique()) for c in CODES},
        "majority_baseline_accuracy": majority,
        "comparison": results, "selected": results[best], "leaky_split_reference": leaky,
        "per_class": {k: v for k, v in rep.items() if k in [LABELS[c] for c in CODES]},
        "confusion_matrix": cm, "labels": [LABELS[c] for c in CODES],
        "stage_reliance": inner.meta_weights(), "stack_stages": inner.stage_names,
        "feature_importance": [{"feature": f, "importance": round(v, 4)} for f, v in importances[:12]],
        "seconds": round(time.time() - t0, 1),
    }
    (BASE / "model" / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nSaved model/stack.joblib and model/metrics.json in {metrics['seconds']}s")
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default=str(BASE / "dataset" / "balanced_full_dataset_clean.csv"))
    ap.add_argument("--test", default=str(BASE / "dataset" / "test_dataset_clean.csv"))
    ap.add_argument("--drop", default="", help="comma list of label codes to leave out, e.g. dk (don't-know = label noise)")
    ap.add_argument("--quick", action="store_true", help="compare fewer variants (faster)")
    main(ap.parse_args())
