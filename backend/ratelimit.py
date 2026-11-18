"""Lightweight in-process rate limiting + spam protection (Phase 11).

Sliding-window counters kept in memory. This suits a single small instance (the free deployment target); for multiple
workers a shared store (Redis) would be needed - noted in the deployment docs. Everything degrades safely: if a limit
structure is missing we allow the request rather than erroring.
"""
import threading
import time
from collections import defaultdict, deque

from flask import jsonify, request

_lock = threading.Lock()
_hits = defaultdict(deque)                 # key -> deque[timestamps]
_inflight = {}                             # user_id -> started_at (concurrency guard)
_recent_files = {}                         # (user_id, sha1) -> timestamp (duplicate guard)


def _allow(key, limit, window):
    now = time.time()
    with _lock:
        dq = _hits[key]
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            return False, int(window - (now - dq[0])) + 1
        dq.append(now)
        return True, 0


def too_many(retry_after, message="Too many requests. Please slow down."):
    r = jsonify(error="rate_limited", message=message, retry_after=retry_after)
    r.status_code = 429
    r.headers["Retry-After"] = str(retry_after)
    return r


def client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    return (xff.split(",")[0].strip() if xff else None) or request.remote_addr or "unknown"


def limit(scope_key, n, window):
    """Imperative check used inside a view: returns a 429 response if over the limit, else None."""
    ok, retry = _allow(scope_key, n, window)
    return None if ok else too_many(retry)


# ---- analysis-specific guards -------------------------------------------------
def begin_analysis(user_id, max_concurrent_seconds=120):
    """Reject a second concurrent analysis from the same user. Returns a 429 response or None; call end_analysis after."""
    with _lock:
        started = _inflight.get(user_id)
        if started and time.time() - started < max_concurrent_seconds:
            return too_many(5, "An analysis is already running. Please wait for it to finish.")
        _inflight[user_id] = time.time()
    return None


def end_analysis(user_id):
    with _lock:
        _inflight.pop(user_id, None)


def duplicate(user_id, sha1, window=30):
    """True if this user submitted the identical file within `window` seconds (accidental double-submit / spam)."""
    now = time.time()
    with _lock:
        for k, ts in list(_recent_files.items()):
            if now - ts > 300:
                _recent_files.pop(k, None)
        key = (user_id, sha1)
        if key in _recent_files and now - _recent_files[key] < window:
            return True
        _recent_files[key] = now
        return False


def reset():
    """For tests."""
    with _lock:
        _hits.clear(); _inflight.clear(); _recent_files.clear()
