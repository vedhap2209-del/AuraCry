# AuraCry: the three requested enhancements

This update preserves the existing single-recording AuraCry pipeline and adds the following targeted fixes.

## 1. Email OTP delivery

The project sends OTP messages through SMTP. To enable real email delivery, edit `backend/.env` (never share or commit this file).

For Gmail:

1. Enable 2-Step Verification on the Google account that will send AuraCry mail.
2. Create a Google App Password from the Google Account security settings.
3. Copy `backend/.env.example` to `backend/.env` if `run.py` has not already created it.
4. Set the following values in `backend/.env`:

```ini
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_STARTTLS=1
SMTP_USER=your-sender@gmail.com
SMTP_PASS=your-16-character-google-app-password
SMTP_FROM=your-sender@gmail.com
OTP_DEV_ECHO=0
```

5. Restart AuraCry and test login. The OTP response should say `delivery: "email"`.

Do not use your normal Gmail password. If SMTP is misconfigured or Gmail rejects the login, AuraCry now returns an OTP delivery error instead of pretending the message was sent. With no SMTP host configured, development mode remains available and logs a development-only OTP as before.

## 2. Admin Model Performance

The admin page now reads the metrics format actually included in this project:

- `backend/model/metrics.json`: tabular stack test metrics, per-class scores, comparison, class counts and confusion matrix.
- `backend/model/dl_metrics.json`: CNN + BiGRU test and validation metrics.

The page shows values from these files and no longer assumes the unrelated nested `test.cnn_gru`, `test.random_forest` and `test.fused` schema. Confusion-matrix labels use the saved class label order, not the extra summary rows in `per_class`.

The numbers are the project's saved evaluation values; this change does not retrain models or alter metrics.

## 3. Multiple-baby cry analysis (experimental)

The existing one-recording analysis always runs first and remains the primary result. An optional second branch attempts to separate a mixed recording into **two candidate sources** and sends each candidate through the same existing AuraCry analysis pipeline. If the optional branch is disabled, unavailable, or cannot obtain two usable sources, the original result is retained.

To enable the experimental separator:

```powershell
pip install -r backend\requirements-multibaby.txt
```

Then set this in `backend/.env`:

```ini
MULTI_BABY_ENABLED=1
```

Restart the server. On the first multi-baby analysis, SpeechBrain downloads the pretrained `speechbrain/sepformer-whamr16k` model weights. The model is CPU-based and may require several GB of free disk space and additional processing time.

**Important limitation:** this pretrained separator was trained on speech mixtures, not infant cries. It is an experimental two-source enhancement, not a validated infant-cry separator. It cannot reliably establish the number or identity of babies and currently produces at most two candidate sources. Overlapping cries, similar vocal characteristics, background noise and recording quality can cause leakage or failed separation. The interface labels the outputs “Baby source 1” and “Baby source 2” and shows a warning. Validate it on representative two-baby recordings before relying on the output. Supporting three or more babies reliably requires an N-source separator trained and evaluated on multi-infant cry mixtures; this ZIP does not claim that capability.

## Run

Use the existing start instructions in `README.md`. The optional multi-baby feature does not replace the current ML model, preprocessing, cry-unit segmentation, feature extraction, or result workflow.
