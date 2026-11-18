"""USER endpoints: dashboard, analyse audio (real pipeline), history. Files can also be opened by an ADMIN."""
import hashlib
import json
import uuid
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

import db
import ratelimit
from auth_utils import current_user, login_required, role_required
from config import ALLOWED_EXTENSIONS, MAX_AUDIO_MB, SPECTROGRAM_DIR, UPLOAD_DIR
from ml.audio_io import AudioError
from ml import upload_validation
from ml.service import ModelNotReady, service

bp = Blueprint("user", __name__, url_prefix="/api")


def analysis_dict(r, full=False, with_user=False):
    res = json.loads(r["result_json"])
    d = {"id": r["id"], "code": f"AC-{r['id']:05d}", "audio_filename": r["audio_filename"],
         "predicted_category": r["predicted_category"], "predicted_label": res.get("label", r["predicted_category"]),
         "confidence": round(r["confidence"] * 100, 1), "uncertain": res.get("uncertain", False),
         "duration_sec": round(r["duration_sec"], 1), "created_at": (r["created_at"] or "").replace(" ", "T") + "Z",
         "audio_url": f"/api/analyses/{r['id']}/audio", "spectrogram_url": f"/api/analyses/{r['id']}/spectrogram",
         "report_url": f"/api/analyses/{r['id']}/report",
         "probabilities": {k: round(v * 100, 1) for k, v in res.get("probabilities", {}).items()}}
    if full:
        d["result"] = res
    if with_user:
        d["user"] = {"id": r["user_id"], "name": r.get("user_name"), "email": r.get("user_email")}
    return d


@bp.get("/dashboard")
@role_required("USER")
def dashboard():
    u = current_user()
    rows = db.q("SELECT * FROM analyses WHERE user_id=? ORDER BY created_at DESC, id DESC LIMIT 3", (u["id"],))
    n = db.one("SELECT COUNT(*) c FROM analyses WHERE user_id=?", (u["id"],))["c"]
    return jsonify(name=u["name"], analysis_count=n, recent=[analysis_dict(r) for r in rows], model_ready=service.is_ready())


@bp.post("/analyses")
@role_required("USER")
def create_analysis():
    if not service.is_ready():
        return jsonify(error="model_unavailable", message="The model is not available yet. Please contact the administrator."), 503
    uid = current_user()["id"]
    rl = current_app.config.get("RATELIMIT_ENABLED", True)
    if rl:
        over = ratelimit.limit(f"analyse:{uid}", 30, 3600)    # per-user: at most 30 analyses/hour
        if over:
            return over
    f = request.files.get("audio")
    if f is None or not f.filename:
        return jsonify(error="validation", message="Please choose an audio file."), 400
    original = secure_filename(f.filename) or "audio.wav"
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify(error="unsupported_ext", message="Unsupported file type. Use WAV, MP3, M4A, OGG or FLAC."), 400
    token = uuid.uuid4().hex
    audio_path, spec_path = UPLOAD_DIR / f"{token}.{ext}", SPECTROGRAM_DIR / f"{token}.png"
    f.save(audio_path)

    def cleanup():
        for p in (audio_path, spec_path):
            Path(p).unlink(missing_ok=True)

    # Phase 9: real server-side validation (magic bytes + ffprobe + bounds) before we trust the file at all.
    try:
        upload_validation.validate_file(audio_path, audio_path.stat().st_size, MAX_AUDIO_MB)
    except AudioError as e:
        cleanup()
        return jsonify(error=e.code, message=str(e)), 422
    # Phase 11: reject an accidental identical re-submit, and don't run two analyses at once for one user.
    if rl:
        sha = hashlib.sha1(audio_path.read_bytes()).hexdigest()
        if ratelimit.duplicate(uid, sha):
            cleanup()
            return jsonify(error="duplicate", message="You just submitted this same recording. Please wait a moment."), 429
        busy = ratelimit.begin_analysis(uid)
        if busy:
            cleanup()
            return busy
    try:
        res = service.analyze_file(audio_path, spec_path)
        # Optional multi-baby branch. The existing single-baby result remains the
        # primary result and is never discarded if separation is unavailable.
        try:
            from ml.multi_baby import analyze_candidates
            res["multi_baby"] = analyze_candidates(audio_path, service)
        except Exception as multi_error:
            current_app.logger.warning("Multi-baby analysis unavailable: %s", multi_error)
            res["multi_baby"] = {"status": "unavailable", "message": "Multi-baby separation is unavailable; the standard analysis is shown."}
    except AudioError as e:
        cleanup()
        return jsonify(error=e.code, message=str(e)), 422
    except ModelNotReady:
        cleanup()
        return jsonify(error="model_unavailable", message="The model is not available."), 503
    except Exception:
        cleanup()
        raise
    finally:
        if rl:
            ratelimit.end_analysis(uid)
    rid = db.execute("INSERT INTO analyses(user_id,audio_filename,audio_path,spectrogram_path,predicted_category,confidence,duration_sec,result_json)"
                     " VALUES(?,?,?,?,?,?,?,?)",
                     (current_user()["id"], original, audio_path.name, spec_path.name, res["category"], res["confidence"],
                      res["duration_sec"], json.dumps(res)))
    return jsonify(analysis=analysis_dict(db.one("SELECT * FROM analyses WHERE id=?", (rid,)), full=True)), 201


@bp.get("/analyses")
@role_required("USER")
def list_analyses():
    rows = db.q("SELECT * FROM analyses WHERE user_id=? ORDER BY created_at DESC, id DESC", (current_user()["id"],))
    return jsonify(analyses=[analysis_dict(r) for r in rows])


@bp.get("/analyses/<int:aid>")
@role_required("USER")
def get_analysis(aid):
    r = db.one("SELECT * FROM analyses WHERE id=? AND user_id=?", (aid, current_user()["id"]))
    if r is None:
        abort(404)
    return jsonify(analysis=analysis_dict(r, full=True))


def _can_open(r):
    u = current_user()
    return r is not None and (u["role"] == "ADMIN" or r["user_id"] == u["id"])


@bp.get("/analyses/<int:aid>/audio")
@login_required
def analysis_audio(aid):
    r = db.one("SELECT * FROM analyses WHERE id=?", (aid,))
    if not _can_open(r):
        abort(404)
    if request.args.get("clean") == "1":
        # Phase 10: band-pass + spectral-gate "cleaned" playback, computed on the fly (display only; not fed to the model)
        import io
        import soundfile as sf
        from ml.audio_io import load_audio
        from ml import denoise
        try:
            y, _ = load_audio(str(UPLOAD_DIR / r["audio_path"]))
            buf = io.BytesIO(); sf.write(buf, denoise.denoise(y, denoise.SR), denoise.SR, format="WAV", subtype="PCM_16")
            buf.seek(0)
            return send_file(buf, mimetype="audio/wav", download_name="cleaned.wav")
        except Exception:
            abort(404)
    return send_from_directory(UPLOAD_DIR, r["audio_path"])


@bp.get("/analyses/<int:aid>/spectrogram")
@login_required
def analysis_spectrogram(aid):
    r = db.one("SELECT * FROM analyses WHERE id=?", (aid,))
    if not _can_open(r) or not r["spectrogram_path"]:
        abort(404)
    return send_from_directory(SPECTROGRAM_DIR, r["spectrogram_path"])


@bp.get("/analyses/<int:aid>/report")
@login_required
def analysis_report(aid):
    """Phase 14: downloadable PDF report for one analysis. Owner or admin only."""
    r = db.one("SELECT * FROM analyses WHERE id=?", (aid,))
    if not _can_open(r):
        abort(404)
    from ml import report_pdf
    spec = None
    if r["spectrogram_path"]:
        p = SPECTROGRAM_DIR / r["spectrogram_path"]
        if p.exists():
            spec = p
    try:
        pdf = report_pdf.build_report(analysis_dict(r, full=True), spectrogram_path=spec)
    except Exception:
        current_app.logger.exception("pdf report failed for analysis %s", aid)
        return jsonify(error="report_failed", message="Could not generate the report. Please try again."), 500
    import io
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name=f"AuraCry-AC-{r['id']:05d}.pdf")
