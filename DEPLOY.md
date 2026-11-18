# AuraCry — deployment (web app)

## What gets deployed
**One service.** Flask serves the web app *and* the API, so you do **not** need Vercel or Supabase or three accounts.
The whole thing runs as a single container on **Render** (free). The database is SQLite, baked into the container.

```
   Your phone/computer browser
            │  https
            ▼
   ┌─────────────────────────┐
   │   Render (one service)  │   ← the only thing you create
   │  Flask: web app + API   │
   │  ML model + SQLite      │
   └─────────────────────────┘
```

## What YOU do (about 10 minutes, mostly waiting)
1. **Put the code on GitHub** (one-time). From the project folder:
   ```bash
   git init && git add . && git commit -m "AuraCry"
   git branch -M main
   git remote add origin https://github.com/<your-username>/auracry.git
   git push -u origin main
   ```
   (Create the empty `auracry` repo on github.com first.)
2. **Create a Render account** at render.com — sign in with GitHub (free, no card).
3. In Render: **New + → Blueprint**, pick your `auracry` repo, click **Apply**.
   Render reads `render.yaml`, builds the `Dockerfile`, and deploys. First build takes ~5–10 min.
4. When it's live, Render gives you a URL like `https://auracry.onrender.com`. Open it — that's your app.

That's everything. No other accounts.

### Logging in on the live site
No email provider is configured, so the app runs in **dev OTP mode**: the 6-digit code is shown on screen (clearly
labelled "dev mode"). Just **Register** an account, and when it asks for the email code, read it from the screen. The
security PIN you set is yours. (To email real codes instead, see "Email" below.)

## Free-tier facts (honest)
- **Sleeps when idle:** the free service spins down after ~15 min of no traffic; the next visit takes ~30–50s to wake. Normal for free hosting.
- **Data resets:** the free disk is ephemeral, so accounts/history reset on redeploy or restart. Fine for a demo. To keep data, add a paid Render disk, or migrate to Postgres.
- **ML model only:** the free tier has 512 MB RAM — enough for the ML model (74% accuracy). The deep (CNN+BiGRU) branch needs ~2 GB, so it's off by default; the app runs ML-only automatically and says so.

## Optional upgrades
- **Turn on the deep model + fusion:** uncomment `torch` and `librosa` in `backend/requirements.txt`, un-ignore and commit
  `backend/model/cry_model.pt`, and use a Render instance with ≥ 2 GB RAM. The app then runs both branches and fuses them.
- **Email real OTP codes:** set `OTP_DEV_ECHO=0` and add `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` in the Render dashboard
  (a free Gmail app password works). The on-screen dev code then disappears and codes go to email.
- **An admin account on boot:** set `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_PIN` in the Render dashboard.
- **Android APK:** once you have the Render URL, put it in `mobile/capacitor.config.json` → `server.url` and build (see `mobile/BUILD_ANDROID.md`).

## Run it locally (no deploy)
```bash
cd backend && pip install -r requirements.txt && cp .env.example .env   # then set SECRET_KEY in .env
python manage.py init-db && python manage.py seed-demo        # demo accounts -> DEMO_CREDENTIALS.md
python app.py                                                 # http://127.0.0.1:5000
```
