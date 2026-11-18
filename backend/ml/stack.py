"""The classical-ML path:  Random Forest  ->  AdaBoost  ->  Logistic Regression (meta-learner).

Stage 1  Random Forest      : many deep trees vote; robust to noisy features.
Stage 2  AdaBoost           : boosted shallow trees; concentrates on the rows the forest finds hard.
Stage 3  Logistic Regression: learns, from OUT-OF-FOLD probabilities of stages 1+2 (+ the raw features'
                              most useful summary), how much to trust each stage for each cry type.
                              It is the final decision maker.

Optional extra stage-1 learners (ExtraTrees, HistGradientBoosting) can be switched on; the trainer
only keeps them when grouped cross-validation shows that they help.
Every prediction returns a TRACE with the output of each stage so the UI can show what happened.
"""
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import (AdaBoostClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier,
                              RandomForestClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from ml.features import FEATURE_COLUMNS

ENG_COLUMNS = FEATURE_COLUMNS + ["F0_range", "F0_cv", "F0_span_ratio"]


def add_engineered(X):
    """19 raw columns -> 22 columns (adds pitch range / variability ratios). Used in training AND serving."""
    X = np.asarray(X, dtype=np.float64)
    mn, mx, mean, std = X[:, 1], X[:, 2], X[:, 3], X[:, 4]
    extra = np.c_[mx - mn, std / (mean + 1e-9), mx / (mn + 1e-9)]
    return np.c_[X, extra]


def expand_proba(p, classes_, n_classes):
    full = np.zeros((p.shape[0], n_classes))
    for col, c in enumerate(classes_):
        full[:, int(c)] = p[:, col]
    return full


def smote(X, y, target_ratio=0.35, k=5, seed=0):
    """Minimal SMOTE: interpolate between a minority row and one of its k nearest same-class neighbours.
    Used ONLY inside training folds, never on test data."""
    rng = np.random.default_rng(seed)
    classes, counts = np.unique(y, return_counts=True)
    goal = int(counts.max() * target_ratio)
    Xs, ys = [X], [y]
    for c, n in zip(classes, counts):
        if n >= goal or n < 2:
            continue
        Xc = X[y == c]
        kk = min(k, n - 1)
        d = ((Xc[:, None, :] - Xc[None, :, :]) ** 2).sum(-1)
        nn = np.argsort(d, axis=1)[:, 1:kk + 1]
        need = goal - n
        i = rng.integers(0, n, need)
        j = nn[i, rng.integers(0, kk, need)]
        lam = rng.random((need, 1))
        Xs.append(Xc[i] + lam * (Xc[j] - Xc[i])); ys.append(np.full(need, c))
    return np.vstack(Xs), np.concatenate(ys)


class CascadeStack(BaseEstimator, ClassifierMixin):
    def __init__(self, n_classes, use_smote=True, extras=(), n_trees=250, seed=42, inner_splits=4, meta_C=1.0, meta_balanced=True):
        self.n_classes = n_classes
        self.use_smote = use_smote
        self.extras = extras
        self.n_trees = n_trees
        self.seed = seed
        self.inner_splits = inner_splits
        self.meta_C = meta_C
        self.meta_balanced = meta_balanced

    # -- stage factories ---------------------------------------------------------------
    def _make(self, name):
        s = self.seed
        if name == "rf":
            return RandomForestClassifier(n_estimators=self.n_trees, min_samples_leaf=2, max_features="sqrt",
                                          class_weight="balanced_subsample", n_jobs=-1, random_state=s)
        if name == "ada":
            return AdaBoostClassifier(estimator=DecisionTreeClassifier(max_depth=3, class_weight="balanced", random_state=s),
                                      n_estimators=80, learning_rate=0.6, random_state=s)
        if name == "et":
            return ExtraTreesClassifier(n_estimators=self.n_trees, min_samples_leaf=2, class_weight="balanced_subsample",
                                        n_jobs=-1, random_state=s)
        if name == "hgb":
            return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=60, class_weight="balanced",
                                                  random_state=s)
        raise ValueError(name)

    @property
    def stage_names(self):
        return ["rf", "ada"] + list(self.extras)

    def _fit_base(self, name, X, y):
        if self.use_smote:
            X, y = smote(X, y, seed=self.seed)
        m = self._make(name)
        if name == "ada":                              # AdaBoost has no class_weight: use sample weights
            cnt = np.bincount(y, minlength=self.n_classes).astype(float)
            m.fit(X, y, sample_weight=(1.0 / np.maximum(cnt[y], 1)) * len(y) / self.n_classes)
        else:
            m.fit(X, y)
        return m

    def _proba(self, m, X):
        return expand_proba(m.predict_proba(X), m.classes_, self.n_classes)

    def _meta_features(self, probs):
        # log-probabilities of every stage side by side -> logistic regression works in log-odds space
        return np.hstack([np.log(np.clip(p, 1e-4, 1)) for p in probs])

    # -- training ----------------------------------------------------------------------
    def fit(self, X, y, groups):
        X = np.asarray(X, float); y = np.asarray(y, int); groups = np.asarray(groups)
        names = self.stage_names
        oof = {n: np.zeros((len(y), self.n_classes)) for n in names}
        splits = min(self.inner_splits, max(2, len(np.unique(groups))))
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cv = StratifiedGroupKFold(splits, shuffle=True, random_state=self.seed)
            for tr, va in cv.split(X, y, groups):
                for n in names:
                    m = self._fit_base(n, X[tr], y[tr])
                    oof[n][va] = self._proba(m, X[va])
        self.base_ = {n: self._fit_base(n, X, y) for n in names}          # refit on everything
        Z = self._meta_features([oof[n] for n in names])
        self.meta_ = make_pipeline(StandardScaler(), LogisticRegression(C=self.meta_C, max_iter=3000,
                                   class_weight="balanced" if self.meta_balanced else None, random_state=self.seed))
        self.meta_.fit(Z, y)
        self.classes_ = np.arange(self.n_classes)
        self.oof_ = oof
        return self

    # -- inference ---------------------------------------------------------------------
    def stage_probas(self, X):
        X = np.asarray(X, float)
        return {n: self._proba(self.base_[n], X) for n in self.stage_names}

    def predict_proba(self, X):
        sp = self.stage_probas(X)
        Z = self._meta_features([sp[n] for n in self.stage_names])
        return expand_proba(self.meta_.predict_proba(Z), self.meta_[-1].classes_, self.n_classes)

    def predict(self, X):
        return self.predict_proba(X).argmax(1)

    def trace(self, X):
        """Per-row output of every stage (used by the 'what is happening' demo)."""
        sp = self.stage_probas(X)
        final = self.predict_proba(X)
        return sp, final

    def meta_weights(self):
        """Mean absolute LR coefficient per stage (how much the final decision relies on each stage)."""
        coef = np.abs(self.meta_[-1].coef_)                                   # (classes_present, stages*n_classes)
        per = coef.reshape(coef.shape[0], len(self.stage_names), self.n_classes).mean(axis=(0, 2))
        per = per / per.sum()
        return {n: float(v) for n, v in zip(self.stage_names, per)}
