# AuraCry Unified

Baby-cry analysis web app. One login page, separate USER / ADMIN interfaces (roles enforced on the server), pastel baby-mascot design,
real audio analysis through **Random Forest → AdaBoost → Logistic Regression**, explanations, soothing suggestions (Gemini / YouTube APIs optional)
and a **Pipeline Lab** that shows what each stage really computes.

## Run (Windows: `run.bat`, Mac/Linux: `./run.sh`, or by hand)
```
pip install -r backend/requirements.txt
python run.py                 # creates backend/.env + first admin (admin@auracry.local / Admin12345), opens http://127.0.0.1:5000
```
No Node/npm needed: the frontend is a no-build ES-module app served by Flask. Python 3.10+.

## Screens
User: Login · Register · Home · Choose Audio · Record · Audio Ready · Processing (replays the real server trace) · Result · History · Details · **Pipeline Lab** · Profile.
Admin: Dashboard · Users · User Details · Dataset (CSV status/upload) · Model Performance (+ train button, model comparison) · Confusion Matrix · Records · Record Details · Reports · **Pipeline Lab** · Profile.

## How an analysis works (all real computation, timed in the Processing/Lab views)
audio → mono 16 kHz → **cry units** (voiced bursts) → **19 features per unit** (Duration, Min/Max/Mean/Std F0, HNR, 13 MFCC; same columns as your CSV)
→ **Stage 1 Random Forest** → **Stage 2 AdaBoost** → **Stage 3 Logistic Regression** (learns from out-of-fold stage outputs) → average over units → reliability gate
("Unclear" if confidence < 40 % or margin < 6 pts) → explanation (feature vs. class profile) → advice.
Improvements added beyond plain RF: SMOTE inside training folds, class weights, engineered pitch-ratio features, out-of-fold stacking, grouped (per-recording) validation, uncertainty gate, feature-drift warning.

## Honest results (read before trusting any number)
Trained on `test_dataset_clean.csv` only: your `balanced_full_dataset_clean.csv` arrived **empty (0 bytes)**. 931 rows = 142 recordings; rare cry types come from 2–4 recordings.
Grouped 5-fold CV (a recording never in both train and test), `dk` ("don't know") excluded → 756 rows / 115 recordings:

| model | accuracy | macro-F1 |
|---|---|---|
| always answer "Hungry" | 86.0 % | ~0.09 |
| Random Forest | 83.6 % | 0.125 |
| AdaBoost | 77.0 % | 0.150 |
| Logistic Regression | 55.2 % | 0.113 |
| **Stack RF→Ada→LR (served)** | 85.6 % | 0.115 |

Verdict: with these 19 features and this few recordings, **no model beats the "always Hungry" baseline on new recordings**; rare cry types are not learned.
A leaky random split (rows of one recording in train and test) shows macro-F1 0.54: that inflated number is recording leakage, not skill.
The app therefore shows per-class reliability and an "Unclear" state, and labels itself an experimental study tool. What would truly help: more recordings per rare class, and the real balanced file + original audio (see HANDOFF.md).

## Tests (all pass in the build sandbox)
```
cd backend
python -m unittest discover -s tests -t . -v      # 19 tests: access control, real audio pipeline, ML correctness
pip install playwright && playwright install chromium
python -m tests.e2e_browser                       # 37 real-browser checks of the whole UI
```
Not verifiable in the sandbox: the optional CNN+BiGRU (`backend/deep`, needs torch), Gemini/YouTube calls (need keys + internet), and live microphone with a real device.

## Suggestion APIs (optional, backend/.env)
`GEMINI_API_KEY` personalises the steps from measured evidence (validated; falls back to built-in safe guidance). `YOUTUBE_API_KEY` embeds vetted-search videos; otherwise search links. Safety/red-flag text always comes from the built-in knowledge base.

## Retrain
Admin → Model Performance → Train (or `cd backend && python -m ml.tabular_train --train dataset/balanced_full_dataset_clean.csv --test dataset/test_dataset_clean.csv`).
With a non-empty train CSV it trains on that file and evaluates on the test CSV (warns about shared recordings); otherwise uses grouped CV on the test CSV.


## Three requested enhancements
See [docs/THREE_ENHANCEMENTS_SETUP.md](docs/THREE_ENHANCEMENTS_SETUP.md) for Gmail SMTP setup, Admin Model Performance metrics, and the optional experimental multi-baby source-separation branch.

## Latest UI and AI enhancements
- Original login and upload/record screens are preserved, including the cursor-following baby mascot, existing background, language selector and theme controls.
- User-facing Pipeline Lab is removed from navigation; the admin lab remains.
- Added AuraCry AI chat on Home and a full AI Companion page. Gemini responses are optional via `GEMINI_API_KEY`; safe built-in guidance works without a key.
- Added a private Baby Memory Diary. The assistant suggests milestone entries and asks the parent to confirm before saving the date and memory.
- Added subtle cry-category result animations and an AI help link from analysis results.
- Retained the optional experimental two-source separation module. See `docs/ENHANCEMENTS_SETUP.md`.

### Admin email OTP
The default admin remains `admin@auracry.local` / `Admin12345`. That `.local` address cannot receive email. To receive admin OTP at a real inbox, set `ADMIN_EMAIL=your-real-email@gmail.com` in `backend/.env`; the next start updates only the default admin email and preserves its password/PIN hashes. Configure SMTP in the same file.
