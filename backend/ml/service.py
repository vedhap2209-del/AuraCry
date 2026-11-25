
"""Loads the trained stack once and turns audio (or one dataset row) into a full result + TRACE.

Pipeline for a recording:
  1 decode        file -> mono 16 kHz waveform
  2 validate      check audio quality and possible non-cry audio
  3 segment       find cry units (voiced bursts) -> units
  4 features      19 acoustic features per unit (pitch, HNR, 13 MFCC)
  5 random forest probabilities per unit
  6 adaboost probabilities per unit
  7 logistic regression meta-learner
  8 aggregate, explain and provide advice

No fake results: if the model file does not exist, is_ready() is False.
"""

import threading
import time
from pathlib import Path

import joblib
import json
import numpy as np

from config import MODEL_DIR, SPECTROGRAM_DIR
from ml import advice as advice_mod
from ml import explain as explain_mod
from ml import features as F
from ml.audio_io import AudioError, load_audio
from ml.stack import add_engineered

CODE_TO_ADVICE = {
    "hu": "Hungry",
    "ti": "Sleepy",
    "dc": "Fussy",
    "bu": "Burp",
    "bp": "Distress",
    "dk": "Uncertain",
    "sc": "Scared",
    "ch": "Cold / Hot",
    "lo": "Lonely"
}

STAGE_TITLES = {
    "rf": "Random Forest",
    "ada": "AdaBoost",
    "et": "Extra Trees",
    "hgb": "Gradient Boosting"
}

LOW_CONF, MIN_MARGIN = 0.40, 0.06


class ModelNotReady(Exception):
    pass


class Service:

    def __init__(self):
        self.bundle = None
        self.metrics = None
        self.error = "Model not loaded yet."
        self._lock = threading.Lock()

    # ---------------------------------------------------------
    # MODEL LOADING
    # ---------------------------------------------------------

    def load(self):
        p = MODEL_DIR / "stack.joblib"
        self.bundle, self.metrics = None, None

        if not p.exists():
            self.error = "Trained model not found. Run: python -m ml.tabular_train"
            return False

        try:
            self.bundle = joblib.load(p)

            mp = MODEL_DIR / "metrics.json"
            self.metrics = json.loads(mp.read_text()) if mp.exists() else None

            self.error = None
            return True

        except Exception as e:
            self.error = f"Could not load model: {e}"
            return False

    def is_ready(self):
        return self.bundle is not None

    @property
    def codes(self):
        return self.bundle["codes"]

    @property
    def labels(self):
        return self.bundle["labels"]

    # ---------------------------------------------------------
    # PREDICTION
    # ---------------------------------------------------------

    def _predict_units(self, V):
        """V: (n_units, 19) -> per-stage probabilities and final probabilities."""

        model = self.bundle["model"]
        X = add_engineered(V)

        with self._lock:
            stages, final = model.trace(X)

        return stages, final

    # ---------------------------------------------------------
    # BUILD RESULT
    # ---------------------------------------------------------

    def _result_from_vectors(self, V, spans, trace, extra):

        t = time.perf_counter()

        stages, final = self._predict_units(V)

        codes, labels = self.codes, self.labels
        model = self.bundle["model"]

        step = lambda key, title, detail, t0: trace.append({
            "key": key,
            "title": title,
            "detail": detail,
            "ms": round((time.perf_counter() - t0) * 1000, 1)
        })

        names = model.stage_names

        stage_mean = {
            n: stages[n].mean(0)
            for n in names
        }

        final_mean = final.mean(0)

        if self.bundle.get("absent_codes"):
            pass

        order = np.argsort(-final_mean)

        top, run = int(order[0]), int(order[1])

        pred, runner = codes[top], codes[run]

        conf = float(final_mean[top])
        margin = float(final_mean[top] - final_mean[run])

        uncertain = conf < LOW_CONF or margin < MIN_MARGIN

        def top3(p):
            o = np.argsort(-p)[:3]

            return [
                {
                    "code": codes[i],
                    "label": labels[codes[i]],
                    "p": round(float(p[i]), 4)
                }
                for i in o
            ]

        rf_t0 = time.perf_counter()

        units_out = []

        for i in range(len(V)):

            d = {
                "index": i,
                "features": {
                    k: round(float(v), 3)
                    for k, v in zip(F.FEATURE_COLUMNS, V[i])
                },
                "final": top3(final[i])
            }

            if spans is not None:
                d["start"], d["end"] = spans[i]

            for n in names:
                d[n] = top3(stages[n][i])

            units_out.append(d)

        step(
            "rf",
            "Stage 1 - Random Forest",
            f"{len(V)} unit(s); top vote for the recording: "
            f"{labels[codes[int(np.argmax(stage_mean['rf']))]]} "
            f"({stage_mean['rf'].max() * 100:.0f}%)",
            rf_t0
        )

        step(
            "ada",
            "Stage 2 - AdaBoost",
            f"top vote: {labels[codes[int(np.argmax(stage_mean['ada']))]]} "
            f"({stage_mean['ada'].max() * 100:.0f}%)",
            rf_t0
        )

        w = model.meta_weights()

        step(
            "meta",
            "Stage 3 - Logistic Regression",
            "combined the stage outputs in log-odds space; reliance: "
            + ", ".join(
                f"{STAGE_TITLES.get(k, k)} {v * 100:.0f}%"
                for k, v in w.items()
            ),
            rf_t0
        )

        mean_feat = dict(zip(F.FEATURE_COLUMNS, V.mean(0)))

        t_ex = time.perf_counter()

        expl = explain_mod.build(
            mean_feat,
            self.bundle["profiles"],
            pred,
            runner,
            labels,
            {
                codes[i]: float(final_mean[i])
                for i in range(len(codes))
            }
        )

        drift = explain_mod.drift(
            F.FEATURE_COLUMNS,
            V.mean(0),
            self.bundle["profiles"]
        )

        step(
            "explain",
            "Explain",
            f"{len(expl['supporting'])} supporting and "
            f"{len(expl['conflicting'])} conflicting properties; "
            f"{len(drift)} feature(s) outside the training range",
            t_ex
        )

        t_ad = time.perf_counter()

        ev = [s["text"] for s in expl["supporting"]]

        adv = advice_mod.get_advice(
            CODE_TO_ADVICE.get(pred, "Uncertain"),
            conf,
            ev,
            uncertain=uncertain
        )

        step(
            "advice",
            "Suggestions",
            f"source: {adv['source']}; {len(adv['videos'])} video link(s)",
            t_ad
        )

        per_class = (self.metrics or {}).get("per_class", {})

        res = {
            "category": pred,
            "label": labels[pred],
            "confidence": round(conf, 4),
            "uncertain": bool(uncertain),
            "runner_up": runner,
            "runner_up_label": labels[runner],

            "probabilities": {
                labels[codes[i]]: round(float(final_mean[i]), 4)
                for i in range(len(codes))
            },

            "stages": {
                n: {
                    labels[codes[i]]: round(float(stage_mean[n][i]), 4)
                    for i in range(len(codes))
                }
                for n in names
            },

            "stage_titles": {
                n: STAGE_TITLES.get(n, n)
                for n in names
            },

            "stage_reliance": w,
            "units": units_out,
            "n_units": len(V),
            "explanation": expl,
            "advice": adv,
            "drift": drift,
            "trace": trace,

            "validation": {
                "model": (self.metrics or {}).get("model_name"),

                "class_recall": per_class.get(
                    labels[pred], {}
                ).get("recall"),

                "class_precision": per_class.get(
                    labels[pred], {}
                ).get("precision"),

                "class_recordings": (
                    (self.metrics or {}).get("class_recordings")
                    or {}
                ).get(labels[pred]),

                "class_share": (
                    lambda cc, n: (
                        cc.get(labels[pred], 0) / n
                    ) if n else None
                )(
                    (self.metrics or {}).get("class_counts") or {},
                    (self.metrics or {}).get("n_rows") or 0
                )
            }
        }

        res.update(extra)

        # Keep ML-only result alongside the fused result.
        res["ml"] = {
            "probabilities": dict(res["probabilities"]),
            "category": pred,
            "label": labels[pred],
            "confidence": round(conf, 4)
        }

        res["pipeline"] = "ml"

        res["fusion"] = {
            "mode": "ml_only",
            "dl_weight": 0.0,
            "fused": dict(res["probabilities"])
        }

        res["deep"] = {
            "status": "unavailable",
            "reason": None
        }

        res["_ml_mean"] = [float(v) for v in final_mean]

        res["_mean_feat"] = {
            k: float(v)
            for k, v in zip(F.FEATURE_COLUMNS, V.mean(0))
        }

        return res

    # ---------------------------------------------------------
    # DEEP LEARNING FUSION
    # ---------------------------------------------------------

    def _decide(self, vec):

        codes, labels = self.codes, self.labels

        vec = np.asarray(vec, float)
        order = np.argsort(-vec)

        top, run = int(order[0]), int(order[1])

        conf = float(vec[top])
        margin = float(vec[top] - vec[run])

        return {
            "category": codes[top],
            "label": labels[top] if isinstance(labels, list) else labels[codes[top]],
            "confidence": round(conf, 4),
            "uncertain": bool(conf < LOW_CONF or margin < MIN_MARGIN),
            "runner_up": codes[run],
            "runner_up_label": labels[codes[run]],

            "probabilities": {
                labels[codes[i]]: round(float(vec[i]), 4)
                for i in range(len(codes))
            }
        }

    def _fuse_into(self, res, path, trace):
        """Run the DL branch and fuse it with the ML result."""

        from ml import deep_service, fusion

        codes, labels = self.codes, self.labels

        if not deep_service.available():

            res["deep"] = {
                "status": "unavailable",
                "reason": deep_service.status().get("reason")
            }

            trace.append({
                "key": "dl_off",
                "title": "Deep model",
                "branch": "dl",
                "ms": 0.0,
                "detail": res["deep"]["reason"]
                or "CNN+BiGRU not available; running ML only"
            })

            return res

        t = time.perf_counter()

        try:
            dp = deep_service.predict(path)

        except Exception as e:

            res["deep"] = {
                "status": "error",
                "reason": str(e)
            }

            trace.append({
                "key": "dl_off",
                "title": "Deep model failed",
                "branch": "dl",
                "ms": 0.0,
                "detail": str(e)[:160]
            })

            return res

        dl_vec = np.array([
            dp["probs"].get(c, 0.0)
            for c in codes
        ], float)

        ml_vec = np.array(res["_ml_mean"], float)

        fused, info = fusion.fuse(ml_vec, dl_vec, None)

        w = info["weight"]

        trace.append({
            "key": "dl_net",
            "title": "Deep branch - CNN + BiGRU",
            "branch": "dl",
            "ms": round(dp["timings_ms"]["network"], 1),

            "detail": (
                f"{dp['n_windows']} window(s); top: "
                f"{labels[codes[int(np.argmax(dl_vec))]]} "
                f"({dl_vec.max() * 100:.0f}%)"
            )
        })

        trace.append({
            "key": "fusion",
            "title": "Fuse ML + DL",
            "branch": "fusion",
            "ms": 0.0,

            "detail": (
                f"weighted average, deep weight {w:.2f} "
                f"({(1-w)*100:.0f}% ML / {w*100:.0f}% DL); "
                f"{'both branches agree' if info['agree'] else 'branches disagree, fused decision used'}"
            )
        })

        dec = self._decide(fused)

        old_top = res["category"]

        res.update(dec)

        res["pipeline"] = "ml+dl"

        res["deep"] = {
            "status": "ok",
            "label": labels[codes[int(np.argmax(dl_vec))]],

            "probabilities": {
                labels[codes[i]]: round(float(dl_vec[i]), 4)
                for i in range(len(codes))
            },

            "windows": dp["windows"],
            "n_windows": dp["n_windows"],
            "window_seconds": dp["window_seconds"],
            "timings_ms": dp["timings_ms"],
            "network": dp["network"],
            "reason": None
        }

        res["fusion"] = {
            "mode": "ml+dl",
            "dl_weight": round(w, 3),
            "agree": info["agree"],
            "fused": dict(dec["probabilities"])
        }

        if dec["category"] != old_top:
            self._reexplain(res)

        return res

    def _reexplain(self, res):

        pred, runner = res["category"], res["runner_up"]
        labels = self.labels

        probs = {
            c: res["probabilities"].get(labels[c], 0.0)
            for c in self.codes
        }

        expl = explain_mod.build(
            res["_mean_feat"],
            self.bundle["profiles"],
            pred,
            runner,
            labels,
            probs
        )

        res["explanation"] = expl

        ev = [s["text"] for s in expl["supporting"]]

        res["advice"] = advice_mod.get_advice(
            CODE_TO_ADVICE.get(pred, "Uncertain"),
            res["confidence"],
            ev,
            uncertain=res["uncertain"]
        )

    # ---------------------------------------------------------
    # ANALYZE AUDIO FILE
    # ---------------------------------------------------------

    def analyze_file(self, path, spectrogram_out=None):

        if not self.is_ready():
            raise ModelNotReady(self.error)

        trace = []

        # STEP 1: Decode audio
        t = time.perf_counter()

        y, dur = load_audio(str(path))

        trace.append({
            "key": "decode",
            "title": "Decode audio",
            "ms": round((time.perf_counter() - t) * 1000, 1),
            "detail": f"{dur:.1f} s, converted to mono 16 kHz and peak-normalised"
        })

        # STEP 2: Validate audio BEFORE classification
        from ml import upload_validation, denoise

        quality_warnings = upload_validation.quality_warnings(
            y,
            F.SR_PITCH
        )

        # Reject recordings flagged by the existing non-cry heuristic.
        # This is a temporary safeguard, not a definitive cry detector.
        if any(
            w.get("code") == "maybe_not_cry"
            for w in quality_warnings
        ):

            raise AudioError(
                "This recording does not appear to be a clear infant cry. "
                "It may contain human speech or another sound. "
                "Please upload a clear baby crying recording."
            )

        # STEP 3: Segment possible cry units
        t = time.perf_counter()

        spans = F.segment_cry_units(y)

        fallback = False

        if not spans and len(y) >= int(0.4 * F.SR_PITCH):

            # Short single-vocalisation clips:
            # use the loudest approximately 1.5-second window.
            n = int(1.5 * F.SR_PITCH)

            if len(y) <= n:

                spans = [
                    (0.0, round(len(y) / F.SR_PITCH, 3))
                ]

            else:

                starts = range(
                    0,
                    len(y) - n,
                    n // 2
                )

                s = max(
                    starts,
                    key=lambda k: float(
                        np.sum(y[k:k + n] ** 2)
                    )
                )

                spans = [
                    (
                        round(s / F.SR_PITCH, 3),
                        round((s + n) / F.SR_PITCH, 3)
                    )
                ]

            fallback = True

        trace.append({
            "key": "segment",
            "title": "Find cry units",
            "branch": "shared",
            "ms": round((time.perf_counter() - t) * 1000, 1),

            "detail": (
                f"{len(spans)} cry unit(s) found"
                if not fallback
                else "no distinct bursts; using the loudest window"
            ) + (
                ": " + ", ".join(
                    f"{s:.2f}-{e:.2f}s"
                    for s, e in spans[:6]
                ) if spans else ""
            )
        })

        if not spans:

            raise AudioError(
                "I could not hear a clear cry in this recording. "
                "Try again closer to the baby with less background noise."
            )

        # STEP 4: Extract features
        t = time.perf_counter()

        units = []

        for s, e in spans:

            v = F.unit_features(y, s, e)

            if v is not None and np.all(np.isfinite(v)):
                units.append((s, e, v))

        trace.append({
            "key": "features",
            "title": "Extract acoustic features",
            "ms": round((time.perf_counter() - t) * 1000, 1),

            "detail": (
                f"{len(units)} of {len(spans)} unit(s) had a measurable pitch; "
                "19 features each (pitch, HNR, 13 MFCC)"
            )
        })

        if not units:

            raise AudioError(
                "The sound has no measurable pitch "
                "(it may be speech-free noise or too quiet). "
                "Try a clearer recording."
            )

        V = np.vstack([
            u[2]
            for u in units
        ])

        sp = [
            (u[0], u[1])
            for u in units
        ]

        extra = {
            "duration_sec": round(float(dur), 2),
            "waveform": F.waveform_envelope(y, F.SR_PITCH),
            "waveform_seconds": round(len(y) / F.SR_PITCH, 3),
            "source": "audio"
        }

        # STEP 5: Run ML classification
        res = self._result_from_vectors(
            V,
            sp,
            trace,
            extra
        )

        # STEP 6: Run deep-learning branch and fusion
        self._fuse_into(
            res,
            path,
            trace
        )

        # STEP 7: Add audio quality information
        res["quality_warnings"] = quality_warnings

        res["quality"] = denoise.quality_score(
            y,
            F.SR_PITCH
        )

        # STEP 8: Save spectrogram if requested
        if spectrogram_out:

            self.save_spectrogram(
                y,
                sp,
                spectrogram_out
            )

        res.pop("_ml_mean", None)
        res.pop("_mean_feat", None)

        return res

    # ---------------------------------------------------------
    # ANALYZE DATASET ROW
    # ---------------------------------------------------------

    def analyze_row(self, row_vector, meta):
        """Run ONE real feature row from the dataset through the same stages."""

        if not self.is_ready():
            raise ModelNotReady(self.error)

        V = np.asarray(
            row_vector,
            float
        ).reshape(1, -1)

        trace = [{
            "key": "dataset",
            "title": "Take a real row from the dataset",
            "ms": 0.0,

            "detail": (
                f"{meta.get('file', '')[:18]}... "
                f"unit {meta.get('cu', '')}: "
                "the 19 features were already measured"
            )
        }]

        res = self._result_from_vectors(
            V,
            None,
            trace,
            {
                "duration_sec": float(V[0, 0]),
                "waveform": [],
                "source": "dataset_row",
                "waveform_seconds": 0,
                "true_label": meta.get("true_label")
            }
        )

        res["deep"] = {
            "status": "needs_audio",
            "reason": (
                "the CNN needs the audio; "
                "a pre-computed feature row cannot run it"
            )
        }

        res.pop("_ml_mean", None)
        res.pop("_mean_feat", None)

        return res

    # ---------------------------------------------------------
    # SAVE SPECTROGRAM
    # ---------------------------------------------------------

    @staticmethod
    def save_spectrogram(y16, spans, out_path):

        import matplotlib

        matplotlib.use("Agg")

        from matplotlib.figure import Figure

        y8 = F.resample(
            y16,
            F.SR_PITCH,
            F.SR_MFCC
        )

        S = F.mel_spectrogram_db(y8)

        dur = len(y8) / F.SR_MFCC

        fig = Figure(
            figsize=(6, 3),
            dpi=110
        )

        ax = fig.subplots()

        im = ax.imshow(
            S,
            origin="lower",
            aspect="auto",
            cmap="magma",
            extent=[0, dur, 50, 4000]
        )

        for s, e in spans:
            ax.axvspan(
                s,
                e,
                ymin=0,
                ymax=0.04,
                color="#7CFC9A"
            )

        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Frequency (Hz)")

        fig.colorbar(
            im,
            ax=ax,
            label="dB"
        )

        fig.tight_layout()

        fig.savefig(out_path)


service = Service()
