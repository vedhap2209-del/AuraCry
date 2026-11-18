"""Fusion of the two branches. Both the ML stack and the CNN+BiGRU output the SAME five classes in the SAME order
(codes hu, ti, dc, bp, bu), so fusion is a plain weighted average of the two probability vectors:

    fused = (1 - w) * ml + w * dl          w = weight of the deep branch (0 = ML only, 1 = DL only)

`w` is tuned on the validation split by Phase 6 (`ml.fuse_eval`) and stored in model/fusion.json. It is never tuned on
the test set. If the file is missing/broken, or the DL branch is unavailable, the app falls back to ML only.
"""
import json
import os

import numpy as np

from config import MODEL_DIR

CONFIG_PATH = MODEL_DIR / "fusion.json"
DEFAULT_WEIGHT = 0.5


def _clamp(w):
    return float(min(max(float(w), 0.0), 1.0))


def load_config():
    try:
        c = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        c["dl_weight"] = _clamp(c["dl_weight"])
        return c
    except Exception:                                   # a broken file must never break an analysis
        return None


def weight_source():
    """(weight, source): 'env' (DEEP_WEIGHT override) | 'tuned' (fusion.json) | 'default'."""
    raw = os.environ.get("DEEP_WEIGHT")
    if raw not in (None, ""):
        try:
            return _clamp(raw), "env"
        except ValueError:
            pass
    c = load_config()
    if c is not None:
        return c["dl_weight"], "tuned"
    return DEFAULT_WEIGHT, "default"


def deep_weight():
    return weight_source()[0]


def fuse(ml, dl, w=None):
    """ml, dl: probability vectors over the same 5 classes in the same order. Returns the fused vector and a summary."""
    ml = np.asarray(ml, float); dl = np.asarray(dl, float)
    if w is None:
        w, _ = weight_source()
    w = _clamp(w)
    fused = (1 - w) * ml + w * dl
    s = fused.sum()
    if s > 0:
        fused = fused / s
    return fused, {"weight": w, "ml_top": int(np.argmax(ml)), "dl_top": int(np.argmax(dl)),
                   "fused_top": int(np.argmax(fused)), "agree": int(np.argmax(ml)) == int(np.argmax(dl))}


def status():
    """For the admin page / health check."""
    w, src = weight_source()
    return {"weight": w, "source": src, "config": load_config()}
