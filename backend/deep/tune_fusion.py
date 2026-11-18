"""Find the ML-vs-deep-learning fusion weight that scores best, and measure the result honestly.

Usage (from backend/, after the CNN is trained):
    python -m deep.tune_fusion --data_dir <folder with labelled audio>  [--objective macro_f1|balanced_accuracy|accuracy]

(It also runs automatically at the end of  python -m deep.train .)

What it does
  1. Splits the clips with the SAME grouped split the CNN was trained with (same --seed), so the CNN has never seen the
     validation or test clips.
  2. Sends every validation / test clip through the REAL app pipeline: the classical ML stack AND the CNN+BiGRU.
  3. Tries weights 0.00 ... 1.00 (step 0.05) on the VALIDATION clips and keeps the one with the best score
     (curve smoothed over neighbouring weights, so one lucky spike cannot win).
  4. Scores ML-only, CNN-only, fused@0.5 and fused@tuned ONCE on the untouched TEST clips - those are the numbers to trust.
  5. Writes model/fusion_config.json (the weight the app then uses) and model/fusion_metrics.json (what the admin page shows).

Honest limits
  * Use clips the ML stack was NOT trained on. If these recordings are also rows of the stack's training CSV, the ML branch
    looks better than it really is and the tuned weight will lean too far toward ML.
  * 'accuracy' alone is a poor target when one class dominates (always answering 'Hungry' already scores ~86 %), so the
    default objective is macro-F1; all three numbers are always reported.
  * With only a few dozen validation clips the best weight is an estimate, not a fact. Re-run it when you add data.
"""
import argparse
import json
import os
import sys

import numpy as np

from . import config as C
from .data_index import discover_files, make_splits
from ml import fusion

DEEP_CLASS_TO_CODE = {"Hungry": "hu", "Sleepy": "ti", "Fussy": "dc", "Burp": "bu", "Distress": "bp"}


def _default_pipeline():
    """The real app pipeline (ML stack + CNN). Advice network calls are switched off - they are irrelevant here."""
    from ml import advice as advice_mod
    from ml import deep_service
    from ml.service import service
    if not service.load():
        raise SystemExit(f"The ML model is not available: {service.error}")
    deep_service.reset()
    if not deep_service.available():
        raise SystemExit(f"The deep model is not available: {deep_service.status().get('reason')}")
    advice_mod.get_advice = lambda *a, **k: {"source": "off", "videos": [], "steps": []}
    return service.analyze_file, list(service.codes), dict(service.labels)


def to_record(res, codes, labels):
    """One analysis result -> (ML probability vector over `codes`, {code: CNN probability}); None if the CNN did not answer."""
    d = res.get("deep") or {}
    if d.get("status") != "ok":
        return None
    by_label = {labels[c]: c for c in codes}
    ml = np.array([res["ml"]["probabilities"][labels[c]] for c in codes], float)
    dl = {by_label[l]: float(p) for l, p in d["probabilities"].items()}
    return ml, dl


def collect(items, idx, analyze, codes, labels, quiet=False):
    ml_rows, dl_rows, y, skipped = [], [], [], []
    for n, i in enumerate(idx):
        it = items[i]
        code = DEEP_CLASS_TO_CODE[C.CLASSES[it.label]]
        try:
            rec = to_record(analyze(it.path), codes, labels)
        except Exception as e:                           # noqa - e.g. "no clear cry in this recording"
            skipped.append({"file": os.path.basename(it.path), "why": f"{type(e).__name__}: {e}"[:140]})
            continue
        if rec is None:
            skipped.append({"file": os.path.basename(it.path), "why": "the CNN gave no answer"})
            continue
        ml_rows.append(rec[0]); dl_rows.append(rec[1]); y.append(codes.index(code))
        if not quiet and (n + 1) % 25 == 0:
            print(f"  {n + 1}/{len(idx)}")
    return (np.array(ml_rows) if ml_rows else np.zeros((0, len(codes)))), dl_rows, np.array(y, int), skipped


def deep_only_pred(dl_rows, codes):
    return np.array([codes.index(max(d, key=d.get)) for d in dl_rows], int)


def run(data_dir, seed=42, objective="macro_f1", step=0.05, analyze=None, codes=None, labels=None, quiet=False):
    say = (lambda *a: None) if quiet else print
    if analyze is None:
        analyze, codes, labels = _default_pipeline()
    items, _ = discover_files(data_dir)
    if not items:
        raise SystemExit(f"No labelled audio found under {data_dir!r}.")
    _, va_idx, te_idx = make_splits(items, seed)
    say(f"Validation clips (used to choose the weight): {len(va_idx)}   test clips (used once, to report): {len(te_idx)}")
    if len(va_idx) < 30:
        say("WARNING: fewer than 30 validation clips - the chosen weight is a rough estimate.")
    say("Running validation clips through ML + CNN ...")
    mv, dv, yv, skip_v = collect(items, va_idx, analyze, codes, labels, quiet)
    if len(yv) == 0:
        raise SystemExit("No validation clip could be analysed by both branches.")
    grid = np.arange(0.0, 1.0001, step)
    t = fusion.tune_weight(mv, dv, yv, codes, objective, grid)
    w = t["weight"]
    say(f"Best deep weight on validation: {w:.2f}  ({objective} {t['scores'][objective]:.3f}; ML-only {t['ml_only'][objective]:.3f})")

    say("Running test clips through ML + CNN ...")
    mt, dt, yt, skip_t = collect(items, te_idx, analyze, codes, labels, quiet)
    if len(yt) == 0:
        raise SystemExit("No test clip could be analysed by both branches.")
    pt = fusion.project_all(mt, codes, dt)
    test = {"ml_only": fusion.scores(yt, fusion.predictions_at(mt, pt, 0.0)),
            "deep_only": fusion.scores(yt, deep_only_pred(dt, codes)),
            "fused_at_0.5": fusion.scores(yt, fusion.predictions_at(mt, pt, 0.5)),
            "fused_tuned": fusion.scores(yt, fusion.predictions_at(mt, pt, w))}
    metrics = {"objective": objective, "dl_weight": w, "n_tune": int(len(yv)), "n_test": int(len(yt)),
               "skipped_validation": skip_v[:20], "skipped_test": skip_t[:20],
               "tune_curve": {"weights": t["grid"], "scores": t["curve"], "smoothed": t["smoothed_curve"]},
               "test": test,
               "fused_beats_ml_on_test": test["fused_tuned"][objective] > test["ml_only"][objective] + 1e-9,
               "fused_beats_deep_on_test": test["fused_tuned"][objective] > test["deep_only"][objective] + 1e-9,
               "caveat": "Weights were tuned on validation clips; the test numbers above were never used for tuning. "
                         "ML numbers are only honest if these clips are not in the ML stack's training CSV."}
    fusion.save_config(w, objective, len(yv), t["scores"], {"n_test": int(len(yt))})
    fusion.METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    say("\n=== TEST CLIPS (never used for tuning) ===")
    say(f"{'':16s}{'accuracy':>10s}{'bal-acc':>10s}{'macro-F1':>10s}")
    for k, v in test.items():
        say(f"{k:16s}{v['accuracy']:10.3f}{v['balanced_accuracy']:10.3f}{v['macro_f1']:10.3f}")
    if not metrics["fused_beats_ml_on_test"]:
        say("NOTE: the tuned fusion did not beat ML-only on the test clips - the CNN is not adding value yet (more data needed).")
    if not metrics["fused_beats_deep_on_test"]:
        say("NOTE: the tuned fusion did not beat CNN-only on the test clips.")
    say(f"\nSaved {fusion.CONFIG_PATH.name} (the app now uses weight {w:.2f}) and {fusion.METRICS_PATH.name}.")
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_dir", required=True)
    ap.add_argument("--seed", type=int, default=42, help="use the same seed as deep.train")
    ap.add_argument("--objective", choices=fusion.OBJECTIVES, default="macro_f1")
    ap.add_argument("--step", type=float, default=0.05)
    a = ap.parse_args()
    run(a.data_dir, a.seed, a.objective, a.step)
