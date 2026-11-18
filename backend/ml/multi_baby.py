"""Optional experimental two-source separation for overlapping infant cries.

The bundled pretrained separator was trained on speech mixtures, not infant cries.
Treat its outputs as candidate sources, not verified baby identities. Validate on
real two-baby recordings before using this in a clinical or production setting.
"""
import os
import tempfile
from pathlib import Path

import numpy as np


def enabled():
    return os.environ.get("MULTI_BABY_ENABLED", "0").strip() == "1"


def _load_separator():
    try:
        from speechbrain.inference.separation import SepformerSeparation
    except Exception as exc:
        raise RuntimeError(
            "Multi-baby separation packages are not installed. Install backend/requirements-multibaby.txt."
        ) from exc

    cache = Path(os.environ.get("MULTI_BABY_MODEL_DIR", "storage/sepformer-whamr16k")).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    return SepformerSeparation.from_hparams(
        source="speechbrain/sepformer-whamr16k",
        savedir=str(cache),
        run_opts={"device": "cpu"},
    )


_separator = None


def analyze_candidates(audio_path, analysis_service):
    """Return separate analyses for two candidate sources, or a safe status without changing base result."""
    global _separator
    if not enabled():
        return {"status": "disabled", "message": "Set MULTI_BABY_ENABLED=1 to enable experimental source separation."}

    try:
        if _separator is None:
            _separator = _load_separator()
        separated = _separator.separate_file(str(audio_path))
        if hasattr(separated, "detach"):
            separated = separated.detach().cpu().numpy()
        separated = np.asarray(separated, dtype=np.float32)
        # SpeechBrain SepFormer output convention: [batch, samples, speakers].
        if separated.ndim == 3:
            separated = separated[0]
        if separated.ndim != 2:
            raise RuntimeError(f"Unexpected separator output shape: {separated.shape}")
        if separated.shape[0] == 2 and separated.shape[1] > 2:
            separated = separated.T
        if separated.shape[1] < 2:
            raise RuntimeError("The separator did not return two source channels.")

        candidates = []
        for idx in range(2):
            signal = np.nan_to_num(separated[:, idx])
            peak = float(np.max(np.abs(signal))) if signal.size else 0.0
            rms = float(np.sqrt(np.mean(signal ** 2))) if signal.size else 0.0
            if peak < 1e-5 or rms < 1e-5:
                continue
            signal = (signal / max(peak, 1e-8) * 0.95).astype(np.float32)
            candidates.append((idx, signal, rms))

        if len(candidates) != 2:
            return {"status": "not_separated", "message": "Two usable cry sources could not be isolated; the original single-recording analysis is shown."}

        # Avoid claiming two sources when the outputs are effectively duplicates.
        a, b = candidates[0][1], candidates[1][1]
        n = min(len(a), len(b))
        if n < 8000:
            return {"status": "not_separated", "message": "The separated sources were too short for reliable individual analysis."}
        corr = float(abs(np.corrcoef(a[:n], b[:n])[0, 1])) if np.std(a[:n]) > 1e-8 and np.std(b[:n]) > 1e-8 else 1.0
        if not np.isfinite(corr) or corr > 0.985:
            return {"status": "not_separated", "message": "The separator did not produce two sufficiently distinct signals."}

        from scipy.io import wavfile
        baby_results = []
        with tempfile.TemporaryDirectory(prefix="auracry_babies_") as tmp:
            for output_index, (source_index, signal, _) in enumerate(candidates, start=1):
                candidate_path = Path(tmp) / f"baby_{output_index}.wav"
                wavfile.write(candidate_path, 16000, signal)
                try:
                    result = analysis_service.analyze_file(candidate_path)
                except Exception as exc:
                    baby_results.append({
                        "baby": output_index,
                        "status": "analysis_failed",
                        "message": f"Separated source could not be analyzed ({exc.__class__.__name__}).",
                    })
                    continue
                baby_results.append({
                    "baby": output_index,
                    "status": "analyzed",
                    "category": result.get("category"),
                    "label": result.get("label"),
                    "confidence": result.get("confidence"),
                    "uncertain": result.get("uncertain"),
                    "probabilities": result.get("probabilities", {}),
                    "n_units": result.get("n_units", 0),
                    "duration_sec": result.get("duration_sec"),
                })

        if not any(x["status"] == "analyzed" for x in baby_results):
            return {"status": "analysis_failed", "message": "Two candidate sources were separated, but neither could be analyzed reliably."}
        return {
            "status": "experimental",
            "method": "SpeechBrain SepFormer (pretrained speech-mixture separator)",
            "source_count": 2,
            "baby_analyses": baby_results,
            "notice": "Candidate-source separation is experimental: the pretrained model was not trained specifically on infant cries. Baby labels are anonymous source labels, not identity recognition.",
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": str(exc)[:240],
        }
