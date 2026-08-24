"""
Blue Team models (Phase 12).

`GradientBoostingClassifier` — logistic-loss histogram GBDT with row/column
subsampling and early stopping on a validation split.

`RandomForestClassifier` — bagged trees with Gini-equivalent splits (see the
note in tree.py on why squared-error on a 0/1 target is Gini).

Both expose the same surface: fit / predict_proba / feature_importances_ /
save / load, so `detection.train` can treat them interchangeably and the
optional XGBoost / LightGBM adapters can slot in beside them.
"""
from __future__ import annotations

import gzip
import json
from typing import Dict, List, Optional, Tuple

import numpy as np

from .tree import Binner, Tree, TreeBuilder, to_columns


def sigmoid(z: np.ndarray) -> np.ndarray:
    out = np.empty_like(z, dtype=np.float64)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


def logloss(y: np.ndarray, p: np.ndarray, eps: float = 1e-7) -> float:
    p = np.clip(p, eps, 1 - eps)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


class BaseModel:
    kind = "base"

    def __init__(self):
        self.binner_: Optional[Binner] = None
        self.trees_: List[Tree] = []
        self.base_score_: float = 0.0
        self.n_features_: int = 0
        self.feature_names_: List[str] = []
        self.train_history_: List[Dict] = []

    # -------------------------------------------------------------- persistence
    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "params": self.params(),
            "binner": self.binner_.to_dict() if self.binner_ else None,
            "trees": [t.to_dict() for t in self.trees_],
            "base_score": self.base_score_,
            "n_features": self.n_features_,
            "feature_names": self.feature_names_,
            "train_history": self.train_history_,
        }

    def params(self) -> dict:
        raise NotImplementedError

    def save(self, path) -> None:
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh)

    @staticmethod
    def load(path) -> "BaseModel":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            d = json.load(fh)
        cls = {"gbdt": GradientBoostingClassifier,
               "forest": RandomForestClassifier}[d["kind"]]
        m = cls(**d["params"])
        m.binner_ = Binner.from_dict(d["binner"]) if d["binner"] else None
        m.trees_ = [Tree.from_dict(t) for t in d["trees"]]
        m.base_score_ = float(d["base_score"])
        m.n_features_ = int(d["n_features"])
        m.feature_names_ = list(d["feature_names"])
        m.train_history_ = list(d.get("train_history", []))
        return m

    # -------------------------------------------------------------- importance
    def feature_importances_(self, normalise: bool = True) -> np.ndarray:
        """Split-count importance weighted by node cover."""
        imp = np.zeros(self.n_features_, dtype=np.float64)
        for t in self.trees_:
            internal = t.feature >= 0
            np.add.at(imp, t.feature[internal], t.cover[internal])
        if normalise and imp.sum() > 0:
            imp = imp / imp.sum()
        return imp

    def importance_table(self, top: int = 20) -> List[Tuple[str, float]]:
        imp = self.feature_importances_()
        order = np.argsort(-imp)[:top]
        names = self.feature_names_ or [f"f{i}" for i in range(self.n_features_)]
        return [(names[i], float(imp[i])) for i in order]


# ==========================================================================
class GradientBoostingClassifier(BaseModel):
    kind = "gbdt"

    def __init__(self, n_estimators: int = 200, learning_rate: float = 0.12,
                 max_depth: int = 6, max_leaves: int = 63,
                 min_samples_leaf: int = 20, min_child_weight: float = 1e-3,
                 l2: float = 1.0, subsample: float = 0.8, colsample: float = 0.7,
                 max_bins: int = 64, early_stopping_rounds: int = 25,
                 scale_pos_weight: float = 1.0, random_state: int = 0,
                 verbose: bool = False):
        super().__init__()
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.max_leaves = max_leaves
        self.min_samples_leaf = min_samples_leaf
        self.min_child_weight = min_child_weight
        self.l2 = l2
        self.subsample = subsample
        self.colsample = colsample
        self.max_bins = max_bins
        self.early_stopping_rounds = early_stopping_rounds
        self.scale_pos_weight = scale_pos_weight
        self.random_state = random_state
        self.verbose = verbose
        self.best_iteration_: int = 0

    def params(self) -> dict:
        return {k: getattr(self, k) for k in
                ("n_estimators", "learning_rate", "max_depth", "max_leaves",
                 "min_samples_leaf", "min_child_weight", "l2", "subsample",
                 "colsample", "max_bins", "early_stopping_rounds",
                 "scale_pos_weight", "random_state", "verbose")}

    def fit(self, X: np.ndarray, y: np.ndarray,
            eval_set: Optional[Tuple[np.ndarray, np.ndarray]] = None,
            feature_names: Optional[List[str]] = None) -> "GradientBoostingClassifier":
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.float64).ravel()
        n, f = X.shape
        self.n_features_ = f
        self.feature_names_ = list(feature_names or [f"f{i}" for i in range(f)])
        rng = np.random.default_rng(self.random_state)

        self.binner_ = Binner(self.max_bins).fit(X)
        Xb = self.binner_.transform(X)
        cols = to_columns(Xb)

        # Sample weights implement class rebalancing without resampling rows.
        w = np.where(y > 0.5, self.scale_pos_weight, 1.0)
        pbar = float(np.average(y, weights=w))
        pbar = min(max(pbar, 1e-6), 1 - 1e-6)
        self.base_score_ = float(np.log(pbar / (1 - pbar)))
        F = np.full(n, self.base_score_, dtype=np.float64)

        have_eval = eval_set is not None
        if have_eval:
            Xv = np.asarray(eval_set[0], dtype=np.float32)
            yv = np.asarray(eval_set[1], dtype=np.float64).ravel()
            Xvb = self.binner_.transform(Xv)
            Fv = np.full(len(yv), self.base_score_, dtype=np.float64)
            best_loss, best_iter, since = np.inf, 0, 0

        builder = TreeBuilder(
            n_bins=self.binner_.n_bins, max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            min_child_weight=self.min_child_weight, l2=self.l2,
            max_leaves=self.max_leaves, colsample=self.colsample)

        self.trees_ = []
        all_rows = np.arange(n)
        for it in range(self.n_estimators):
            p = sigmoid(F)
            grad = (p - y) * w
            hess = np.maximum(p * (1.0 - p), 1e-6) * w
            if self.subsample < 1.0:
                m = max(self.min_samples_leaf * 4, int(n * self.subsample))
                rows = rng.choice(n, size=min(m, n), replace=False)
            else:
                rows = all_rows
            tree = builder.build(cols, grad, hess, rows, rng)
            self.trees_.append(tree)
            F += self.learning_rate * tree.predict_binned(Xb)

            rec = {"iteration": it + 1, "train_logloss": logloss(y, sigmoid(F))}
            if have_eval:
                Fv += self.learning_rate * tree.predict_binned(Xvb)
                vl = logloss(yv, sigmoid(Fv))
                rec["valid_logloss"] = vl
                if vl < best_loss - 1e-6:
                    best_loss, best_iter, since = vl, it + 1, 0
                else:
                    since += 1
            self.train_history_.append(rec)
            if self.verbose and (it + 1) % 20 == 0:
                print(f"  iter {it+1:4d} {rec}")
            if have_eval and since >= self.early_stopping_rounds:
                break

        if have_eval:
            self.best_iteration_ = int(best_iter)
            # Truncate to the best iteration — the stored model is the best model.
            self.trees_ = self.trees_[:max(1, self.best_iteration_)]
        else:
            self.best_iteration_ = len(self.trees_)
        return self

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        Xb = self.binner_.transform(np.asarray(X, dtype=np.float32))
        F = np.full(Xb.shape[0], self.base_score_, dtype=np.float64)
        for t in self.trees_:
            F += self.learning_rate * t.predict_binned(Xb)
        return F

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return sigmoid(self.decision_function(X))


# ==========================================================================
class RandomForestClassifier(BaseModel):
    kind = "forest"

    def __init__(self, n_estimators: int = 120, max_depth: int = 14,
                 min_samples_leaf: int = 5, colsample: float = 0.35,
                 max_leaves: int = 4096, bootstrap: bool = True,
                 subsample: float = 1.0, max_bins: int = 64,
                 class_weight_balanced: bool = True,
                 random_state: int = 0, verbose: bool = False):
        super().__init__()
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.colsample = colsample
        self.max_leaves = max_leaves
        self.bootstrap = bootstrap
        self.subsample = subsample
        self.max_bins = max_bins
        self.class_weight_balanced = class_weight_balanced
        self.random_state = random_state
        self.verbose = verbose

    def params(self) -> dict:
        return {k: getattr(self, k) for k in
                ("n_estimators", "max_depth", "min_samples_leaf", "colsample",
                 "max_leaves", "bootstrap", "subsample", "max_bins",
                 "class_weight_balanced", "random_state", "verbose")}

    def fit(self, X: np.ndarray, y: np.ndarray,
            eval_set=None, feature_names: Optional[List[str]] = None
            ) -> "RandomForestClassifier":
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y, dtype=np.float64).ravel()
        n, f = X.shape
        self.n_features_ = f
        self.feature_names_ = list(feature_names or [f"f{i}" for i in range(f)])
        rng = np.random.default_rng(self.random_state)

        self.binner_ = Binner(self.max_bins).fit(X)
        Xb = self.binner_.transform(X)
        cols = to_columns(Xb)

        if self.class_weight_balanced:
            pos = max(y.sum(), 1.0)
            neg = max(n - pos, 1.0)
            w = np.where(y > 0.5, n / (2.0 * pos), n / (2.0 * neg))
        else:
            w = np.ones(n)

        # grad = -y*w, hess = w  =>  leaf value = weighted mean of y  and
        # split gain == weighted variance reduction (== Gini for 0/1 targets).
        grad = -(y * w)
        hess = w
        self.base_score_ = 0.0

        builder = TreeBuilder(
            n_bins=self.binner_.n_bins, max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf, min_child_weight=1e-9,
            l2=1e-9, max_leaves=self.max_leaves, colsample=self.colsample)

        self.trees_ = []
        for it in range(self.n_estimators):
            if self.bootstrap:
                rows = rng.integers(0, n, size=int(n * self.subsample))
            else:
                m = max(self.min_samples_leaf * 4, int(n * self.subsample))
                rows = rng.choice(n, size=min(m, n), replace=False)
            self.trees_.append(builder.build(cols, grad, hess, rows, rng))
            if self.verbose and (it + 1) % 20 == 0:
                print(f"  tree {it+1}/{self.n_estimators}")
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        Xb = self.binner_.transform(np.asarray(X, dtype=np.float32))
        acc = np.zeros(Xb.shape[0], dtype=np.float64)
        for t in self.trees_:
            acc += t.predict_binned(Xb)
        return np.clip(acc / max(1, len(self.trees_)), 0.0, 1.0)

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        p = np.clip(self.predict_proba(X), 1e-7, 1 - 1e-7)
        return np.log(p / (1 - p))
