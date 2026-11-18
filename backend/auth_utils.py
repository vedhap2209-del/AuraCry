"""current_user() always re-reads role + status from the database; the browser is never trusted."""
from functools import wraps
from flask import g, jsonify, session

import db


def current_user():
    if "user" in g:
        return g.user
    user = None
    uid = session.get("uid")
    if uid:
        user = db.one("SELECT * FROM users WHERE id=?", (uid,))
        if user is None or user["status"] != "ACTIVE":
            session.clear()
            user = None
    g.user = user
    return user


def public_user(u):
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"],
            "status": u["status"], "created_at": u["created_at"]}


def _unauth():
    return jsonify(error="unauthenticated", message="Please log in to continue."), 401


def _forbidden():
    return jsonify(error="access_denied", message="Access denied. You do not have permission to view this."), 403


def login_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        return _unauth() if current_user() is None else fn(*a, **kw)
    return w


def role_required(role):
    def deco(fn):
        @wraps(fn)
        def w(*a, **kw):
            u = current_user()
            if u is None:
                return _unauth()
            if u["role"] != role:
                return _forbidden()
            return fn(*a, **kw)
        return w
    return deco
