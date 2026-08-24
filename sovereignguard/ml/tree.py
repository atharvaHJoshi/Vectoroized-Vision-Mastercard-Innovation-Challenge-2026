"""
Histogram-based decision tree — the shared primitive for both Blue Team models.

WHY THIS EXISTS
---------------
This project is built to run with no third-party ML dependency, so the trees
are implemented here directly. The design follows the standard
histogram-gradient-boosting approach (LightGBM / XGBoost `hist`):

  * features are pre-binned once into small integer codes
  * a node's split is chosen from gradient/hessian histograms
  * the histogram of the larger child is obtained by subtraction from the
    parent, so only the smaller child is ever scanned

ONE TREE, TWO MODELS
--------------------
The split criterion is the usual second-order gain

    gain = G_L^2/(H_L+L2) + G_R^2/(H_R+L2) - G^2/(H+L2)

With `grad = -y` and `hess = 1` this reduces exactly to

    (Sum y_L)^2/n_L + (Sum y_R)^2/n_R - (Sum y)^2/n

which is the variance-reduction criterion. For a 0/1 target the variance is
p(1-p) and Gini impurity is 2p(1-p), so they induce the *same* split ordering.
That means the identical tree builder serves gradient boosting (logistic
gradients) and a random forest (Gini-equivalent splits), which keeps the amount
of code that has to be trusted small.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

MISSING_BIN = 0  # bin 0 is reserved; real values start at 1


# ==========================================================================
class Binner:
    """Quantile binning of a float feature matrix into uint8 codes.

    Fitted on training data only. Bin edges are stored so scoring a single
    transaction at inference time uses exactly the training discretisation.
    """

    def __init__(self, max_bins: int = 64):
        if not 2 <= max_bins <= 255:
            raise ValueError("max_bins must be in [2, 255]")
        self.max_bins = max_bins
        self.edges_: List[np.ndarray] = []
        self.n_features_: int = 0

    def fit(self, X: np.ndarray) -> "Binner":
        X = np.asarray(X, dtype=np.float32)
        self.n_features_ = X.shape[1]
        self.edges_ = []
        qs = np.linspace(0.0, 1.0, self.max_bins + 1)[1:-1]
        for j in range(self.n_features_):
            col = X[:, j]
            finite = col[np.isfinite(col)]
            if finite.size == 0:
                self.edges_.append(np.array([0.0], dtype=np.float32))
                continue
            e = np.unique(np.quantile(finite, qs).astype(np.float32))
            if e.size == 0:
                e = np.array([float(finite[0])], dtype=np.float32)
            self.edges_.append(e)
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float32)
        if X.shape[1] != self.n_features_:
            raise ValueError(f"expected {self.n_features_} features, got {X.shape[1]}")
        out = np.empty(X.shape, dtype=np.uint8)
        for j in range(self.n_features_):
            # +1 keeps bin 0 free as the missing/sentinel bin
            out[:, j] = np.searchsorted(self.edges_[j], X[:, j], side="left") + 1
        return out

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        return self.fit(X).transform(X)

    @property
    def n_bins(self) -> int:
        return self.max_bins + 2

    def bin_upper_value(self, feature: int, bin_idx: int) -> float:
        """Approximate real-valued threshold for a bin boundary (for reporting)."""
        e = self.edges_[feature]
        i = int(bin_idx) - 1
        if i <= 0:
            return float(e[0]) if e.size else 0.0
        if i >= e.size:
            return float(e[-1]) if e.size else 0.0
        return float(e[i - 1])

    def to_dict(self) -> dict:
        return {"max_bins": self.max_bins,
                "edges": [e.tolist() for e in self.edges_],
                "n_features": self.n_features_}

    @classmethod
    def from_dict(cls, d: dict) -> "Binner":
        b = cls(max_bins=int(d["max_bins"]))
        b.edges_ = [np.asarray(e, dtype=np.float32) for e in d["edges"]]
        b.n_features_ = int(d["n_features"])
        return b


# ==========================================================================
@dataclass
class Tree:
    """Flat array representation of a binary tree.

    Internal node i: feature[i] >= 0, split on `bin <= threshold[i]` -> left.
    Leaf node i: feature[i] == -1, prediction is value[i].
    `cover[i]` is the sum of hessians reaching i, used by TreeSHAP.
    """
    feature: np.ndarray      # int32
    threshold: np.ndarray    # uint8 bin index (inclusive upper bound of left)
    left: np.ndarray         # int32
    right: np.ndarray        # int32
    value: np.ndarray        # float32
    cover: np.ndarray        # float32
    n_nodes: int

    def predict_binned(self, Xb: np.ndarray) -> np.ndarray:
        """Vectorised traversal: all rows walk the tree level by level."""
        n = Xb.shape[0]
        node = np.zeros(n, dtype=np.int32)
        out = np.empty(n, dtype=np.float32)
        active = np.arange(n)
        while active.size:
            nd = node[active]
            feat = self.feature[nd]
            is_leaf = feat < 0
            if is_leaf.any():
                done = active[is_leaf]
                out[done] = self.value[node[done]]
                active = active[~is_leaf]
                if active.size == 0:
                    break
                nd = node[active]
                feat = self.feature[nd]
            vals = Xb[active, feat]
            go_left = vals <= self.threshold[nd]
            node[active] = np.where(go_left, self.left[nd], self.right[nd])
        return out

    def leaf_index(self, Xb: np.ndarray) -> np.ndarray:
        n = Xb.shape[0]
        node = np.zeros(n, dtype=np.int32)
        active = np.arange(n)
        while active.size:
            nd = node[active]
            feat = self.feature[nd]
            keep = feat >= 0
            active = active[keep]
            if active.size == 0:
                break
            nd = node[active]
            feat = self.feature[nd]
            vals = Xb[active, feat]
            go_left = vals <= self.threshold[nd]
            node[active] = np.where(go_left, self.left[nd], self.right[nd])
        return node

    @property
    def max_depth_actual(self) -> int:
        depth = np.zeros(self.n_nodes, dtype=np.int32)
        best = 0
        for i in range(self.n_nodes):
            if self.feature[i] >= 0:
                depth[self.left[i]] = depth[i] + 1
                depth[self.right[i]] = depth[i] + 1
                best = max(best, depth[i] + 1)
        return int(best)

    def to_dict(self) -> dict:
        return {"feature": self.feature.tolist(), "threshold": self.threshold.tolist(),
                "left": self.left.tolist(), "right": self.right.tolist(),
                "value": self.value.tolist(), "cover": self.cover.tolist(),
                "n_nodes": int(self.n_nodes)}

    @classmethod
    def from_dict(cls, d: dict) -> "Tree":
        return cls(
            feature=np.asarray(d["feature"], dtype=np.int32),
            threshold=np.asarray(d["threshold"], dtype=np.uint8),
            left=np.asarray(d["left"], dtype=np.int32),
            right=np.asarray(d["right"], dtype=np.int32),
            value=np.asarray(d["value"], dtype=np.float32),
            cover=np.asarray(d["cover"], dtype=np.float32),
            n_nodes=int(d["n_nodes"]))


# ==========================================================================
class TreeBuilder:
    """Grows one Tree from gradients and hessians."""

    def __init__(self, n_bins: int, max_depth: int = 6, min_samples_leaf: int = 20,
                 min_child_weight: float = 1e-3, l2: float = 1.0,
                 max_leaves: int = 63, colsample: float = 1.0,
                 min_gain: float = 1e-7):
        self.n_bins = n_bins
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.min_child_weight = min_child_weight
        self.l2 = l2
        self.max_leaves = max_leaves
        self.colsample = colsample
        self.min_gain = min_gain

    # ------------------------------------------------------------------
    def _histograms(self, cols: List[np.ndarray], rows: np.ndarray,
                    grad: np.ndarray, hess: np.ndarray,
                    features: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        nb = self.n_bins
        nf = features.size
        hg = np.zeros((nf, nb), dtype=np.float64)
        hh = np.zeros((nf, nb), dtype=np.float64)
        hc = np.zeros((nf, nb), dtype=np.float64)
        g_r = grad[rows]
        h_r = hess[rows]
        for a, j in enumerate(features):
            v = cols[j][rows]
            hg[a] = np.bincount(v, weights=g_r, minlength=nb)[:nb]
            hh[a] = np.bincount(v, weights=h_r, minlength=nb)[:nb]
            hc[a] = np.bincount(v, minlength=nb)[:nb]
        return hg, hh, hc

    def _best_split(self, hg: np.ndarray, hh: np.ndarray, hc: np.ndarray,
                    features: np.ndarray) -> Optional[Tuple[int, int, float]]:
        """Scan cumulative histograms for the highest-gain (feature, bin)."""
        G = hg.sum(axis=1)
        H = hh.sum(axis=1)
        Cn = hc.sum(axis=1)
        cg = np.cumsum(hg, axis=1)
        chh = np.cumsum(hh, axis=1)
        cc = np.cumsum(hc, axis=1)

        GL, HL, CL = cg[:, :-1], chh[:, :-1], cc[:, :-1]
        GR = G[:, None] - GL
        HR = H[:, None] - HL
        CR = Cn[:, None] - CL

        valid = ((CL >= self.min_samples_leaf) & (CR >= self.min_samples_leaf) &
                 (HL >= self.min_child_weight) & (HR >= self.min_child_weight))
        if not valid.any():
            return None
        parent = (G ** 2) / (H + self.l2)
        gain = (GL ** 2) / (HL + self.l2) + (GR ** 2) / (HR + self.l2) - parent[:, None]
        gain = np.where(valid, gain, -np.inf)
        flat = int(np.argmax(gain))
        a, b = divmod(flat, gain.shape[1])
        best = float(gain[a, b])
        if not np.isfinite(best) or best <= self.min_gain:
            return None
        return int(features[a]), int(b), best

    # ------------------------------------------------------------------
    def build(self, cols: List[np.ndarray], grad: np.ndarray, hess: np.ndarray,
              rows: np.ndarray, rng: np.random.Generator) -> Tree:
        n_features = len(cols)
        k = max(1, int(round(n_features * self.colsample)))
        feat_pool = (np.arange(n_features) if k >= n_features
                     else np.sort(rng.choice(n_features, size=k, replace=False)))

        feature: List[int] = []
        threshold: List[int] = []
        left: List[int] = []
        right: List[int] = []
        value: List[float] = []
        cover: List[float] = []

        def new_node() -> int:
            feature.append(-1); threshold.append(0)
            left.append(-1); right.append(-1)
            value.append(0.0); cover.append(0.0)
            return len(feature) - 1

        def leaf_value(g_sum: float, h_sum: float) -> float:
            return float(-g_sum / (h_sum + self.l2))

        root = new_node()
        hg, hh, hc = self._histograms(cols, rows, grad, hess, feat_pool)
        # (node, rows, depth, hist triple or None)
        stack: List[Tuple[int, np.ndarray, int, Optional[Tuple]]] = [
            (root, rows, 0, (hg, hh, hc))]
        n_leaves = 1

        while stack:
            node, node_rows, depth, hists = stack.pop()
            if hists is None:
                hists = self._histograms(cols, node_rows, grad, hess, feat_pool)
            hg, hh, hc = hists
            g_sum = float(hg.sum(axis=1)[0]) if hg.shape[0] else 0.0
            h_sum = float(hh.sum(axis=1)[0]) if hh.shape[0] else 0.0
            cover[node] = h_sum
            value[node] = leaf_value(g_sum, h_sum)

            if (depth >= self.max_depth or node_rows.size < 2 * self.min_samples_leaf
                    or n_leaves >= self.max_leaves):
                continue
            split = self._best_split(hg, hh, hc, feat_pool)
            if split is None:
                continue
            f, b, _gain = split
            mask = cols[f][node_rows] <= b
            rl = node_rows[mask]
            rr = node_rows[~mask]
            if rl.size < self.min_samples_leaf or rr.size < self.min_samples_leaf:
                continue

            li, ri = new_node(), new_node()
            feature[node] = f
            threshold[node] = b
            left[node] = li
            right[node] = ri
            n_leaves += 1

            # Histogram subtraction: scan the smaller child, subtract for the other.
            if rl.size <= rr.size:
                hl = self._histograms(cols, rl, grad, hess, feat_pool)
                hr = (hg - hl[0], hh - hl[1], hc - hl[2])
            else:
                hr = self._histograms(cols, rr, grad, hess, feat_pool)
                hl = (hg - hr[0], hh - hr[1], hc - hr[2])
            stack.append((li, rl, depth + 1, hl))
            stack.append((ri, rr, depth + 1, hr))

        return Tree(
            feature=np.asarray(feature, dtype=np.int32),
            threshold=np.asarray(threshold, dtype=np.uint8),
            left=np.asarray(left, dtype=np.int32),
            right=np.asarray(right, dtype=np.int32),
            value=np.asarray(value, dtype=np.float32),
            cover=np.asarray(cover, dtype=np.float32),
            n_nodes=len(feature))


def to_columns(Xb: np.ndarray) -> List[np.ndarray]:
    """Column-major view for cache-friendly per-feature histogram building."""
    return [np.ascontiguousarray(Xb[:, j]) for j in range(Xb.shape[1])]
