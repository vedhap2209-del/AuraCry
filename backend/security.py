"""Security primitives for the three-step auth: password hashing (bcrypt, with legacy verify + auto-rehash), email OTP
tickets, account lockout, audit logging, CSRF tokens, and email delivery.

Nothing here trusts the browser: OTPs are stored only as hashes, tickets are random server-side handles, and the real
session is created ONLY after the OTP step succeeds (done in routes/auth.py).
"""
import hashlib
import hmac
import os
import secrets
import smtplib
import time
from email.message import EmailMessage

import bcrypt
# Load backend/.env before reading SMTP/OTP settings, including when app.py is launched directly.
try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from flask import request, session
from werkzeug.security import check_password_hash as _legacy_check

import db

# ------------------------------------------------------------------ config (env-overridable)
OTP_TTL = int(os.environ.get("OTP_TTL_SECONDS", "300"))          # OTP valid for 5 minutes
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))  # wrong codes before the ticket is burned
OTP_RESEND_COOLDOWN = int(os.environ.get("OTP_RESEND_COOLDOWN", "30"))
OTP_MAX_RESENDS = int(os.environ.get("OTP_MAX_RESENDS", "5"))
TICKET_TTL = int(os.environ.get("LOGIN_TICKET_TTL", "900"))      # whole login must finish within 15 min
PIN_MAX_ATTEMPTS = int(os.environ.get("PIN_MAX_ATTEMPTS", "5"))
LOCKOUT_THRESHOLD = int(os.environ.get("LOCKOUT_THRESHOLD", "8"))
LOCKOUT_SECONDS = int(os.environ.get("LOCKOUT_SECONDS", "900"))
DEV_ECHO = os.environ.get("OTP_DEV_ECHO", "0") == "1"           # tests/dev: surface the OTP instead of emailing


# ------------------------------------------------------------------ passwords
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(pw: str, stored: str):
    """Returns (ok, needs_rehash). Accepts legacy werkzeug hashes and flags them for upgrade to bcrypt on next login."""
    if not stored:
        return False, False
    if stored.startswith("$2"):                                 # bcrypt
        try:
            return bcrypt.checkpw(pw.encode("utf-8"), stored.encode("ascii")), False
        except ValueError:
            return False, False
    ok = _legacy_check(stored, pw)                              # pbkdf2/scrypt from older accounts
    return ok, ok


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_pin(pin: str, stored: str) -> bool:
    if not stored:
        return False
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), stored.encode("ascii"))
    except ValueError:
        return False


# ------------------------------------------------------------------ OTP + tickets
def _otp_hash(code: str, ticket: str) -> str:
    return hashlib.sha256(f"{ticket}:{code}".encode()).hexdigest()


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def create_ticket(user_id: int, purpose: str = "login") -> str:
    tok = secrets.token_urlsafe(32)
    db.execute("INSERT INTO login_tickets(token,user_id,purpose,created_at) VALUES(?,?,?,?)",
               (tok, user_id, purpose, int(time.time())))
    return tok


def get_ticket(tok: str, purpose: str = "login"):
    t = db.one("SELECT * FROM login_tickets WHERE token=? AND purpose=?", (tok, purpose))
    if not t or time.time() - t["created_at"] > TICKET_TTL:
        if t:
            db.execute("DELETE FROM login_tickets WHERE token=?", (tok,))
        return None
    return t


def drop_ticket(tok: str):
    db.execute("DELETE FROM login_tickets WHERE token=?", (tok,))


def issue_otp(ticket: str) -> str:
    """Generate, store (hashed) and return an OTP for a ticket. Caller emails it."""
    code = new_otp()
    db.execute("UPDATE login_tickets SET otp_hash=?, otp_expires=?, otp_attempts=0, last_sent=? WHERE token=?",
               (_otp_hash(code, ticket), int(time.time()) + OTP_TTL, int(time.time()), ticket))
    return code


def can_resend(t) -> int:
    """Seconds to wait before a resend is allowed (0 = allowed). -1 = resend limit reached."""
    if (t["resend_count"] or 0) >= OTP_MAX_RESENDS:
        return -1
    wait = OTP_RESEND_COOLDOWN - (time.time() - (t["last_sent"] or 0))
    return int(max(0, wait))


def mark_resent(ticket: str):
    db.execute("UPDATE login_tickets SET resend_count=COALESCE(resend_count,0)+1 WHERE token=?", (ticket,))


def check_otp(t, code: str):
    """Returns one of: 'ok' | 'expired' | 'bad' | 'locked'. Burns the ticket on too many wrong attempts."""
    if not t["otp_hash"] or time.time() > (t["otp_expires"] or 0):
        return "expired"
    if (t["otp_attempts"] or 0) >= OTP_MAX_ATTEMPTS:
        return "locked"
    if hmac.compare_digest(t["otp_hash"], _otp_hash(code or "", t["token"])):
        return "ok"
    db.execute("UPDATE login_tickets SET otp_attempts=COALESCE(otp_attempts,0)+1 WHERE token=?", (t["token"],))
    return "bad"


# ------------------------------------------------------------------ account lockout
def is_locked(user):
    lu = user.get("locked_until")
    return bool(lu) and time.time() < float(lu)


def lock_seconds_left(user):
    return int(float(user.get("locked_until") or 0) - time.time())


def record_failure(user_id: int):
    u = db.one("SELECT failed_logins FROM users WHERE id=?", (user_id,))
    n = (u["failed_logins"] or 0) + 1
    locked = int(time.time()) + LOCKOUT_SECONDS if n >= LOCKOUT_THRESHOLD else None
    db.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?",
               (0 if locked else n, locked, user_id))
    return locked is not None


def clear_failures(user_id: int):
    db.execute("UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=?", (user_id,))


# ------------------------------------------------------------------ audit log
def audit(event: str, user_id=None, detail: str = ""):
    try:
        ip = request.remote_addr if request else None
    except Exception:
        ip = None
    db.execute("INSERT INTO audit_log(user_id,event,ip,detail,created_at) VALUES(?,?,?,?,datetime('now'))",
               (user_id, event, ip, detail[:300]))


# ------------------------------------------------------------------ CSRF (double-submit token)
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def ensure_csrf():
    tok = session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["csrf"] = tok
    return tok


def csrf_ok() -> bool:
    sent = request.headers.get(CSRF_HEADER) or (request.get_json(silent=True) or {}).get("csrf_token")
    good = session.get("csrf")
    return bool(sent and good and hmac.compare_digest(sent, good))


# ------------------------------------------------------------------ email delivery
def mask_email(e: str) -> str:
    try:
        name, dom = e.split("@", 1)
        shown = name[0] + "***" + (name[-1] if len(name) > 1 else "")
        return f"{shown}@{dom}"
    except ValueError:
        return "your email"


class OTPDeliveryError(RuntimeError):
    """Raised when SMTP is configured but the message could not be delivered."""



def send_otp_email(to_email: str, code: str, purpose: str = "login"):
    """Show OTP in the frontend when development mode is enabled."""

    # Development mode takes priority over SMTP.
    if DEV_ECHO:
        print(f"[AuraCry][DEV OTP] {to_email} -> {code}", flush=True)
        return "dev", code

    host = (os.environ.get("SMTP_HOST") or "").strip()
    user = (os.environ.get("SMTP_USER") or "").strip()
    password = os.environ.get("SMTP_PASS") or ""
    sender = (os.environ.get("SMTP_FROM") or user).strip()

    if not host:
        raise OTPDeliveryError("No email delivery provider is configured.")

    if not user or not password or not sender:
        raise OTPDeliveryError(
            "SMTP_USER, SMTP_PASS and SMTP_FROM must be configured."
        )

    subject = "Your AuraCry verification code"
    purpose_label = "login" if purpose == "login" else "password reset"
    body = (
        f"Your AuraCry {purpose_label} verification code is: {code}\n\n"
        f"It expires in {OTP_TTL // 60} minutes. "
        "If you did not request this, ignore this email."
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(body)

    port = int(os.environ.get("SMTP_PORT", "587"))

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if os.environ.get("SMTP_STARTTLS", "1") == "1":
                smtp.starttls()
                smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(msg)
    except Exception as exc:
        raise OTPDeliveryError(
            f"Could not send verification email ({exc.__class__.__name__})."
        ) from exc

    return "email", None
