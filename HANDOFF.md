# AuraCry Unified - HANDOFF (paste this whole file into the next chatbot)

## 0. What the user wants (original brief, condensed)
One single zip combining:
* `auracry__1_.zip`  -> **application architecture**: one common login page, USER and ADMIN interfaces, role checks on the
  server, pages: Login, Register, Home, Choose Audio, Record, Audio Ready, Processing, Result, History, Profile;
  Admin: Dashboard, Users, User Details, Dataset, Model Performance, Confusion Matrix, Records, Reports, Profile. Flask backend.
* `infant_cry_auracry.zip` (infant_cry_pro) -> **graphics, colours, animations** (pastel gradient, baby mascot orb, glass cards,
  Nunito font, shine buttons, dark mode, EN/HI/TE), plus its **suggestion APIs** (Gemini advice, YouTube videos, lullaby rules),
  explainability, Random Forest, CNN+BiGRU deep model.
* `test_dataset_clean.csv` (931 real rows) and `balanced_full_dataset_clean.csv` (**arrived as a 0-byte file**, so it was never used).
* Classical ML path must run **Random Forest -> AdaBoost -> Logistic Regression**, and use any better method that really raises accuracy.
* A **demo that shows what is actually happening** (real stage-by-stage outputs, not dummy UI). Test it for real.

## 1. Environment limits found in the build sandbox (why the code is built the way it is)
No internet, so `pip install flask-sqlalchemy librosa torch` and `npm install react vite` were impossible. Therefore:
* Backend = **Flask + stdlib sqlite3** (no SQLAlchemy). Audio features = **numpy + scipy only** (`backend/ml/features.py`), no librosa.
* Frontend = **no-build ES-module single-page app** (`frontend/`, served by Flask). Same pages/routes/guards as the React project,
  same CSS tokens. React/Vite was NOT used because it could not be compiled/tested here. Porting back to React is mechanical.
* The PyTorch CNN+BiGRU code from infant_cry_pro is copied unchanged into `backend/deep/` as an **optional** module. It was
  **not run** in the sandbox (no torch). It activates only if torch+librosa are installed and `model/cry_model.pt` exists.

## 2. Data facts (important, they decide what accuracy is possible)
* CSV columns: File_ID, Original_File, Gender, Age, Reason, CE_ID, CU_ID, Start_sec, End_sec, Duration, Min_F0, Max_F0, Mean_F0,
  Std_F0, HNR, MFCC_1..13, is_synthetic. Each row = one **cry unit** (~0.76 s) cut from a recording. 931 rows from **142 recordings**.
* Labels (Donate-a-Cry codes): hu hungry 650 | dk don't-know 175 | ti tired 23 | bp belly pain 17 | sc scared 16 | dc discomfort 14 |
  ch cold/hot 13 | bu burping 13 | lo lonely 10. Rare classes come from only **2-4 recordings each**.
* Rows from one recording are near-duplicates. A random row split leaks; **always split by `Original_File`** (grouped CV).
* HNR in the CSV goes down to -195: Praat-style, unvoiced frames count as -200. MFCC_1 is c0 (librosa-style, median about -116).
  Feature extractor mirrors that, but it has **never been checked against the original audio** (no wav files were supplied).

## 3. Layout
```
auracry_unified/
  run.py / run.bat / run.sh        one command start (creates admin if none)
  HANDOFF.md  README.md
  backend/  app.py config.py db.py auth_utils.py validators.py manage.py requirements.txt .env.example
    routes/ auth.py user.py admin.py lab.py
    ml/     features.py (audio -> cry units -> 19 CSV features)   stack.py (RF->Ada->LR cascade, SMOTE, trace)
            tabular_train.py (grouped CV + model selection + save)  service.py (load model, analyse audio/row, trace, explain)
            explain.py advice.py (Gemini/YouTube/KB)  deep_service.py (optional CNN-GRU)  calibrate_features.py
    deep/   original infant_cry_pro torch code (optional)
    model/  stack.joblib metrics.json (trained from the CSV)
    dataset/ test_dataset_clean.csv  balanced_full_dataset_clean.csv (empty placeholder - drop the real one here)
    tests/  test_access_control.py test_ml.py test_api_flow.py
  frontend/ index.html css/styles.css js/{app,api,ui,charts,mascot,wav}.js js/pages/{login,register,...}
```

## 4. How to run
```
cd backend && pip install -r requirements.txt && cp .env.example .env   # set SECRET_KEY
python manage.py create-admin --email admin@auracry.local --name "Admin"
python app.py        # http://127.0.0.1:5000
python -m ml.tabular_train --train dataset/balanced_full_dataset_clean.csv --test dataset/test_dataset_clean.csv
python -m unittest discover -v
```

## 5. Status / results
* DONE and tested in sandbox: Flask API (auth, user, admin, lab), sqlite, feature extractor, RF->Ada->LR stack, trainer with grouped CV,
  explanations, advice (+3 new classes: Scared, Cold/Hot, Lonely), full SPA frontend, Pipeline Lab, dark mode.
  Tests: `python -m unittest discover -s tests -t .` = 19 pass; `python -m tests.e2e_browser` = 37/37 pass (headless Chromium).
* NOT done / unverified: React port (frontend is vanilla ES modules), EN/HI/TE language switch of the old page (not ported; dark mode was),
  CNN+BiGRU never run, Gemini/YouTube never called (no network), feature extractor never compared with original audio,
  `balanced_full_dataset_clean.csv` was empty.
* Key result: grouped CV (by recording, dk dropped, 756 rows/115 recordings): always-Hungry 86.0% acc; RF 83.6% (macro-F1 .125); AdaBoost 77.0% (.150);
  LR 55.2% (.113); served Stack+SMOTE 85.6% (.115). Nothing beats the majority baseline on new recordings; rare classes (2-4 recordings each)
  are not learned. Leaky random split gives macro-F1 .54 = leakage. Do not claim higher accuracy without a grouped evaluation.
* Gotchas: this sandbox's /bin/sh has no brace expansion (use bash -c); single CPU, 300 s command limit (train in background with setsid nohup);
  Flask jsonify cannot be called at import time; JSON key order from Flask is alphabetical (frontend sorts stages rf, ada, ...).

## 6. Next steps worth doing (highest value first)
1. Re-upload `balanced_full_dataset_clean.csv` (it was empty) and retrain: `python -m ml.tabular_train --train ... --test ...`.
2. Get the original wav files and run `python -m ml.calibrate_features --audio_dir <wavs>`; fix any feature drift.
3. More recordings for rare classes (2-4 recordings per class cannot generalise). This is the real limit on accuracy.
4. Train the CNN+BiGRU on raw audio (`backend/deep`, needs torch+librosa) and fuse it.
