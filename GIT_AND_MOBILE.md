# Push to Git, deploy, and make the mobile app

## 1. Push to GitHub (once)
1. Create an empty repository on github.com (no README). Copy its URL.
2. In the project folder:
   ```
   git init
   git add .
   git status            # check: no .env, no *.db, no uploads/ are listed (the .gitignore excludes them)
   git commit -m "AuraCry: ML + CNN-BiGRU-attention pipeline with tuned fusion"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
3. Never commit `backend/.env` (secrets). `model/stack.joblib` (26 MB) and the dataset CSV (9 MB) fit under GitHub's 100 MB file limit.
   `cry_model.pt` is ignored by default; remove that line from `.gitignore` if you want to commit it (use Git LFS above ~50 MB).
4. Later changes: `git add . && git commit -m "message" && git push`.

## 2. Put the backend online (needed before any phone can use it)
A phone cannot reach `127.0.0.1`, and browsers/phones allow the microphone only over **https**.
* Easiest: Render / Railway / a small VPS. Connect the GitHub repo; start command is in `Procfile`
  (`gunicorn "app:create_app()"`), set the env vars from `backend/.env.example` (SECRET_KEY, optional GEMINI/YOUTUBE keys).
* The ML part is light. **PyTorch is heavy (about 1-2 GB RAM)**: free tiers will not run the CNN; use a paid instance, or deploy without
  `requirements-deep.txt` (the app then runs ML-only and says so).
* SQLite (`auracry.db`) resets on free hosts that have no disk; attach a persistent disk or move to Postgres for real users.
* Change the default admin password (`Admin12345`) on first login.

## 3. Mobile app (Capacitor wrapper, Android + iOS)
The frontend is a web app; Capacitor packages it as a real app that loads your deployed https site, so login cookies and the API keep working.
1. Install Node.js (nodejs.org). In the `mobile/` folder:
   ```
   cd mobile
   # edit capacitor.config.json: set "server.url" to your deployed https address
   npm install
   npx cap add android          # and/or: npx cap add ios   (iOS needs a Mac with Xcode)
   npm run sync
   npm run android              # opens Android Studio -> press Run (emulator or USB phone)
   ```
2. **Microphone permission.** Android: in `android/app/src/main/AndroidManifest.xml` add
   `<uses-permission android:name="android.permission.RECORD_AUDIO" />` and
   `<uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />`.
   iOS: in `ios/App/App/Info.plist` add `NSMicrophoneUsageDescription` = "AuraCry listens to your baby's cry to analyse it."
3. Build a release: Android Studio -> Build -> Generate Signed Bundle/APK (Play Store needs a $25 developer account);
   Xcode -> Product -> Archive (App Store needs the $99/year Apple program).
4. Quick no-store option: open the deployed site on the phone and "Add to Home Screen".

Note: the app only works while the server is online. Recording works only if the site is served over https.
