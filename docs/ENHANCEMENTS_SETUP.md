# AuraCry enhancements setup

## Preserved
The original login screen, cursor-following baby mascot, blue-to-pink background, audio upload/record screen, language selector, theme controls, authentication flow, admin account defaults, and existing ML/DL pipeline are retained. The user-facing Pipeline Lab navigation/page is removed; the admin lab remains available.

## AI Companion
The AI Companion and diary APIs work with safe built-in guidance. For Gemini-powered answers, add `GEMINI_API_KEY` to `backend/.env`. Never commit or share this key.

## Baby Memory Diary
Parents can tell AuraCry AI about a milestone. The UI asks for confirmation before saving it with a date. Memories are private to the signed-in user and can be deleted.

## Email OTP
Copy `backend/.env.example` to `backend/.env` and configure SMTP privately:

```ini
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_STARTTLS=1
SMTP_USER=your-sender@gmail.com
SMTP_PASS=your-Google-App-Password
SMTP_FROM=your-sender@gmail.com
OTP_DEV_ECHO=0
```

The default admin credentials remain `admin@auracry.local` / `Admin12345`. The `.local` address is not a real inbox, so for email OTP delivery set `ADMIN_EMAIL=your-real-gmail@gmail.com` in `backend/.env`. On the next start, the app updates only the default admin email; its existing password and PIN hashes are preserved. If you leave `ADMIN_EMAIL` blank, the original admin email remains unchanged. Keep the admin password/PIN and Gmail App Password private. Do not share Gmail credentials in chat.

## Multi-baby separation
This ZIP retains the optional experimental two-source separation module. Enable with `MULTI_BABY_ENABLED=1` and install `backend/requirements-multibaby.txt`. The separator was pretrained on speech mixtures, not infant cries; it is not a validated baby diarization model. It may fail or mix sources. Do not treat its output as reliable separation, and it does not support a guaranteed count of three or more babies.

## Important
Cry labels and AI chat are educational estimates, not medical diagnoses. Seek professional care for health concerns and emergency help for urgent symptoms.
