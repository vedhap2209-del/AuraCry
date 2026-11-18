"""The deep-learning branch as a service: loads the CNN+BiGRU-attention model once and turns a recording into a
probability over the SAME five classes the ML stack uses, plus per-window attention for the Pipeline Lab.

It is optional: if torch/librosa are not installed or model/cry_model.pt is missing, `available()` is False and the app
runs ML-only and says so. Nothing here ever raises into the request path; callers check `available()` first.
"""
from pathlib import Path

from config import MODEL_DIR

# Deep class order (model output) == ML code order, so no projection is needed.
CODES = ["hu", "ti", "dc", "bp", "bu"]
_state = {"model": None, "tried": False, "reason": None, "classes": None, "ck": None}


def reset():
    _state.update(model=None, tried=False, reason=None, classes=None, ck=None)


def _try_load():
    _state["tried"] = True
    try:
        import torch  # noqa
        import librosa  # noqa
    except Exception as e:
        _state["reason"] = f"No deep-learning packages installed ({e.__class__.__name__}). Install backend/requirements-deep.txt."
        return
    p = Path(MODEL_DIR) / "cry_model.pt"
    if not p.exists():
        _state["reason"] = "No trained weights (model/cry_model.pt). Train with: python -m deep.train_unified --manifest ../data/manifest.csv"
        return
    try:
        import torch
        from deep.model import CryCNNGRUModel
        ck = torch.load(p, map_location="cpu", weights_only=False)
        m = CryCNNGRUModel(**ck["arch"]); m.load_state_dict(ck["state_dict"]); m.eval()
        _state.update(model=m, classes=list(ck.get("label_order", CODES)), ck=ck, reason=None)
    except Exception as e:                               # noqa - a bad checkpoint must not break ML
        _state["reason"] = f"Deep model present but could not be loaded: {e}"


def available():
    if not _state["tried"]:
        _try_load()
    return _state["model"] is not None


def status():
    """For the admin diagnostics / fusion health."""
    if not _state["tried"]:
        _try_load()
    try:
        import torch, librosa  # noqa
        pkgs = True
    except Exception:
        pkgs = False
    return {"ready": _state["model"] is not None, "reason": _state["reason"], "packages_installed": pkgs,
            "weights_present": (Path(MODEL_DIR) / "cry_model.pt").exists(), "classes": _state["classes"],
            "covered_codes": sorted(CODES)}


def predict(path):
    """Run the CNN on up to MAX_WINDOWS loudest windows of the recording. Returns a 5-way probability (code->p over the
    ML classes), the per-window attention, and timings for the Pipeline Lab."""
    import time
    import numpy as np
    import torch
    import torch.nn.functional as F
    from deep.audio_utils import load_audio_file, prepare_waveform, windows_for_inference, logmel
    from deep import config as C

    t0 = time.perf_counter()
    y = prepare_waveform(load_audio_file(str(path)))
    wins = windows_for_inference(y)
    t_win = (time.perf_counter() - t0) * 1000
    mels = np.stack([logmel(w) for w in wins])
    t_mel = (time.perf_counter() - t0) * 1000
    X = torch.from_numpy(mels).unsqueeze(1)
    with torch.no_grad():
        logits, attn = _state["model"](X, return_attention=True)
        p = F.softmax(logits, dim=1).numpy()
    t_net = (time.perf_counter() - t0) * 1000
    mean = p.mean(0)
    dur = C.DURATION
    windows = []
    for i, w in enumerate(wins):
        top = int(p[i].argmax())
        windows.append({"start": round(i * (dur / 2), 2), "end": round(i * (dur / 2) + dur, 2),
                        "top_code": CODES[top], "top_p": float(p[i, top]),
                        "probs": {CODES[j]: float(p[i, j]) for j in range(len(CODES))},
                        "attention": [float(a) for a in attn[i].tolist()]})
    return {"probs": {CODES[j]: float(mean[j]) for j in range(len(CODES))},
            "vector": [float(v) for v in mean],
            "windows": windows, "n_windows": len(wins), "window_seconds": dur,
            "timings_ms": {"windows": round(t_win, 1), "logmel": round(t_mel - t_win, 1), "network": round(t_net - t_mel, 1)},
            "network": {"n_mels": C.N_MELS, "frames": int(mels.shape[-1]), "gru_steps": int(mels.shape[-1] // 4)}}
