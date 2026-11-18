# AuraCry dataset report (Phase 2)

Built by `backend/data_pipeline/build_dataset.py`. Outputs live in `data/` (audio is git-ignored; rebuild with the script).

```
cd backend && python -m data_pipeline.build_dataset \
    --dac ../data/sources/donateacry-corpus \
    --esc50 ../data/sources/ESC-50 \
    --dbl ../data/sources/InfantCry-DBL \
    --out ../data
```

| File | What it is |
|---|---|
| `data/manifest.csv` | Every recording used for the cry-reason task: source, licence, original + standard label, subject id, split, fold, audio path, hashes, augmentation flags |
| `data/excluded.csv` | Every source file **not** used, with the reason |
| `data/manifest_cry_detection.csv` | Separate cry vs not-cry task (ESC-50). Never mixed into the reason classifier |
| `data/class_distribution.csv` | Counts before and after balancing |
| `data/cross_source_conflicts.csv` | DBL clips that are the same audio as a Donate-a-Cry clip but labelled differently (dropped) |
| `data/build_info.json` | Classes, split seed, totals, duplicate stats |

## 1. Datasets used

| Dataset | Labels | Role | Licence | Status |
|---|---|---|---|---|
| **Donate-a-Cry** (gveres/donateacry-corpus) | 9 parent-tagged reasons | cry-reason | ODbL 1.0 / DbCL 1.0 | **Used** — 457 curated recordings (from 1,128 raw uploads) |
| **InfantCry-DBL** (Mendeley DOI 10.17632/x493z8nmwc.1) | 5 Dunstan sounds | cry-reason | CC BY 4.0 | **Used** — 1,321 clips after cleaning (Tier 1: 333, Tier 2: 988) |
| **ESC-50** (karolpiczak/ESC-50) | 50 env. classes incl. `crying_baby` | cry vs not-cry side task | CC BY-NC 3.0 | **Used** — 40 cry / 1,960 not-cry |

Considered and **not** merged: CryCeleb2023 (identity only, no reasons, gated NC-ND); Baby Chillanto (pathology task, restricted); Kaggle/HF "Donate a Cry" re-uploads (duplicates of the corpus already included). See §8.

## 2. One label set for both models

The old project had **9 ML classes and 5 DL classes** and mapped one onto the other. Both now use five classes in a fixed order (`backend/data_pipeline/labels.py`):

`hungry, tired, discomfort, belly_pain, burping`

| Standard | Donate-a-Cry tag | Dunstan (InfantCry-DBL) |
|---|---|---|
| hungry | hu | neh |
| tired | ti | owh |
| discomfort | dc, ch (merged, as the corpus curators did) | heh |
| belly_pain | bp | eairh (lower gas) |
| burping | bu | eh |
| *excluded* | lo, sc, dk | — |

**Label reliability, stated plainly:** Donate-a-Cry labels are a parent's guess at upload time. Dunstan labels are a commercial sound scheme; a 2023 study (Mathevon et al., *Communications Psychology*) could not show that cries reliably encode their cause. InfantCry-DBL reports strong annotator agreement (Cohen's κ = 0.89) but that measures whether two listeners agree on the *sound*, not whether the sound reflects the true cause. These are the best labels available, not ground truth, and the app says so.

## 3. Totals

| | Real recordings | Augmented (train only) | Excluded |
|---|---|---|---|
| cry-reason task | **1,778** | 997 | 901 |

930 distinct subjects. This is **~4× the real data** the old project trained on (457).

## 4. Cleaning and what was removed

| Reason excluded | Count |
|---|---|
| Donate-a-Cry uploads rejected by the KTH curators (non-cry, noise, adult imitation) | 437 |
| Donate-a-Cry labels not used (lonely / scared / don't-know) | 232 |
| Exact audio duplicates (same decoded PCM) | 197 |
| **DBL clips that are the same audio as a Donate-a-Cry clip but a different label** | 27 |
| DBL clips whose identical audio is labelled two different ways within DBL | 3 |
| Other (broken filenames, undecodable) | 5 |

### Finding: InfantCry-DBL Tier 2 contains relabelled Donate-a-Cry audio

27 DBL clips are acoustically identical (cosine ≥ 0.9 on a time-aligned log-mel, most ≈ 1.0) to a curated Donate-a-Cry recording **with a different label** — 26 of them are DBL `eh`/**burping** that is really Donate-a-Cry **hungry**. DBL lists these Tier 2 clips as coming from "online/volunteer/CryCeleb" sources, but they are re-encoded Donate-a-Cry uploads. They are listed in `cross_source_conflicts.csv` and dropped; Donate-a-Cry's curated label is kept. This is why the **burping** class should be treated with the most caution of the five.

### Near-duplicate clustering (leakage prevention)

Beyond exact duplicates, many clips are re-encodes or overlapping segments of one recording (DBL Tier 1 studio clips reappear in Tier 2; Donate-a-Cry re-uploads). The builder fingerprints every clip (4 kHz band-limited log-mel, mean+std), links pairs above cosine 0.995, and **unions their whole subject groups** so every near-duplicate shares one subject id: 1,458 pairs → 128 clusters. Without this, the same cry could sit in both train and test.

### Recording-device bias

Donate-a-Cry Android clips are AMR 8 kHz (nothing above 4 kHz); iOS and most DBL clips are 16 kHz+. Classes are not evenly spread across devices, so a model could learn "which device" instead of "which cry". **Phase 3 band-limits every clip to 4 kHz** for both training and inference.

## 5. Splits (subject-wise, no leakage)

* **Subject** = Donate-a-Cry app install (`dac:<uuid>`) or DBL Tier 2 infant id (`dbl:<id>`), after near-duplicate union. A subject is a proxy, not a guaranteed single baby, but it is the strongest grouping the data allows.
* `StratifiedGroupKFold(5)`, seed 42: fold 0 = **test**, fold 1 = **validation**, folds 2–4 = **train**. `cv_fold` also supports full grouped 5-fold CV.
* **DBL Tier 1 (studio instructional-video clips) is train-only** — it has no infant identity and is acoustically unlike real home recordings, so it must never inflate a validation/test score (`cv_fold = -1`).
* Verified on the final build: **0 subjects in more than one split**, **0 augmented clips outside train**, **0 Tier-1 clips in val/test**.

Real recordings per source and split:

| source | test | train | val | total |
|---|---|---|---|---|
| donateacry | 63 | 322 | 72 | 457 |
| infantcry_dbl_t1 | 0 | 333 | 0 | 333 |
| infantcry_dbl_t2 | 157 | 683 | 148 | 988 |
| **all** | **220** | **1,338** | **220** | **1,778** |

## 6. Class distribution: before and after balancing

| label | real | subjects | train (real) | val | test | train after augmentation |
|---|---|---|---|---|---|---|
| hungry | 567 | 255 | 423 | 72 | 72 | 467 |
| tired | 678 | 484 | 467 | 106 | 105 | 467 |
| discomfort | 155 | 81 | 133 | 11 | 11 | 467 |
| belly_pain | 166 | 82 | 137 | 14 | 15 | 467 |
| burping | 212 | 104 | 178 | 17 | 17 | 467 |

* Balancing touches **train only**. Validation and test stay real and unbalanced.
* Every test class now has **11–105 real recordings** (was 2–77). Per-class metrics are meaningful now, though discomfort/belly_pain/burping test counts (11–17) are still small — treat single-point swings with care.
* Augmentation: pitch ±1/±2 semitones, time-stretch 0.9/0.95/1.1, noise at 15/20 dB SNR, −6 dB gain. **Capped at 8 copies per real clip**; the rest of the imbalance is handled by class weights at training time. Augmented clips are flagged `is_synthetic=1, is_augmented=1` with `parent_id` and never used for validation/test.
* The old `balanced_full_dataset_clean.csv` (84% synthetic rows) is not used.

## 7. Limits (read before quoting accuracy)

* The class balance is far better than before, so **"always hungry" no longer scores ~85%** — hungry is now 32% of real data. Headline metrics stay **macro-F1 and balanced accuracy**, with plain accuracy beside them.
* DBL Tier 1 is studio audio from a few instructional videos; it is train-only, but models can still over-rely on it. Phase 4–5 will report Donate-a-Cry-only and DBL-only test scores **separately** as well as combined, so a clean-studio score can't hide weak real-world performance.
* Labels remain parent/annotator judgements of the sound, not verified causes (§2). The app presents results as experimental and shows an "Unclear" state on low confidence.
* `burping` carries the known contamination issue (§4) and the fewest subjects — expect it to be the weakest class.

## 8. Datasets considered but not merged

| Dataset | Why not |
|---|---|
| CryCeleb2023 (Ubenwa) | Labels are infant identity, not cry reason. Gated, CC BY-NC-ND. Usable only for a cry-detection/pre-training side task |
| Baby Chillanto | Pathology labels (asphyxia/deaf/pain); "pain" ≠ "belly pain". Restricted access |
| Kaggle / HF "Donate a Cry" uploads | Re-uploads of the corpus already included — would duplicate and leak |
| Dunstan Baby Language DVD | Commercial/copyrighted |
| AxonData infant-cry-detection (HF) | 50 h, but **no cry-reason labels** ("Not in this release"). Detection only |

## Sources

* Donate-a-Cry corpus — https://github.com/gveres/donateacry-corpus
* InfantCry-DBL — https://data.mendeley.com/datasets/x493z8nmwc/1
* ESC-50 — https://github.com/karolpiczak/ESC-50
* CryCeleb2023 — https://huggingface.co/datasets/Ubenwa/CryCeleb2023
* ICSD paper (describes Baby Chillanto) — https://arxiv.org/abs/2408.10561
* Mathevon et al. 2023, *Communications Psychology* — https://www.nature.com/articles/s44271-023-00022-z
