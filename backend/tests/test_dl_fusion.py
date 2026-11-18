"""The two-branch serving pipeline: the CNN+BiGRU branch runs on the same audio as the ML stack and its vote is fused
into the answer. The CNN needs torch + weights, so here the deep branch is replaced by a deterministic stand-in; what
is verified is everything around it - both branches run, the fusion maths, the trace, and the graceful fallbacks.
Run from backend/:  python -m unittest tests.test_dl_fusion -v"""
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from tests import _helpers as H
from ml import deep_service
from ml.service import service

CODES = ["hu", "ti", "dc", "bp", "bu"]


def fake_status(ready=True, reason=None):
    return {"ready": ready, "reason": reason, "packages_installed": ready, "weights_present": ready,
            "classes": ["hungry", "tired", "discomfort", "belly_pain", "burping"], "covered_codes": sorted(CODES)}


def fake_predict_factory(top="ti"):
    def fake_predict(path):
        p = {c: 0.05 for c in CODES}; p[top] = 1 - 0.05 * 4
        vec = [p[c] for c in CODES]
        win = {"start": 0.0, "end": 3.0, "top_code": top, "top_p": p[top], "probs": p, "attention": [0.1] * 47}
        return {"probs": p, "vector": vec, "windows": [win, dict(win, start=1.5, end=4.5)], "n_windows": 2,
                "window_seconds": 3.0, "timings_ms": {"windows": 1.0, "logmel": 2.0, "network": 3.0},
                "network": {"n_mels": 128, "frames": 188, "gru_steps": 47}}
    return fake_predict


class TwoBranchPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert service.load(), service.error
        y, sr = H.synth_cry()
        cls.wav = os.path.join(tempfile.mkdtemp(), "cry.wav")
        open(cls.wav, "wb").write(H.wav_bytes(y, sr).read())

    def run_pipeline(self, top="ti", weight="0.5"):
        with mock.patch.object(deep_service, "available", return_value=True), \
             mock.patch.object(deep_service, "status", return_value=fake_status()), \
             mock.patch.object(deep_service, "predict", side_effect=fake_predict_factory(top)), \
             mock.patch.dict(os.environ, {"DEEP_WEIGHT": weight}):
            return service.analyze_file(self.wav)

    def test_both_branches_run_then_fuse(self):
        res = self.run_pipeline()
        keys = [t["key"] for t in res["trace"]]
        for k in ("decode", "segment", "features", "rf", "ada", "meta", "dl_net", "fusion"):
            self.assertIn(k, keys)
        self.assertEqual(res["pipeline"], "ml+dl")
        self.assertEqual(res["deep"]["status"], "ok")
        self.assertEqual(res["deep"]["n_windows"], 2)
        self.assertEqual(len(res["deep"]["windows"][0]["attention"]), 47)
        self.assertEqual(res["fusion"]["mode"], "ml+dl")
        self.assertEqual(res["fusion"]["dl_weight"], 0.5)

    def test_fused_probs_are_the_weighted_average_and_reported(self):
        res = self.run_pipeline(top="ti", weight="0.5")
        ml = np.array([res["ml"]["probabilities"][service.labels[c]] for c in CODES])
        dl = np.array([res["deep"]["probabilities"][service.labels[c]] for c in CODES])
        fused = 0.5 * dl + 0.5 * ml; fused = fused / fused.sum()
        got = np.array([res["probabilities"][service.labels[c]] for c in CODES])
        np.testing.assert_allclose(got, fused, atol=1e-3)
        self.assertEqual(res["label"], service.labels[CODES[int(got.argmax())]])

    def test_deep_weight_moves_the_answer_towards_the_cnn(self):
        low = self.run_pipeline(top="bu", weight="0.0")["probabilities"][service.labels["bu"]]
        high = self.run_pipeline(top="bu", weight="1.0")["probabilities"][service.labels["bu"]]
        self.assertGreaterEqual(high, low)

    def test_fallback_to_ml_only_when_deep_unavailable(self):
        with mock.patch.object(deep_service, "available", return_value=False), \
             mock.patch.object(deep_service, "status", return_value=fake_status(False, "No trained weights")):
            res = service.analyze_file(self.wav)
        self.assertEqual(res["pipeline"], "ml")
        self.assertEqual(res["deep"]["status"], "unavailable")
        self.assertIn("No trained weights", res["deep"]["reason"])
        self.assertEqual(res["fusion"]["mode"], "ml_only")
        self.assertEqual(res["probabilities"], res["ml"]["probabilities"])
        self.assertIn("dl_off", [t["key"] for t in res["trace"]])

    def test_deep_crash_never_breaks_the_ml_answer(self):
        with mock.patch.object(deep_service, "available", return_value=True), \
             mock.patch.object(deep_service, "status", return_value=fake_status()), \
             mock.patch.object(deep_service, "predict", side_effect=RuntimeError("boom")):
            res = service.analyze_file(self.wav)
        self.assertEqual(res["deep"]["status"], "error")
        self.assertIn("boom", res["deep"]["reason"])
        self.assertEqual(res["pipeline"], "ml")
        self.assertTrue(res["label"])

    def test_dataset_row_cannot_use_the_cnn(self):
        res = service.analyze_row(np.array([0.8, 300, 250, 400, 40, 5] + [0.0] * 13),
                                  {"file": "x", "cu": "1", "true_label": "Hungry"})
        self.assertEqual(res["deep"]["status"], "needs_audio")
        self.assertEqual(res["pipeline"], "ml")

    def test_real_status_without_torch_is_honest(self):
        deep_service.reset()
        st = deep_service.status()
        if not st["ready"]:
            self.assertTrue(st["reason"])
        deep_service.reset()


if __name__ == "__main__":
    unittest.main()
