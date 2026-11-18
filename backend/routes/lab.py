"""Pipeline Lab: shows what REALLY happens, stage by stage. Nothing is stored. Any logged-in user may use it."""
import tempfile
import uuid
from pathlib import Path

import numpy as np
from flask import Blueprint, jsonify, request

from auth_utils import login_required
from config import ALLOWED_EXTENSIONS, BASE_DIR, MAX_AUDIO_MB
from ml.audio_io import AudioError
from ml.features import FEATURE_COLUMNS
from ml.service import ModelNotReady, service

bp = Blueprint("lab", __name__, url_prefix="/api/lab")
# Unified 5-class demo rows, sampled from the real test split features (same data the models were evaluated on).
LABELS = {"hu": "Hungry", "ti": "Tired", "dc": "Discomfort", "bp": "Belly Pain", "bu": "Needs Burping"}
DUR_IDX = FEATURE_COLUMNS.index("Duration")
F0_IDX = FEATURE_COLUMNS.index("Mean_F0")
_cache = {"mtime": None, "rows": None}


def dataset_rows():
    """Returns a list of {code, label, vector(19)} from real test-split cry units, a few per class."""
    p = BASE_DIR.parent / "data" / "features_ml.npz"
    if not p.exists():
        return None
    if _cache["mtime"] != p.stat().st_mtime:
        d = np.load(p, allow_pickle=True)
        X, y, split, codes = d["X"], d["y"], d["split"], list(d["codes"])
        rng = np.random.default_rng(7); rows = []
        for ci, code in enumerate(codes):
            idx = np.where((split == "test") & (y == ci))[0]
            for j in (rng.choice(idx, size=min(3, len(idx)), replace=False) if len(idx) else []):
                rows.append({"code": code, "label": LABELS.get(code, code), "vector": X[j].astype(float).tolist()})
        _cache.update(mtime=p.stat().st_mtime, rows=rows)
    return _cache["rows"]


@bp.get("/samples")
@login_required
def samples():
    rows = dataset_rows()
    if not rows:
        return jsonify(samples=[])
    out = [{"id": i, "true_code": r["code"], "true_label": r["label"],
            "duration": round(r["vector"][DUR_IDX], 2), "mean_f0": round(r["vector"][F0_IDX], 0)}
           for i, r in enumerate(rows)]
    return jsonify(samples=sorted(out, key=lambda s: s["true_label"]))


@bp.post("/run")
@login_required
def run():
    if not service.is_ready():
        return jsonify(error="model_unavailable", message="The model is not available yet."), 503
    try:
        if request.files.get("audio") is not None:
            f = request.files["audio"]
            ext = (f.filename.rsplit(".", 1)[-1] if "." in f.filename else "wav").lower()
            if ext not in ALLOWED_EXTENSIONS:
                return jsonify(error="validation", message="Unsupported file type."), 400
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / f"{uuid.uuid4().hex}.{ext}"
                f.save(p)
                if p.stat().st_size > MAX_AUDIO_MB * 1024 * 1024:
                    return jsonify(error="validation", message="File is too large."), 400
                res = service.analyze_file(p)
            return jsonify(result=res)
        body = request.get_json(silent=True) or {}
        rows = dataset_rows()
        if not rows or "row" not in body or not (0 <= int(body["row"]) < len(rows)):
            return jsonify(error="validation", message="Unknown sample row."), 400
        r = rows[int(body["row"])]
        res = service.analyze_row(np.array(r["vector"], float), {"true_label": r["label"]})
        return jsonify(result=res)
    except AudioError as e:
        return jsonify(error="invalid_audio", message=str(e)), 422
    except ModelNotReady:
        return jsonify(error="model_unavailable", message="The model is not available."), 503
