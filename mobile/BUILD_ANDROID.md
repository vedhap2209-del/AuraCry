# AuraCry — Android APK build

The Android app is a **Capacitor WebView shell** around the deployed AuraCry web app. The app itself needs the backend
(the ML + DL models run on the server), so the APK points at your deployed backend URL and shows the real app inside a
native Android wrapper. Login, the 3-step auth, language switch, upload, record, results and history all work — it is the
same web app, so there is no second copy of the code to maintain.

This folder is a **complete, ready-to-build project**. The APK binary itself was not built in the authoring environment
because Google's Android SDK servers and `services.gradle.org` were not reachable there. On any machine with internet it
builds with one command.

## 1. One-time setup
- Install **Android Studio** (bundles the Android SDK, platform tools and a JDK). Open it once so it downloads the SDK.
  (Or: a JDK 17 + the Android command-line tools + `ANDROID_HOME` set.)
- Install Node.js 18+.

## 2. Point the app at your backend
Edit `capacitor.config.json` and set `server.url` to your deployed backend (from Phase 15, e.g. your Render URL):
```json
"server": { "url": "https://auracry-backend.onrender.com", "androidScheme": "https" }
```
For a quick local demo over your Wi-Fi instead, run the backend on your PC and use its LAN address, allowing cleartext:
```json
"server": { "url": "http://192.168.1.50:5000", "cleartext": true, "androidScheme": "http" }
```

## 3. Build the APK
```bash
cd mobile
npm install
npx cap sync android        # copies config + web assets into the android project
cd android
./gradlew assembleDebug     # first run downloads Gradle + Android deps (needs internet)
```
The debug APK appears at:
```
mobile/android/app/build/outputs/apk/debug/app-debug.apk
```
Copy it to an Android phone and install it (enable "install from unknown sources"). It is a **real installable APK**, not a
renamed web build.

## 4. Open in Android Studio instead (optional)
```bash
npx cap open android
```
then press **Run** to install on a connected device or emulator.

## 5. Release build (optional, needs your own signing key)
```bash
cd android && ./gradlew assembleRelease
```
Create and keep your keystore private — **never commit signing keys or passwords**. Configure signing in
`android/app/build.gradle` (`signingConfigs`) with a keystore you generate via `keytool`.

## Notes
- The manifest already declares `INTERNET` and `RECORD_AUDIO` (microphone recording) permissions.
- `appId` is `app.auracry.mobile`, app name **AuraCry**. Change the launcher icon under `android/app/src/main/res/mipmap-*`.
- If `./gradlew` cannot download Gradle, your network blocks `services.gradle.org`; build on an unrestricted network or
  use a CI runner (e.g. GitHub Actions `android` workflow) which has access.
- `mobile/node_modules`, `mobile/android/build`, `.gradle`, and any `*.apk` are git-ignored; regenerate with the steps above.
