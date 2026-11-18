"""Phase 5: train the CNN+BiGRU-attention model on the unified dataset (manifest-driven).

Reads data/manifest.csv, uses its subject-wise splits (DBL Tier 1 is train-only). Trains on REAL train clips with
class-balanced sampling + on-the-fly augmentation (the pre-made augmented files are for the ML stack; the CNN augments
itself, so using them too would double-augment). Honest val/test are real clips only. Saves backend/model/cry_model.pt
and backend/model/dl_metrics.json.

    cd backend && python -m deep.train_unified --manifest ../data/manifest.csv --epochs 40
"""
import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix, f1_score
from torch.utils.data import DataLoader, WeightedRandomSampler

from . import config as C
from .audio_utils import load_audio_file, prepare_waveform
from .dataset import CryDataset
from .model import CryCNNGRUModel, DEFAULT_ARCH

torch.set_num_threads(max(1, torch.get_num_threads()))


def set_seed(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)


def read_manifest(path):
    root = Path(path).resolve().parent
    rows = [r for r in csv.DictReader(open(path, newline="")) if r["task"] == "cry_reason"]
    items = {"train": [], "val": [], "test": []}
    for r in rows:
        if r["split"] == "train" and int(r["is_augmented"]):     # DL augments on the fly; skip pre-made copies
            continue
        if r["label"] not in C.LABEL_ORDER:
            continue
        items[r["split"]].append((str(root / r["audio_path"]), C.LABEL_ORDER.index(r["label"])))
    return items


@torch.no_grad()
def predict(model, loader, device):
    model.eval(); P, Y = [], []
    for x, y in loader:
        P.append(torch.softmax(model(x.to(device)), 1).cpu().numpy()); Y.append(y.numpy())
    return np.concatenate(P), np.concatenate(Y)


def report(y, p, nC):
    return {"accuracy": round(float(accuracy_score(y, p.argmax(1))), 4),
            "balanced_accuracy": round(float(balanced_accuracy_score(y, p.argmax(1))), 4),
            "macro_f1": round(float(f1_score(y, p.argmax(1), labels=list(range(nC)), average="macro", zero_division=0)), 4),
            "per_class": classification_report(y, p.argmax(1), labels=list(range(nC)), target_names=C.CLASSES,
                                               output_dict=True, zero_division=0),
            "confusion_matrix": confusion_matrix(y, p.argmax(1), labels=list(range(nC))).tolist()}


def run(a):
    set_seed(a.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    nC = len(C.CLASSES)
    items = read_manifest(a.manifest)
    print({k: len(v) for k, v in items.items()}, "device:", device)

    def load_split(key):
        waves, labels = [], []
        for k, (path, lab) in enumerate(items[key]):
            try:
                w = prepare_waveform(load_audio_file(path))
            except Exception:
                continue
            waves.append(w); labels.append(lab)
            if (k + 1) % 300 == 0:
                print(f"  {key} {k+1}/{len(items[key])}", flush=True)
        return waves, np.array(labels)

    wtr, ytr = load_split("train"); wva, yva = load_split("val"); wte, yte = load_split("test")
    print("class counts (train):", {C.CLASSES[i]: int((ytr == i).sum()) for i in range(nC)})

    ds_tr = CryDataset(wtr, ytr, train=True); ds_va = CryDataset(wva, yva, False); ds_te = CryDataset(wte, yte, False)
    cls_counts = np.bincount(ytr, minlength=nC).astype(float)
    sw = 1.0 / np.maximum(cls_counts[ytr], 1.0)
    sampler = WeightedRandomSampler(sw, num_samples=len(ytr), replacement=True)
    dl_tr = DataLoader(ds_tr, batch_size=a.batch, sampler=sampler, num_workers=a.workers)
    dl_va = DataLoader(ds_va, batch_size=32); dl_te = DataLoader(ds_te, batch_size=32)

    arch = dict(DEFAULT_ARCH, num_classes=nC, n_mels=C.N_MELS)
    model = CryCNNGRUModel(**arch).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-2)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=a.epochs)
    # class-weighted loss on top of balanced sampling, so rare classes still count even within a balanced batch
    cw = torch.tensor((cls_counts.sum() / np.maximum(cls_counts, 1)) ** 0.5, dtype=torch.float32, device=device)
    cw = cw / cw.mean()
    loss_fn = nn.CrossEntropyLoss(weight=cw, label_smoothing=0.05)

    best_f1, best_state, bad, log = -1.0, None, 0, []
    for ep in range(1, a.epochs + 1):
        model.train(); rl = 0.0
        for x, y in dl_tr:
            x, y = x.to(device), y.to(device)
            opt.zero_grad(); loss = loss_fn(model(x), y); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step(); rl += loss.item() * len(y)
        sched.step()
        pv, yv = predict(model, dl_va, device); f1 = f1_score(yv, pv.argmax(1), average="macro", zero_division=0)
        log.append({"epoch": ep, "loss": round(rl / len(ds_tr), 4), "val_macro_f1": round(float(f1), 4),
                    "val_acc": round(float(accuracy_score(yv, pv.argmax(1))), 4)})
        print(f"epoch {ep:3d} | loss {rl/len(ds_tr):.3f} | val acc {accuracy_score(yv, pv.argmax(1)):.3f} | val macro-F1 {f1:.3f}", flush=True)
        if f1 > best_f1:
            best_f1, bad = f1, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= a.patience:
                print(f"early stop (no val gain for {a.patience} epochs)"); break

    model.load_state_dict(best_state)
    C.MODEL_DIR.mkdir(exist_ok=True)
    torch.save({"state_dict": best_state, "classes": C.CLASSES, "label_order": C.LABEL_ORDER, "arch": arch,
                "sr": C.SR, "duration": C.DURATION, "fmax": C.FMAX}, C.MODEL_DIR / "cry_model.pt")

    pv, yv = predict(model, dl_va, device); pt, yt = predict(model, dl_te, device)
    np.savez(C.MODEL_DIR / "dl_val_probs.npz", p=pv, y=yv)       # reused by Phase 6 fusion tuning
    metrics = {"task": "cry_reason", "classes": C.CLASSES, "arch": arch,
               "n_train": len(ytr), "n_val": len(yva), "n_test": len(yte),
               "class_counts_train": {C.CLASSES[i]: int((ytr == i).sum()) for i in range(nC)},
               "best_val_macro_f1": round(float(best_f1), 4),
               "val": report(yv, pv, nC), "test": report(yt, pt, nC), "history": log}
    (C.MODEL_DIR / "dl_metrics.json").write_text(json.dumps(metrics, indent=2))
    print("\n=== DL TEST (real clips) ===")
    print(classification_report(yt, pt.argmax(1), labels=list(range(nC)), target_names=C.CLASSES, zero_division=0))
    print("test:", metrics["test"]["accuracy"], "bal_acc", metrics["test"]["balanced_accuracy"], "macro-F1", metrics["test"]["macro_f1"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    run(ap.parse_args())
