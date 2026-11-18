"""Train the CNN+BiGRU model AND the acoustic-feature Random Forest, then fuse them.

Usage (from the project root):
    python -m src.train --data_dir data/donateacry_corpus_cleaned_and_updated_data

Outputs in models/:
    cry_model.pt         CNN+GRU weights
    rf.joblib            Random Forest on acoustic features
    fusion.json          best weighting of the two models (tuned on validation data)
    class_profiles.json  per-class feature statistics (used for the "why" explanations)
    metrics.json         honest TEST-set results (never used for tuning)
"""
import argparse
import json
import random
from collections import Counter

import joblib
import numpy as np
import torch
import torch.nn as nn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import make_pipeline
from torch.utils.data import DataLoader, WeightedRandomSampler

from . import config as C
from .audio_utils import NAMED_FEATURES, analyze_acoustics, load_audio_file, prepare_waveform
from .data_index import discover_files, make_splits
from .dataset import CryDataset
from .model import CryCNNGRUModel, DEFAULT_ARCH
from .stats import build_class_profiles, expand_proba, tune_fusion


def set_seed(s):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)


@torch.no_grad()
def predict_probs(model, loader, device):
    model.eval()
    probs, ys = [], []
    for x, y in loader:
        probs.append(torch.softmax(model(x.to(device)), dim=1).cpu().numpy())
        ys.append(y.numpy())
    return np.concatenate(probs), np.concatenate(ys)


def macro_f1(y, p):
    return f1_score(y, p.argmax(1), average="macro", zero_division=0)


def report(name, y, p, n_cls):
    labels = list(range(n_cls))
    return {
        "accuracy": float(accuracy_score(y, p.argmax(1))),
        "macro_f1": float(macro_f1(y, p)),
        "per_class": classification_report(y, p.argmax(1), labels=labels, target_names=C.CLASSES,
                                           output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(y, p.argmax(1), labels=labels).tolist(),
    }


def run(args):
    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_cls = len(C.CLASSES)

    # 1) data -----------------------------------------------------------------
    items, skipped = discover_files(args.data_dir)
    if not items:
        raise SystemExit(f"No labelled audio found under {args.data_dir!r}. See README for the dataset layout.")
    counts = Counter(it.label for it in items)
    print(f"Found {len(items)} clips ({skipped} skipped, no label):")
    for i, name in enumerate(C.CLASSES):
        print(f"  {name:9s} {counts.get(i, 0):4d}")
    if min(counts.get(i, 0) for i in range(n_cls)) < 10:
        print("WARNING: a class has <10 clips - its accuracy will be unreliable. Add more data.")

    tr_idx, va_idx, te_idx = make_splits(items, args.seed)
    print(f"Split (grouped by household/device): train={len(tr_idx)} val={len(va_idx)} test={len(te_idx)}")

    print("Loading audio once into memory ...")
    waves = []
    for k, it in enumerate(items):
        waves.append(prepare_waveform(load_audio_file(it.path)))
        if (k + 1) % 100 == 0:
            print(f"  {k + 1}/{len(items)}")
    labels = np.array([it.label for it in items])

    def subset(idx, train):
        return CryDataset([waves[i] for i in idx], labels[idx], train=train)

    ds_tr, ds_va, ds_te = subset(tr_idx, True), subset(va_idx, False), subset(te_idx, False)

    # class-balanced sampling (the corpus is heavily dominated by 'hungry')
    cls_counts = np.bincount(labels[tr_idx], minlength=n_cls).astype(float)
    sample_w = 1.0 / np.maximum(cls_counts[labels[tr_idx]], 1.0)
    sampler = WeightedRandomSampler(sample_w, num_samples=len(tr_idx), replacement=True)
    dl_tr = DataLoader(ds_tr, batch_size=args.batch, sampler=sampler, num_workers=args.workers)
    dl_va = DataLoader(ds_va, batch_size=32, num_workers=0)
    dl_te = DataLoader(ds_te, batch_size=32, num_workers=0)

    # 2) deep model -----------------------------------------------------------
    arch = dict(DEFAULT_ARCH, num_classes=n_cls, n_mels=C.N_MELS)
    model = CryCNNGRUModel(**arch).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-2)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)

    best_f1, best_state, bad = -1.0, None, 0
    for ep in range(1, args.epochs + 1):
        model.train()
        run_loss = 0.0
        for x, y in dl_tr:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            run_loss += loss.item() * len(y)
        sched.step()
        p_va, y_va = predict_probs(model, dl_va, device)
        f1 = macro_f1(y_va, p_va)
        print(f"epoch {ep:3d} | loss {run_loss / len(ds_tr):.3f} | val acc {accuracy_score(y_va, p_va.argmax(1)):.3f} | val macro-F1 {f1:.3f}")
        if f1 > best_f1:
            best_f1, bad = f1, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= args.patience:
                print(f"Early stopping (no val improvement for {args.patience} epochs).")
                break

    model.load_state_dict(best_state)
    C.MODEL_DIR.mkdir(exist_ok=True)
    torch.save({"state_dict": best_state, "classes": C.CLASSES, "arch": arch,
                "sr": C.SR, "duration": C.DURATION}, C.MODEL_DIR / "cry_model.pt")

    # 3) acoustic-feature Random Forest ---------------------------------------
    print("Extracting acoustic features for the Random Forest ...")

    def feats(idx):
        out = []
        for k, i in enumerate(idx):
            out.append(analyze_acoustics(CryDataset([waves[i]], [0]).best_wave(0)))
            if (k + 1) % 100 == 0:
                print(f"  {k + 1}/{len(idx)}")
        return out

    f_tr, f_va, f_te = feats(tr_idx), feats(va_idx), feats(te_idx)
    X = lambda fl: np.stack([f["vector"] for f in fl])
    rf = make_pipeline(
        SimpleImputer(strategy="median"),
        RandomForestClassifier(n_estimators=500, min_samples_leaf=2, class_weight="balanced_subsample",
                               n_jobs=-1, random_state=args.seed))
    rf.fit(X(f_tr), labels[tr_idx])
    joblib.dump({"pipeline": rf, "feature_names": f_tr[0]["names"]}, C.MODEL_DIR / "rf.joblib")
    rf_classes = rf[-1].classes_

    # 4) fuse + honest test evaluation -----------------------------------------
    p_va_dl, y_va = predict_probs(model, dl_va, device)
    p_te_dl, y_te = predict_probs(model, dl_te, device)
    p_va_rf = expand_proba(rf.predict_proba(X(f_va)), rf_classes, n_cls)
    p_te_rf = expand_proba(rf.predict_proba(X(f_te)), rf_classes, n_cls)
    w, val_f1 = tune_fusion(p_va_dl, p_va_rf, y_va)
    p_te_fused = w * p_te_dl + (1 - w) * p_te_rf
    (C.MODEL_DIR / "fusion.json").write_text(json.dumps({"dl_weight": w, "val_macro_f1": val_f1}, indent=2))

    metrics = {
        "n_train": int(len(tr_idx)), "n_val": int(len(va_idx)), "n_test": int(len(te_idx)),
        "class_counts": {C.CLASSES[i]: int(counts.get(i, 0)) for i in range(n_cls)},
        "dl_weight": w,
        "test": {"cnn_gru": report("cnn_gru", y_te, p_te_dl, n_cls),
                 "random_forest": report("rf", y_te, p_te_rf, n_cls),
                 "fused": report("fused", y_te, p_te_fused, n_cls)},
    }
    (C.MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

    # 5) class profiles for explanations (train split only) ---------------------
    profiles = build_class_profiles([f["features"] for f in f_tr], labels[tr_idx], C.CLASSES, NAMED_FEATURES)
    (C.MODEL_DIR / "class_profiles.json").write_text(json.dumps(profiles, indent=2))

    print("\n=== TEST SET (never used for tuning) ===")
    for k, name in [("cnn_gru", "CNN+GRU only"), ("random_forest", "Random Forest only"), ("fused", f"Fused (DL weight {w})")]:
        r = metrics["test"][k]
        print(f"{name:26s} accuracy {r['accuracy']:.3f} | macro-F1 {r['macro_f1']:.3f}")
    print("\nPer-class (fused):")
    print(classification_report(y_te, p_te_fused.argmax(1), labels=list(range(n_cls)),
                                target_names=C.CLASSES, zero_division=0))
    print("Confusion matrix (rows = true, cols = predicted):")
    print(np.array(metrics["test"]["fused"]["confusion_matrix"]))
    print(f"\nSaved everything to {C.MODEL_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_dir", required=True)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=15)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    run(ap.parse_args())
