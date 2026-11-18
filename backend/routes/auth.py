"""Three-step authentication (one login page, the SERVER decides the role):

  Step 1  /auth/login/identify  email or username + chosen role  -> ticket
  Step 2  /auth/login/password  ticket + password (bcrypt)       -> OTP emailed, masked address returned
  Step 3  /auth/login/verify    ticket + 6-digit code            -> real session created (only here)

Plus: resend (with cooldown + cap), logout, me, csrf, register, password reset, change password, edit profile.
No session is created until the OTP step succeeds. Every failure is audited; repeated failures lock the account.
"""
import time
from collections import defaultdict

from flask import Blueprint, jsonify, request, session

import db
import security as S
import validators as V
from auth_utils import current_user, login_required, public_user

bp = Blueprint("auth", __name__, url_prefix="/api")

_fails = defaultdict(list)                     # (ip, identifier) -> recent failed-step timestamps (fast pre-DB throttle)
LIMIT, WINDOW = 6, 300


def _throttled(key):
    now = time.time()
    _fails[key] = [t for t in _fails[key] if now - t < WINDOW]
    return len(_fails[key]) >= LIMIT


def _note_fail(key):
    _fails[key].append(time.time())


def admin_denied():
    return jsonify(error="access_denied", message="Access Denied: invalid admin credentials."), 403


def _emit_otp(ticket, user, purpose="login"):
    code = S.issue_otp(ticket)
    try:
        channel, dev_code = S.send_otp_email(user["email"], code, purpose)
    except S.OTPDeliveryError:
        # Do not leave a valid OTP ticket behind when delivery failed.
        db.execute("UPDATE login_tickets SET otp_hash=NULL, otp_expires=NULL WHERE token=?", (ticket,))
        raise
    out = {"otp_required": True, "masked_email": S.mask_email(user["email"]), "delivery": channel,
           "resend_in": S.OTP_RESEND_COOLDOWN, "expires_in": S.OTP_TTL}
    if dev_code is not None:                   # only when OTP_DEV_ECHO=1 (dev/testing); honestly labelled
        out["dev_code"] = dev_code
        out["dev_note"] = "No email provider configured - this code is shown for development only."
    return out


# ------------------------------------------------------------------ register
@bp.post("/auth/register")
def register():
    d = request.get_json(silent=True) or {}
    name, email = (d.get("name") or "").strip(), (d.get("email") or "").strip().lower()
    err = V.check_name(name) or V.check_email(email) or V.check_password(d.get("password")) or V.check_pin(d.get("pin"))
    if not err and d.get("password") != d.get("confirm_password"):
        err = "Passwords do not match."
    if err:
        return jsonify(error="validation", message=err), 400
    if db.one("SELECT 1 FROM users WHERE email=?", (email,)):
        return jsonify(error="validation", message="An account with this email already exists."), 409
    db.execute("INSERT INTO users(name,email,password_hash,role,pin_hash) VALUES(?,?,?, 'USER', ?)",  # role is ALWAYS USER here
               (name, email, S.hash_password(d["password"]), S.hash_pin((d["pin"]).strip())))
    S.audit("register", detail=email)
    return jsonify(message="Account created. You can now sign in."), 201


# ------------------------------------------------------------------ step 1: identify
@bp.post("/auth/login/identify")
def identify():
    d = request.get_json(silent=True) or {}
    ident = (d.get("identifier") or "").strip().lower()
    as_ = d.get("login_as")
    if not ident or as_ not in ("USER", "ADMIN"):
        return jsonify(error="validation", message="Please enter your email and choose a role."), 400
    key = (request.remote_addr, ident)
    if _throttled(key):
        return jsonify(error="too_many_attempts", message="Too many attempts. Please wait a few minutes."), 429
    u = db.one("SELECT * FROM users WHERE email=?", (ident,))
    # Admin sign-in gives one identical answer for every failure (no hint about which part was wrong).
    if as_ == "ADMIN" and not (u and u["role"] == "ADMIN" and u["status"] == "ACTIVE"):
        _note_fail(key); S.audit("login_identify_fail", u["id"] if u else None, f"admin as {ident}")
        return admin_denied()
    if as_ == "USER":
        if u is None:
            _note_fail(key); S.audit("login_identify_fail", None, ident)
            return jsonify(error="invalid_credentials", message="No account found for that email."), 404
        if u["role"] == "ADMIN":
            return jsonify(error="access_denied", message="Administrators must choose 'Admin' to sign in."), 403
        if u["status"] != "ACTIVE":
            S.audit("login_inactive", u["id"], ident)
            return jsonify(error="inactive", message="This account is deactivated. Please contact the administrator."), 403
    if S.is_locked(u):
        return jsonify(error="locked", message=f"Account temporarily locked. Try again in {max(1, S.lock_seconds_left(u)//60)} min."), 423
    ticket = S.create_ticket(u["id"], "login")
    return jsonify(ticket=ticket, step="password", name=u["name"])


# ------------------------------------------------------------------ step 2: password -> OTP
@bp.post("/auth/login/password")
def login_password():
    d = request.get_json(silent=True) or {}
    tok, pw = d.get("ticket") or "", d.get("password") or ""
    t = S.get_ticket(tok, "login")
    if not t:
        return jsonify(error="expired", message="Your session expired. Please start again."), 410
    u = db.one("SELECT * FROM users WHERE id=?", (t["user_id"],))
    if u is None or u["status"] != "ACTIVE":
        S.drop_ticket(tok)
        return jsonify(error="invalid_credentials", message="Account unavailable."), 403
    if S.is_locked(u):
        S.drop_ticket(tok)
        return jsonify(error="locked", message=f"Account temporarily locked. Try again in {max(1, S.lock_seconds_left(u)//60)} min."), 423
    ok, needs_rehash = S.verify_password(pw, u["password_hash"])
    key = (request.remote_addr, u["email"])
    if not ok:
        _note_fail(key)
        locked = S.record_failure(u["id"])
        S.audit("login_password_fail", u["id"], "locked" if locked else "")
        S.drop_ticket(tok)
        if locked:
            return jsonify(error="locked", message="Too many failed attempts. Account locked for a while."), 423
        return jsonify(error="invalid_credentials", message="Incorrect password."), 401
    if needs_rehash:
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (S.hash_password(pw), u["id"]))
    db.execute("UPDATE login_tickets SET password_ok=1 WHERE token=?", (tok,))
    S.audit("login_password_ok", u["id"])
    try:
        return jsonify(ticket=tok, step="otp", **_emit_otp(tok, u))
    except S.OTPDeliveryError as e:
        return jsonify(error="otp_delivery_failed", message=str(e)), 503


# ------------------------------------------------------------------ step 3: OTP -> session
@bp.post("/auth/login/verify")
def login_verify():
    d = request.get_json(silent=True) or {}
    tok, code = d.get("ticket") or "", (d.get("code") or "").strip()
    t = S.get_ticket(tok, "login")
    if not t or not t["password_ok"]:
        return jsonify(error="expired", message="Your session expired. Please start again."), 410
    res = S.check_otp(t, code)
    u = db.one("SELECT * FROM users WHERE id=?", (t["user_id"],))
    if res == "ok":
        # Factor 2 passed. Do NOT create a session yet - the third factor (security PIN) is still required.
        db.execute("UPDATE login_tickets SET otp_ok=1 WHERE token=?", (tok,))
        S.audit("login_otp_ok", u["id"])
        return jsonify(ticket=tok, step="pin", pin_set=bool(u.get("pin_hash")))
    if res == "expired":
        S.drop_ticket(tok)
        return jsonify(error="otp_expired", message="The code expired. Please request a new one."), 410
    if res == "locked":
        S.drop_ticket(tok); S.audit("login_otp_locked", u["id"])
        return jsonify(error="otp_locked", message="Too many incorrect codes. Please start again."), 429
    S.audit("login_otp_bad", u["id"])
    left = max(0, S.OTP_MAX_ATTEMPTS - ((t["otp_attempts"] or 0) + 1))
    return jsonify(error="otp_invalid", message=f"Incorrect code. {left} attempt(s) left."), 401


# ------------------------------------------------------------------ resend OTP
@bp.post("/auth/login/resend")
def login_resend():
    d = request.get_json(silent=True) or {}
    tok = d.get("ticket") or ""
    t = S.get_ticket(tok, "login")
    if not t or not t["password_ok"]:
        return jsonify(error="expired", message="Your session expired. Please start again."), 410
    wait = S.can_resend(t)
    if wait == -1:
        return jsonify(error="resend_limit", message="Resend limit reached. Please start again."), 429
    if wait > 0:
        return jsonify(error="cooldown", message=f"Please wait {wait}s before requesting another code.", resend_in=wait), 429
    u = db.one("SELECT * FROM users WHERE id=?", (t["user_id"],))
    S.mark_resent(tok)
    S.audit("login_otp_resend", u["id"])
    try:
        return jsonify(ticket=tok, step="otp", **_emit_otp(tok, u))
    except S.OTPDeliveryError as e:
        return jsonify(error="otp_delivery_failed", message=str(e)), 503


# ------------------------------------------------------------------ step 4 (factor 3): security PIN -> session
@bp.post("/auth/login/pin")
def login_pin():
    d = request.get_json(silent=True) or {}
    tok, pin = d.get("ticket") or "", (d.get("pin") or "").strip()
    t = S.get_ticket(tok, "login")
    if not t or not t["password_ok"] or not t["otp_ok"]:
        return jsonify(error="expired", message="Your session expired. Please start again."), 410
    u = db.one("SELECT * FROM users WHERE id=?", (t["user_id"],))
    if u is None or u["status"] != "ACTIVE":
        S.drop_ticket(tok)
        return jsonify(error="invalid_credentials", message="Account unavailable."), 403

    if not u.get("pin_hash"):
        # legacy account with no PIN yet: this step sets it (first-time security setup)
        err = V.check_pin(pin)
        if err:
            return jsonify(error="validation", message=err, pin_setup=True), 400
        db.execute("UPDATE users SET pin_hash=? WHERE id=?", (S.hash_pin(pin), u["id"]))
        S.audit("pin_set_on_login", u["id"])
    else:
        if (t["pin_attempts"] or 0) >= S.PIN_MAX_ATTEMPTS:
            S.drop_ticket(tok); S.audit("login_pin_locked", u["id"])
            return jsonify(error="pin_locked", message="Too many incorrect PIN tries. Please start again."), 429
        if not S.verify_pin(pin, u["pin_hash"]):
            db.execute("UPDATE login_tickets SET pin_attempts=COALESCE(pin_attempts,0)+1 WHERE token=?", (tok,))
            S.audit("login_pin_bad", u["id"])
            left = max(0, S.PIN_MAX_ATTEMPTS - ((t["pin_attempts"] or 0) + 1))
            return jsonify(error="pin_invalid", message=f"Incorrect PIN. {left} attempt(s) left."), 401

    S.drop_ticket(tok); S.clear_failures(u["id"])
    session.clear()
    session["uid"] = u["id"]; session.permanent = True
    S.ensure_csrf()
    S.audit("login_success", u["id"], u["role"])
    return jsonify(user=public_user(u), csrf_token=session["csrf"])


# ------------------------------------------------------------------ logout / me / csrf
@bp.post("/auth/logout")
def logout():
    u = current_user()
    if u:
        S.audit("logout", u["id"])
    session.clear()
    return jsonify(message="Logged out.")


@bp.get("/auth/me")
def me():
    u = current_user()
    if u is None:
        return jsonify(error="unauthenticated", message="Not logged in."), 401
    return jsonify(user=public_user(u), csrf_token=S.ensure_csrf())


@bp.get("/auth/csrf")
def csrf():
    return jsonify(csrf_token=S.ensure_csrf())


# ------------------------------------------------------------------ password reset (email OTP)
@bp.post("/auth/password-reset/request")
def reset_request():
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    u = db.one("SELECT * FROM users WHERE email=? AND status='ACTIVE'", (email,))
    resp = {"message": "If an account exists for that email, a reset code has been sent."}
    if u is None:                                   # no account enumeration
        return jsonify(**resp)
    tok = S.create_ticket(u["id"], "reset")
    db.execute("UPDATE login_tickets SET password_ok=1 WHERE token=?", (tok,))   # reset tickets go straight to OTP
    try:
        info = _emit_otp(tok, u, "reset")
    except S.OTPDeliveryError as e:
        S.drop_ticket(tok)
        return jsonify(error="otp_delivery_failed", message=str(e)), 503
    out = {**resp, "ticket": tok, "masked_email": info["masked_email"], "delivery": info["delivery"],
           "resend_in": info["resend_in"], "expires_in": info["expires_in"]}
    if "dev_code" in info:
        out["dev_code"] = info["dev_code"]; out["dev_note"] = info["dev_note"]
    S.audit("reset_request", u["id"])
    return jsonify(**out)


@bp.post("/auth/password-reset/confirm")
def reset_confirm():
    d = request.get_json(silent=True) or {}
    tok, code = d.get("ticket") or "", (d.get("code") or "").strip()
    t = S.get_ticket(tok, "reset")
    if not t:
        return jsonify(error="expired", message="Your reset session expired. Please start again."), 410
    err = V.check_password(d.get("new_password"))
    if not err and d.get("new_password") != d.get("confirm_password"):
        err = "Passwords do not match."
    if err:
        return jsonify(error="validation", message=err), 400
    res = S.check_otp(t, code)
    u = db.one("SELECT * FROM users WHERE id=?", (t["user_id"],))
    if res != "ok":
        if res in ("expired", "locked"):
            S.drop_ticket(tok)
        msg = {"expired": "The code expired. Please start again.", "locked": "Too many attempts. Please start again.",
               "bad": "Incorrect code."}[res]
        return jsonify(error=f"otp_{res}", message=msg), 401
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (S.hash_password(d["new_password"]), u["id"]))
    S.clear_failures(u["id"]); S.drop_ticket(tok)
    S.audit("reset_done", u["id"])
    return jsonify(message="Password reset. You can now sign in.")


# ------------------------------------------------------------------ account (logged in)
@bp.put("/account/profile")
@login_required
def edit_profile():
    d, u = request.get_json(silent=True) or {}, current_user()
    name, email = (d.get("name") or "").strip(), (d.get("email") or "").strip().lower()
    err = V.check_name(name) or V.check_email(email)
    if err:
        return jsonify(error="validation", message=err), 400
    if db.one("SELECT 1 FROM users WHERE email=? AND id<>?", (email, u["id"])):
        return jsonify(error="validation", message="That email is already used by another account."), 409
    db.execute("UPDATE users SET name=?, email=? WHERE id=?", (name, email, u["id"]))
    S.audit("profile_update", u["id"])
    return jsonify(user=public_user(db.one("SELECT * FROM users WHERE id=?", (u["id"],))))


@bp.post("/account/password")
@login_required
def change_password():
    d, u = request.get_json(silent=True) or {}, current_user()
    ok, _ = S.verify_password(d.get("current_password") or "", u["password_hash"])
    if not ok:
        return jsonify(error="validation", message="Current password is incorrect."), 400
    err = V.check_password(d.get("new_password"))
    if not err and d.get("new_password") != d.get("confirm_password"):
        err = "New passwords do not match."
    if err:
        return jsonify(error="validation", message=err), 400
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (S.hash_password(d["new_password"]), u["id"]))
    S.audit("password_change", u["id"])
    return jsonify(message="Password changed.")


@bp.post("/account/pin")
@login_required
def change_pin():
    d, u = request.get_json(silent=True) or {}, current_user()
    ok, _ = S.verify_password(d.get("current_password") or "", u["password_hash"])
    if not ok:
        return jsonify(error="validation", message="Current password is incorrect."), 400
    err = V.check_pin(d.get("new_pin"))
    if err:
        return jsonify(error="validation", message=err), 400
    db.execute("UPDATE users SET pin_hash=? WHERE id=?", (S.hash_pin((d["new_pin"]).strip()), u["id"]))
    S.audit("pin_change", u["id"])
    return jsonify(message="Security PIN updated.")
