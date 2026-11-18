"""Fusion of the two branches (unified 5-class weighted average). Run from backend/:
    python -m unittest tests.test_fusion -v
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from ml import fusion


class FuseMath(unittest.TestCase):
    ml = np.array([0.6, 0.1, 0.1, 0.1, 0.1])
    dl = np.array([0.1, 0.7, 0.1, 0.05, 0.05])

    def test_w0_is_pure_ml(self):
        f, _ = fusion.fuse(self.ml, self.dl, w=0.0)
        np.testing.assert_allclose(f, self.ml, atol=1e-9)

    def test_w1_is_pure_dl(self):
        f, _ = fusion.fuse(self.ml, self.dl, w=1.0)
        np.testing.assert_allclose(f, self.dl, atol=1e-9)

    def test_fused_is_a_distribution_and_between(self):
        for w in (0.2, 0.5, 0.8):
            f, info = fusion.fuse(self.ml, self.dl, w=w)
            self.assertAlmostEqual(f.sum(), 1.0, places=9)
            self.assertEqual(info["weight"], w)
            self.assertTrue(min(self.ml[1], self.dl[1]) - 1e-9 <= f[1] <= max(self.ml[1], self.dl[1]) + 1e-9)

    def test_dl_can_flip_the_winner(self):
        _, info = fusion.fuse(self.ml, self.dl, w=0.8)
        self.assertEqual(info["fused_top"], 1)          # DL's class (tired) wins at high weight
        self.assertFalse(info["agree"])

    def test_agreement_flag(self):
        _, info = fusion.fuse(self.ml, self.ml, w=0.5)
        self.assertTrue(info["agree"])


class WeightSource(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.p = mock.patch.object(fusion, "CONFIG_PATH", self.tmp / "fusion.json"); self.p.start()
        self.env = mock.patch.dict(os.environ, {}, clear=False); self.env.start(); os.environ.pop("DEEP_WEIGHT", None)

    def tearDown(self):
        self.p.stop(); self.env.stop()

    def test_default_then_tuned_then_env(self):
        self.assertEqual(fusion.weight_source(), (0.5, "default"))
        fusion.CONFIG_PATH.write_text(json.dumps({"dl_weight": 0.35}))
        self.assertEqual(fusion.weight_source(), (0.35, "tuned"))
        os.environ["DEEP_WEIGHT"] = "0.9"
        self.assertEqual(fusion.weight_source(), (0.9, "env"))
        os.environ["DEEP_WEIGHT"] = "banana"            # unusable override -> falls back to the tuned file
        self.assertEqual(fusion.weight_source(), (0.35, "tuned"))

    def test_env_is_clamped(self):
        with mock.patch.dict(os.environ, {"DEEP_WEIGHT": "7"}):
            self.assertEqual(fusion.deep_weight(), 1.0)
        with mock.patch.dict(os.environ, {"DEEP_WEIGHT": "-2"}):
            self.assertEqual(fusion.deep_weight(), 0.0)

    def test_broken_or_out_of_range_config(self):
        fusion.CONFIG_PATH.write_text("{not json")
        self.assertEqual(fusion.weight_source(), (0.5, "default"))
        fusion.CONFIG_PATH.write_text(json.dumps({"dl_weight": 7}))
        self.assertEqual(fusion.weight_source(), (1.0, "tuned"))


if __name__ == "__main__":
    unittest.main()
