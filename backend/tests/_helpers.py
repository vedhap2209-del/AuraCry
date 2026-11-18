import io
import os
import tempfile

import numpy as np
from scipy.io import wavfile

_tmp = tempfile.mkdtemp()
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "t.db")
os.environ["OTP_DEV_ECHO"] = "1"          # tests read the OTP from the API response instead of an email
os.environ.setdefault("RATELIMIT_ENABLED", "0")   # off by default so the suite's many calls aren't throttled

from flask.testing import FlaskClient      # noqa: E402


class CsrfClient(FlaskClient):
    """Test client that mirrors a browser: it echoes the csrf_token cookie back as the X-CSRF-Token header on
    mutating requests, so the server's CSRF guard is exercised rather than bypassed."""
    def open(self, *args, **kwargs):
        if (kwargs.get("method") or "GET").upper() in ("POST", "PUT", "PATCH", "DELETE"):
            tok = None
            try:
                ck = self.get_cookie("csrf_token")
                tok = ck.value if ck else None
            except Exception:
                tok = None
            if tok:
                h = kwargs.get("headers") or {}
                if isinstance(h, dict):
                    h.setdefault("X-CSRF-Token", tok)
                else:
                    h = list(h) + [("X-CSRF-Token", tok)]
                kwargs["headers"] = h
        return super().open(*args, **kwargs)


TEST_PIN = "2468"


def three_step_login(c, email, pw, as_, pin=TEST_PIN):
    """Full three-factor login: password -> email code -> security PIN. Returns the LAST response, so a failure at any
    step is returned with its status."""
    r = c.post("/api/auth/login/identify", json={"identifier": email, "login_as": as_})
    if r.status_code != 200:
        return r
    t = r.get_json()["ticket"]
    r = c.post("/api/auth/login/password", json={"ticket": t, "password": pw})
    if r.status_code != 200 or "dev_code" not in (r.get_json() or {}):
        return r
    r = c.post("/api/auth/login/verify", json={"ticket": t, "code": r.get_json()["dev_code"]})
    if r.status_code != 200:
        return r
    return c.post("/api/auth/login/pin", json={"ticket": t, "pin": pin})


def synth_cry(sr=44100, bursts=((0.3, 1.1, 420), (1.5, 2.4, 480), (2.8, 3.7, 390)), total=4.2, noise=0.01, seed=0):
    """A cry-like signal: harmonic bursts with vibrato at known pitches."""
    t = np.arange(int(sr * total)) / sr
    y = np.zeros_like(t)
    for s, e, f in bursts:
        m = (t >= s) & (t < e); tt = t[m] - s
        ph = 2 * np.pi * np.cumsum(f * (1 + 0.08 * np.sin(2 * np.pi * 3 * tt))) / sr
        y[m] = sum(np.sin(k * ph) / k for k in range(1, 8)) * np.hanning(m.sum())
    y += noise * np.random.default_rng(seed).standard_normal(len(y))
    return (y / np.abs(y).max() * 0.8).astype(np.float32), sr


def wav_bytes(y, sr):
    b = io.BytesIO()
    wavfile.write(b, sr, (np.clip(y, -1, 1) * 32767).astype(np.int16))
    b.seek(0)
    return b
