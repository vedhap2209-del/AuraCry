"""ADMIN-only endpoints. ONE before_request check protects every route in this blueprint."""
import json
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import pandas as pd
from flask import Blueprint, abort, jsonify, request
from werkzeug.utils import secure_filename

import db
from auth_utils import current_user
from config import BASE_DIR, DATASET_DIR, MODEL_DIR
from ml.service import service
from routes.user import analysis_dict

bp = Blueprint("admin", __name__, url_prefix="/api/admin")
TRAIN_LOG = MODEL_DIR / "train.log"
_job = {"proc": None, "started": None, "args": None}


@bp.before_request
def admin_only():
    u = current_user()
    if u is None:
        return jsonify(error="unauthenticated", message="Please log in to continue."), 401
    if u["role"] != "ADMIN":
        return jsonify(error="access_denied", message="Access denied. Administrators only."), 403


def _latest_run():
    # The active service metrics are loaded from backend/model/metrics.json and
    # are the source used by the running model. Fall back to a saved DB run only
    # when that file is unavailable.
    if service.metrics:
        return service.metrics
    r = db.one("SELECT * FROM model_runs ORDER BY id DESC LIMIT 1")
    return json.loads(r["metrics_json"]) if r else None



# ---------------------------------------------------------------- dashboard
@bp.get("/stats")
def stats():
    m = _latest_run() or {}

    # Support both tabular ML metrics and deep-learning metrics
    test_metrics = m.get("test") or {}

    selected = (
        m.get("selected")
        or (test_metrics if "accuracy" in test_metrics else None)   # unified metrics: test = flat {accuracy, macro_f1, ...}
        or test_metrics.get("fused")
        or test_metrics.get("random_forest")
        or test_metrics.get("cnn_gru")
        or {}
    )

    class_counts = m.get("class_counts") or {}
    dataset_rows = m.get("n_rows")

    if dataset_rows is None and class_counts:
        dataset_rows = sum(class_counts.values())

    recent = db.q(
        "SELECT a.*, u.name user_name, u.email user_email "
        "FROM analyses a JOIN users u ON u.id=a.user_id "
        "ORDER BY a.created_at DESC, a.id DESC LIMIT 5"
    )

    return jsonify(
        total_users=db.one(
            "SELECT COUNT(*) c FROM users WHERE role='USER'"
        )["c"],

        total_analyses=db.one(
            "SELECT COUNT(*) c FROM analyses"
        )["c"],

        total_dataset=dataset_rows,

        model_name=m.get(
            "model_name",
            "CNN+BiGRU + Random Forest (Fusion)"
        ),

        model_macro_f1=(
            round(selected["macro_f1"] * 100, 1)
            if "macro_f1" in selected else None
        ),

        model_accuracy=(
            round(selected["accuracy"] * 100, 1)
            if "accuracy" in selected else None
        ),

        majority_baseline=(
            round(m["majority_baseline_accuracy"] * 100, 1)
            if "majority_baseline_accuracy" in m else None
        ),

        model_ready=service.is_ready(),

        recent=[
            analysis_dict(r, with_user=True)
            for r in recent
        ]
    )

# ---------------------------------------------------------------- users
@bp.get("/users")
def users():
    q = request.args.get("q", "").strip().lower()
    like = f"%{q}%"
    rows = db.q("SELECT u.*, (SELECT COUNT(*) FROM analyses a WHERE a.user_id=u.id) analysis_count FROM users u "
                "WHERE (?='' OR lower(name) LIKE ? OR lower(email) LIKE ?) ORDER BY created_at DESC LIMIT 500", (q, like, like))
    for r in rows:
        r.pop("password_hash", None)
    return jsonify(users=rows)


def _user_or_404(uid):
    u = db.one("SELECT * FROM users WHERE id=?", (uid,))
    if u is None:
        abort(404)
    u.pop("password_hash", None)
    return u


@bp.get("/users/<int:uid>")
def user_details(uid):
    u = _user_or_404(uid)
    rows = db.q("SELECT * FROM analyses WHERE user_id=? ORDER BY created_at DESC, id DESC", (uid,))
    u["analysis_count"] = len(rows)
    return jsonify(user=u, analyses=[analysis_dict(r) for r in rows])


@bp.patch("/users/<int:uid>/status")
def user_status(uid):
    u = _user_or_404(uid)
    status = (request.get_json(silent=True) or {}).get("status")
    if u["role"] != "USER":
        return jsonify(error="validation", message="Administrator accounts cannot be changed here."), 400
    if status not in ("ACTIVE", "INACTIVE"):
        return jsonify(error="validation", message="Invalid status."), 400
    db.execute("UPDATE users SET status=? WHERE id=?", (status, uid))
    return jsonify(user=_user_or_404(uid))


@bp.delete("/users/<int:uid>")
def user_delete(uid):
    u = _user_or_404(uid)
    if u["role"] != "USER":
        return jsonify(error="validation", message="Administrator accounts cannot be deleted."), 400
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    return jsonify(message="User deleted.")


# ---------------------------------------------------------------- dataset (CSV files)
def _csv_info(p):
    if not p.exists():
        return {"file": p.name, "exists": False, "rows": 0, "empty": True}
    if p.stat().st_size == 0:
        return {"file": p.name, "exists": True, "rows": 0, "empty": True, "bytes": 0}
    d = pd.read_csv(p)
    syn = int(d["is_synthetic"].sum()) if "is_synthetic" in d else 0
    return {"file": p.name, "exists": True, "empty": False, "bytes": p.stat().st_size, "rows": int(len(d)),
            "recordings": int(d["Original_File"].nunique()), "synthetic_rows": syn,
            "classes": {k: int(v) for k, v in d["Reason"].value_counts().items()}}


@bp.get("/dataset")
def dataset():
    return jsonify(train=_csv_info(DATASET_DIR / "balanced_full_dataset_clean.csv"),
                   test=_csv_info(DATASET_DIR / "test_dataset_clean.csv"))


@bp.post("/dataset/upload")
def dataset_upload():
    role = request.form.get("role")
    f = request.files.get("file")
    if role not in ("train", "test") or f is None:
        return jsonify(error="validation", message="Choose 'train' or 'test' and a CSV file."), 400
    if not (f.filename or "").lower().endswith(".csv"):
        return jsonify(error="validation", message="Only .csv files are accepted."), 400
    tmp = DATASET_DIR / f".upload_{int(time.time())}.csv"
    f.save(tmp)
    try:
        from ml.features import FEATURE_COLUMNS
        head = pd.read_csv(tmp, nrows=5)
        miss = [c for c in FEATURE_COLUMNS + ["Reason", "Original_File"] if c not in head.columns]
        if miss:
            tmp.unlink(missing_ok=True)
            return jsonify(error="validation", message="CSV is missing columns: " + ", ".join(miss)), 400
    except Exception:
        tmp.unlink(missing_ok=True)
        return jsonify(error="validation", message="This file is not a readable CSV."), 400
    target = DATASET_DIR / ("balanced_full_dataset_clean.csv" if role == "train" else "test_dataset_clean.csv")
    tmp.replace(target)
    return jsonify(info=_csv_info(target))


# ---------------------------------------------------------------- model
@bp.get("/model/performance")
def performance():
    m = _latest_run() or {}
    # This project stores tabular stack metrics in metrics.json and CNN+BiGRU
    # evaluation separately in dl_metrics.json. Return both in one stable shape.
    dl_path = MODEL_DIR / "dl_metrics.json"
    dl = {}
    if dl_path.exists():
        try:
            dl = json.loads(dl_path.read_text())
        except (OSError, json.JSONDecodeError):
            dl = {}
    m = dict(m)
    m["deep_learning"] = {
        "test": dl.get("test") or {},
        "validation": dl.get("val") or {},
        "n_train": dl.get("n_train"),
        "n_val": dl.get("n_val"),
        "n_test": dl.get("n_test"),
        "best_val_macro_f1": dl.get("best_val_macro_f1"),
    }
    runs = db.q("SELECT id, model_name, accuracy, macro_f1, created_at FROM model_runs ORDER BY id DESC LIMIT 10")
    return jsonify(metrics=m, runs=runs, model_ready=service.is_ready())


@bp.post("/model/reload")
def reload_model():
    return jsonify(model_ready=service.load(), message=service.error)


def _job_status():
    p = _job["proc"]
    running = p is not None and p.poll() is None
    tail = TRAIN_LOG.read_text(errors="ignore")[-2500:] if TRAIN_LOG.exists() else ""
    return {"running": running, "exit_code": None if p is None or running else p.returncode,
            "started": _job["started"], "log_tail": tail}


@bp.post("/model/retrain")
def retrain():
    if _job_status()["running"]:
        return jsonify(error="busy", message="Training is already running."), 409
    body = request.get_json(silent=True) or {}
    args = [sys.executable, "-u", "-m", "ml.tabular_train"]
    if body.get("drop_unclear", True):
        args += ["--drop", "dk"]
    if body.get("quick", True):
        args += ["--quick"]
    TRAIN_LOG.parent.mkdir(exist_ok=True)
    _job.update(proc=subprocess.Popen(args, cwd=str(BASE_DIR), stdout=open(TRAIN_LOG, "w"), stderr=subprocess.STDOUT),
                started=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), args=args)
    return jsonify(message="Training started.", **_job_status()), 202


@bp.get("/model/train-status")
def train_status():
    st = _job_status()
    if st["exit_code"] == 0 and _job.get("args") and not _job.get("recorded"):
        _job["recorded"] = True
        service.load()
        m = service.metrics or {}
        if m:
            test = m.get("test") or {}
            selected = m.get("selected") or (test if "accuracy" in test else
                       test.get("fused") or test.get("random_forest") or test.get("cnn_gru") or {})
            if selected:
                db.execute("INSERT INTO model_runs(model_name,accuracy,balanced_accuracy,macro_f1,metrics_json) VALUES(?,?,?,?,?)",
                           (m.get("model_name", "AuraCry ML model"), selected.get("accuracy"),
                            selected.get("balanced_accuracy"), selected.get("macro_f1"), json.dumps(m)))
    if st["running"]:
        _job["recorded"] = False
    return jsonify(**st)


# ---------------------------------------------------------------- records + reports
@bp.get("/analyses")
def records():
    q, cat = request.args.get("q", "").strip().lower(), request.args.get("category", "")
    like = f"%{q}%"
    rows = db.q("SELECT a.*, u.name user_name, u.email user_email FROM analyses a JOIN users u ON u.id=a.user_id "
                "WHERE (?='' OR lower(a.audio_filename) LIKE ? OR lower(u.name) LIKE ? OR lower(u.email) LIKE ? OR ('ac-'||printf('%05d',a.id)) LIKE ?)"
                " AND (?='' OR a.predicted_category=?) ORDER BY a.created_at DESC, a.id DESC LIMIT 500",
                (q, like, like, like, like, cat, cat))
    return jsonify(analyses=[analysis_dict(r, with_user=True) for r in rows])


@bp.get("/analyses/<int:aid>")
def record(aid):
    r = db.one("SELECT a.*, u.name user_name, u.email user_email FROM analyses a JOIN users u ON u.id=a.user_id WHERE a.id=?", (aid,))
    if r is None:
        abort(404)
    return jsonify(analysis=analysis_dict(r, full=True, with_user=True))


@bp.get("/reports")
def reports():
    rows = db.q("SELECT predicted_category c, created_at t, result_json FROM analyses")
    labels = {}
    dist = Counter()
    for r in rows:
        labels[r["c"]] = json.loads(r["result_json"]).get("label", r["c"])
        dist[r["c"]] += 1
    now = datetime.now(timezone.utc)

    def bucket(days, fmt):
        out = {}
        for i in range(days - 1, -1, -1):
            out[(now - timedelta(days=i)).strftime(fmt)] = 0
        return out
    daily, weekly, monthly = bucket(14, "%d %b"), {}, {}
    for r in rows:
        t = datetime.strptime(r["t"][:19], "%Y-%m-%d %H:%M:%S")
        k = t.strftime("%d %b")
        if k in daily:
            daily[k] += 1
        weekly[t.strftime("%G-W%V")] = weekly.get(t.strftime("%G-W%V"), 0) + 1
        monthly[t.strftime("%b %Y")] = monthly.get(t.strftime("%b %Y"), 0) + 1
    conf = db.one("SELECT AVG(confidence) a FROM analyses")["a"]
    return jsonify(total_analyses=len(rows), total_users=db.one("SELECT COUNT(*) c FROM users WHERE role='USER'")["c"],
                   avg_confidence=None if conf is None else round(conf * 100, 1),
                   distribution=[{"category": k, "label": labels[k], "count": v} for k, v in dist.most_common()],
                   daily=[{"label": k, "count": v} for k, v in daily.items()],
                   weekly=[{"label": k, "count": v} for k, v in sorted(weekly.items())[-12:]],
                   monthly=[{"label": k, "count": v} for k, v in list(monthly.items())[-12:]])
