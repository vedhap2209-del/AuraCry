# AuraCry model report (Phases 3–6)

All numbers are on the **held-out test set** (220 real recordings, no augmentation, subject-wise split so no baby appears
in both train and test). Headline metric is **macro-F1** (averages all five classes equally) with accuracy and balanced
accuracy beside it, because accuracy alone is misleading on imbalanced cry data.

Reproduce:
```
cd backend
python -m data_pipeline.featurize_ml --manifest ../data/manifest.csv --out ../data/features_ml.npz   # Phase 3
python -m ml.train_unified   --features ../data/features_ml.npz                                       # Phase 4
python -m deep.train_unified --manifest ../data/manifest.csv --epochs 40                              # Phase 5
python -m ml.fuse_eval       --manifest ../data/manifest.csv --features ../data/features_ml.npz       # Phase 6
```

## Headline

| Model | Accuracy | Balanced acc | Macro-F1 |
|---|---|---|---|
| Majority baseline ("always Hungry") | 0.33 | 0.20 | 0.10 |
| ML stack (RF→AdaBoost→LR) | 0.743 | 0.589 | 0.565 |
| DL (CNN+BiGRU-attention) | 0.750 | 0.627 | 0.604 |
| **Fused (ML+DL, deep weight 0.55)** | **0.780** | **0.631** | **0.614** |

For comparison, the **original project** scored accuracy 0.83 / macro-F1 0.17 — i.e. it hit the accuracy target only by
answering "Hungry" for almost everything. The new fused model reaches 78% accuracy **while actually recognising the
cry types** (every class F1 ≥ 0.35), and the majority baseline it beats is now 33%, not 85%.

## Fused per-class (test)

| Class | Precision | Recall | F1 | Test recordings |
|---|---|---|---|---|
| Hungry | 0.85 | 0.77 | 0.81 | 71 |
| Tired | 0.91 | 0.89 | 0.90 | 104 |
| Discomfort | 0.33 | 0.36 | 0.35 | 11 |
| Belly Pain | 0.44 | 0.53 | 0.48 | 15 |
| Needs Burping | 0.48 | 0.59 | 0.53 | 17 |

Tired and Hungry are strong. The three rare classes are recognised but noisy — each has only 11–17 test recordings, so one
clip moves its F1 by several points. Burping is weakest (fewest subjects, and the contamination issue from Phase 2).

## Phase 3 — preprocessing (consistent train ↔ serve)

* **Device-bias guard:** every clip is low-pass filtered to 4 kHz before features (ML) and the DL log-mel uses `fmax=4000`.
  Donate-a-Cry Android clips are 8 kHz; without this the model could tell classes apart by recording device.
* **ML:** 19 acoustic features per *cry unit* (Duration, F0 min/max/mean/std, HNR, 13 MFCC), exactly as the app extracts
  them at inference — the app predicts per unit and averages, and training uses the same per-unit rows.
* **DL:** 128-band log-mel of the loudest 3-second window(s), standardised per clip.
* 6,348 ML units from 2,775 clips (29 clips had no detectable unit and were dropped).

## Phase 4 — ML stack

RF → AdaBoost → Logistic-Regression meta-learner, class weights + fold-internal SMOTE, grouped inner CV. Model comparison
at the recording level (test):

| | Accuracy | Macro-F1 |
|---|---|---|
| Random Forest | 0.766 | 0.596 |
| AdaBoost | 0.606 | 0.481 |
| Logistic Regression | 0.647 | 0.437 |
| Stack (served) | 0.743 | 0.565 |

Second estimate — **grouped 5-fold CV on real clips: macro-F1 0.60 ± 0.08**. A leaky unit-level random split scores 0.60
too, so with the bigger, more diverse dataset there is now little leakage headroom to inflate (unlike the old data, where
leaky was 0.54 vs honest 0.12).

## Phase 5 — DL model (CNN + BiGRU + attention)

Trained on real train clips with class-balanced sampling, class-weighted loss, on-the-fly augmentation (crop/noise/pitch/
stretch + SpecAugment), early stopping on validation macro-F1. DBL Tier-1 studio clips are train-only. Best val macro-F1
0.55 at epoch 25; **test accuracy 0.75, macro-F1 0.60**. The CNN is notably better than the ML stack on Discomfort
(F1 0.48 vs 0.22), which is why fusing them helps.

## Phase 6 — fusion

Both models now output the **same five classes in the same order**, so fusion is a plain weighted average:
`fused = (1−w)·ML + w·DL`. The weight `w` is tuned **on the validation split only** (never test); best `w = 0.55`
(55% DL / 45% ML). On test the fused model beats both branches:

| | Accuracy | Macro-F1 |
|---|---|---|
| ML only | 0.743 | 0.565 |
| DL only | 0.748 | 0.603 |
| **Fused (w=0.55)** | **0.780** | **0.614** |

Both branches genuinely run on the same audio in the served app (`backend/ml/service.py`): the result carries an `ml`
block, a `deep` block (with per-window attention), and a `fusion` block, and the trace shows `rf → ada → meta → dl_net →
fusion`. If the DL model or torch is missing, the app falls back to ML-only and says so; a DL crash never breaks the ML
answer. The tuned weight is stored in `model/fusion.json` and applied at serve time.

## Honesty notes

* Accuracy (78%) meets the 70–90% goal, but macro-F1 (0.61) is the number that shows the model recognises cry types
  rather than guessing the majority class. Both are reported in the app.
* Rare-class scores rest on 11–17 test recordings each; treat per-class numbers as indicative, not precise.
* Labels are parent/annotator judgements of the sound, not verified causes (see DATASET_REPORT.md §2). The app presents
  every result as experimental, shows an "Unclear" state on low confidence, and is not a medical device.
