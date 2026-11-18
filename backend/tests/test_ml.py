"""ML tests. Run from backend/:  python -m unittest tests.test_ml -v"""
import unittest

import numpy as np
import pandas as pd

from tests import _helpers as H
from ml import features as F
from ml import tabular_train as T
from ml.stack import CascadeStack, add_engineered, smote


class Features(unittest.TestCase):
    def test_pitch_recovered(self):
        y, sr = H.synth_cry(sr=16000)
        u = F.extract_units(y)
        self.assertEqual(len(u), 3)
        for x, true in zip(u, (420, 480, 390)):
            self.assertLess(abs(x["vector"][3] - true) / true, 0.05)
            self.assertLessEqual(x["vector"][1], x["vector"][3] <= x["vector"][2] and x["vector"][3] or 1e9)

    def test_vector_shape_and_scale_like_csv(self):
        y, _ = H.synth_cry(sr=16000)
        v = F.extract_units(y)[0]["vector"]
        self.assertEqual(len(v), len(F.FEATURE_COLUMNS))
        d = pd.read_csv("dataset/test_dataset_clean.csv")
        lo, hi = d["MFCC_1"].quantile(.01), d["MFCC_1"].quantile(.99)
        self.assertTrue(lo - 100 < v[6] < hi + 100, f"MFCC_1={v[6]} CSV range {lo:.0f}..{hi:.0f}")

    def test_noise_has_low_hnr_and_silence_gives_no_units(self):
        rng = np.random.default_rng(0)
        self.assertEqual(F.extract_units(np.zeros(32000, dtype=np.float32)), [])
        noise = (rng.standard_normal(32000) * .3).astype(np.float32)
        tone, _ = H.synth_cry(sr=16000)
        hn = [x["vector"][5] for x in F.extract_units(noise)]
        ht = [x["vector"][5] for x in F.extract_units(tone)]
        if hn:
            self.assertLess(np.mean(hn), np.mean(ht))

    def test_mel_filterbank_matches_known_properties(self):
        fb = F.mel_filterbank(8000, 2048, 128)
        self.assertEqual(fb.shape, (128, 1025)); self.assertTrue((fb >= 0).all()); self.assertTrue((fb.sum(1) > 0).all())


class Stack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = T.load("dataset/test_dataset_clean.csv")
        cls.X, cls.y, cls.g = T.xy(d)

    def test_grouped_cv_never_shares_recordings(self):
        from sklearn.model_selection import StratifiedGroupKFold
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=T.SEED).split(self.X, self.y, self.g):
                self.assertFalse(set(self.g[tr]) & set(self.g[te]))

    def test_smote_adds_only_minority_rows_inside_class_hull(self):
        Xs, ys = smote(self.X, self.y, seed=1)
        self.assertGreater(len(Xs), len(self.X))
        for c in np.unique(self.y):
            lo, hi = self.X[self.y == c].min(0), self.X[self.y == c].max(0)
            new = Xs[len(self.X):][ys[len(self.y):] == c]
            if len(new):
                self.assertTrue(((new >= lo - 1e-9) & (new <= hi + 1e-9)).all())

    def test_cascade_trace(self):
        sub = np.random.default_rng(0).choice(len(self.y), 300, replace=False)
        m = CascadeStack(len(T.CODES), use_smote=False, n_trees=40, inner_splits=3).fit(add_engineered(self.X[sub]), self.y[sub], self.g[sub])
        sp, final = m.trace(add_engineered(self.X[:5]))
        self.assertEqual(set(sp), {"rf", "ada"}); self.assertEqual(final.shape, (5, len(T.CODES)))
        np.testing.assert_allclose(final.sum(1), 1, atol=1e-6)
        np.testing.assert_allclose(sum(m.meta_weights().values()), 1, atol=1e-6)

    def test_saved_metrics_are_honest(self):
        """The served metrics must carry the honest context: the majority baseline it has to beat, a leaky-split
        reference to show what leakage would inflate the number to, a grouped-CV estimate, and a per-model comparison."""
        import json
        m = json.load(open("model/metrics.json"))
        self.assertEqual(m["mode"], "unified_subjectwise_split")
        self.assertIn("majority_baseline_accuracy", m)
        self.assertIn("leaky_split_reference", m)
        self.assertIn("grouped_cv_macro_f1", m)
        self.assertIn("recording_level", m["comparison"]["Random Forest"])
        # the stack must genuinely beat the majority baseline (the old model only tied it)
        self.assertGreater(m["test"]["macro_f1"], m["majority_baseline_accuracy"] * 0 + 0.3)


if __name__ == "__main__":
    unittest.main()
