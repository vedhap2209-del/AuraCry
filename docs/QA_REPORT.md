# AuraCry — Testing & Quality Assurance Report (Phase 17)

_Last run: all tests green on the current code._

## 1. Summary

| | |
|---|---|
| Automated tests | **60**, all passing |
| Test framework | `pytest` / `unittest` (run from `backend/`) |
| Headline model metric | **Fused ML+DL: 78.0% accuracy, macro-F1 0.61** |
| Web deployment model | ML-only (74.3% accuracy, macro-F1 0.56) on the free tier |
| Real training clips | 1,778 across 5 cry types, subject-wise split |

How to run them:

```bash
cd backend
python -m pytest tests/ -q        # or: python -m unittest discover -v
```

## 2. What the 60 tests cover

| Suite | Tests | What it checks |
|---|---|---|
| `test_auth.py` | 16 | Three-factor login (password → email code → PIN), registration, account lockout, CSRF protection, role rules, password/PIN reset, session only after all three factors |
| `test_backend.py` | 11 | Full analysis flow end-to-end, real pitch tracking (not canned values), file ownership (a user can't open another user's audio/report), admin stats & reports, **PDF report download**, invalid-audio rejection |
| `test_ml.py` | 8 | Feature extraction, the RF→AdaBoost→LR stack, probability outputs, class handling |
| `test_fusion.py` | 8 | ML+DL weighted-average fusion maths, weight bounds, label alignment |
| `test_dl_fusion.py` | 7 | DL branch wiring, graceful fallback to ML-only when torch/model is absent (a DL crash never breaks the ML answer) |
| `test_upload_validation.py` | 6 | Magic-byte sniffing, ffprobe container check, size/duration bounds, rejection of mislabelled files |
| `test_ratelimit.py` | 4 | Sliding-window rate limit, duplicate-submission guard, one-analysis-at-a-time guard |

A browser end-to-end script (`tests/e2e_browser.py`) is included for manual UI smoke testing.

## 3. Model accuracy (honest numbers)

Measured on a **subject-wise test split** — no baby appears in both training and test, so these numbers reflect performance on genuinely new recordings, not memorised ones.

| Model | Accuracy | Balanced acc | Macro-F1 |
|---|---|---|---|
| ML stack (RF→AdaBoost→LR) | 0.743 | 0.589 | 0.564 |
| DL (CNN+BiGRU-attention) | 0.750 | 0.627 | 0.604 |
| **Fused (ML+DL, deep weight 0.55)** | **0.780** | **0.631** | **0.614** |

**Why macro-F1 is the headline, not accuracy:** the data is imbalanced (far more "tired" and "hungry" clips than "discomfort" or "belly pain"). The *original* project scored 83% accuracy but macro-F1 0.17 — it reached that accuracy by answering "Hungry" for almost everything. The fused model scores a little lower on raw accuracy but actually recognises all five cry types.

Per-class F1 (fused/DL test set): Tired ~0.87, Hungry ~0.77, Discomfort/Belly-pain/Burping ~0.42–0.48. The three rare classes are weaker — expected given how few real examples exist — and the app says so in each result and marks low-confidence predictions as uncertain.

## 4. Dataset integrity

- 1,778 real clips from Donate-a-Cry + InfantCry-DBL (two tiers), unified to 5 classes.
- 901 clips excluded (silence, corruption, out-of-scope labels); 83 cross-source label conflicts quarantined.
- Near-duplicate detection merged clips by **subject** (union-find), so the same baby can't leak across the train/val/test split.
- Augmentation (997 extra clips) is **training-only** and capped per clip; val/test are real clips only.

## 5. Reliability & safety behaviour (verified)

- DL model or torch missing → app falls back to ML-only and says so; it never crashes.
- Low confidence or a small margin to the runner-up → result is marked "uncertain" and the UI shows a best-guess + checklist instead of a hard answer.
- Out-of-range acoustic values vs the training set → a drift notice is shown.
- Every result and every PDF report carries the medical disclaimer (Phase 18): experimental, not a diagnosis, see a doctor if worried.
- Uploads are validated by content (magic bytes + ffprobe), not just file extension.

## 6. Known limitations

- Rare cry types (discomfort, belly pain, burping) have limited real data and lower per-class F1.
- The free web deployment runs **ML-only** (the DL branch needs ~2 GB RAM). Accuracy there is 74% rather than the fused 78%.
- Free-tier hosting sleeps when idle (~40 s cold start) and does not persist the SQLite database across restarts.
- This is a study project, not a medical device.
