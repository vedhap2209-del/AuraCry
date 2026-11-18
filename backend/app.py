"""AuraCry Unified - Flask entry point.   Run:  python app.py   ->  http://127.0.0.1:5000
Serves the REST API (/api/*) AND the no-build frontend (../frontend). Admin PAGE urls are guarded on the server too."""
import logging
import os

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.exceptions import HTTPException

import db
import ratelimit
import security as S
from auth_utils import current_user
from config import (DATASET_DIR, FRONTEND_DIR, MODEL_DIR, SPECTROGRAM_DIR, UPLOAD_DIR, Config)

DEFAULT_MESSAGES = {400: "Bad request.", 401: "Please log in to continue.", 403: "Access denied.", 404: "Not found.",
                    405: "Method not allowed.", 413: "The uploaded file is too large."}
ACCESS_DENIED_HTML = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Access denied</title><body style="font-family:system-ui;text-align:center;padding:15vh 24px">
<h1>Access Denied</h1><p>You do not have permission to view this page.</p><p><a href="/">Back to login</a></p>"""


def create_app(load_model=True):
    if not Config.SECRET_KEY:
        raise RuntimeError("SECRET_KEY is missing. Copy backend/.env.example to backend/.env and set it.")
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    app.config["RATELIMIT_ENABLED"] = os.environ.get("RATELIMIT_ENABLED", "1") == "1"
    logging.basicConfig(level=logging.INFO)
    for p in (UPLOAD_DIR, SPECTROGRAM_DIR, DATASET_DIR, MODEL_DIR):
        p.mkdir(parents=True, exist_ok=True)
    db.init()
    app.teardown_appcontext(db.close)

    from routes import admin, auth, lab, user, companion
    for m in (auth, user, admin, lab, companion):
        app.register_blueprint(m.bp)

    if load_model:
        from ml.service import service
        app.logger.info("Model loaded." if service.load() else service.error)

    @app.get("/api/health")
    def health():
        from ml.service import service
        m = service.metrics or {}
        return jsonify(status="ready" if service.is_ready() else "model_not_trained", model=m.get("model_name"),
                       gemini_enabled=bool(os.getenv("GEMINI_API_KEY")), youtube_enabled=bool(os.getenv("YOUTUBE_API_KEY")))

    def wants_json():
        return request.path.startswith("/api/")

    CSRF_EXEMPT = ("/api/auth/",)             # login/register/reset run before a session exists

    @app.before_request
    def rate_guard():
        p = request.path
        if not app.config.get("RATELIMIT_ENABLED", True) or not p.startswith("/api/") or request.method == "OPTIONS":
            return
        ip = ratelimit.client_ip()
        if p.startswith("/api/auth/"):        # auth surface is the most-attacked: tighter per-IP limit
            resp = ratelimit.limit(f"auth:{ip}", 40, 60)
            if resp:
                return resp
        resp = ratelimit.limit(f"api:{ip}", 300, 60)   # global flood guard
        if resp:
            return resp

    @app.before_request
    def csrf_guard():
        if (request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/")
                and not request.path.startswith(CSRF_EXEMPT) and session.get("uid")):
            if not S.csrf_ok():
                return jsonify(error="csrf", message="Missing or invalid security token. Refresh and try again."), 403

    @app.errorhandler(HTTPException)
    def http_err(e):
        if wants_json():
            return jsonify(error=e.name.lower().replace(" ", "_"), message=DEFAULT_MESSAGES.get(e.code, e.description)), e.code
        return e

    @app.errorhandler(Exception)
    def any_err(e):
        app.logger.exception("Unhandled error")
        if wants_json():
            return jsonify(error="server_error", message="Something went wrong on the server."), 500
        return "Internal server error", 500

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if wants_json():
            resp.headers["Cache-Control"] = "no-store"
        tok = session.get("csrf")               # expose the CSRF token to the SPA (double-submit); readable by JS
        if tok and request.cookies.get(S.CSRF_COOKIE) != tok:
            resp.set_cookie(S.CSRF_COOKIE, tok, samesite="Lax", secure=Config.SESSION_COOKIE_SECURE, httponly=False)
        return resp

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path):
        if path.startswith("api/"):
            return jsonify(error="not_found", message="Not found."), 404
        if path == "admin" or path.startswith("admin/"):          # server-side guard for admin PAGE urls
            u = current_user()
            if u is None or u["role"] != "ADMIN":
                return ACCESS_DENIED_HTML, 403
        if path and (FRONTEND_DIR / path).is_file():
            r = send_from_directory(FRONTEND_DIR, path)
            r.headers["Cache-Control"] = "no-cache"
            return r
        return send_from_directory(FRONTEND_DIR, "index.html")     # client-side router handles the rest

    return app


if __name__ == "__main__":
    create_app().run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)), debug=False)
