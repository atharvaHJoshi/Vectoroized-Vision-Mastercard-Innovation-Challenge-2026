"""
Path-dependent TreeSHAP (Phase 19).

Implements the exact polynomial-time algorithm of Lundberg, Erion & Lee
("Consistent Individualized Feature Attribution for Tree Ensembles"), which
computes Shapley values for a tree ensemble in O(T * L * D^2) instead of the
O(2^M) of the definition. The `shap` package is not available in this project's
runtime, so the algorithm is implemented here directly.

The implementation is verified in tests/test_treeshap.py against a brute-force
evaluation of the Shapley definition over all 2^M subsets on small trees. That
test is the reason this file can be trusted: any indexing slip in the
extend/unwind recursion shows up immediately as a mismatch against the
definition.

GUARANTEE (local accuracy / efficiency):

    base_value + sum(phi) == model output for that row

which is asserted at the end of `shap_values`.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from .models import BaseModel, GradientBoostingClassifier, RandomForestClassifier
from .tree import Tree


# --------------------------------------------------------------------------
def _tree_shap_single(tree: Tree, xb: np.ndarray, phi: np.ndarray) -> None:
    """Accumulate SHAP values for one row into `phi` (length n_features)."""
    n_nodes = tree.n_nodes
    max_d = 0
    # cheap depth bound: number of nodes is an upper bound on path length
    # (a tighter bound keeps the path arrays small)
    depth_of = np.zeros(n_nodes, dtype=np.int32)
    for i in range(n_nodes):
        if tree.feature[i] >= 0:
            depth_of[tree.left[i]] = depth_of[i] + 1
            depth_of[tree.right[i]] = depth_of[i] + 1
            max_d = max(max_d, depth_of[i] + 1)
    size = max_d + 2

    # unique_path arrays, indexed by path position
    d_feat = np.full(size, -1, dtype=np.int32)
    z_frac = np.zeros(size, dtype=np.float64)
    o_frac = np.zeros(size, dtype=np.float64)
    weight = np.zeros(size, dtype=np.float64)

    feature = tree.feature
    threshold = tree.threshold
    left = tree.left
    right = tree.right
    value = tree.value
    cover = tree.cover

    def extend(m: int, pz: float, po: float, pi: int) -> None:
        d_feat[m] = pi
        z_frac[m] = pz
        o_frac[m] = po
        weight[m] = 1.0 if m == 0 else 0.0
        for i in range(m - 1, -1, -1):
            weight[i + 1] += po * weight[i] * (i + 1) / (m + 1)
            weight[i] = pz * weight[i] * (m - i) / (m + 1)

    def unwind(m: int, i: int) -> None:
        o = o_frac[i]
        z = z_frac[i]
        n = weight[m]
        for j in range(m - 1, -1, -1):
            if o != 0.0:
                t = weight[j]
                weight[j] = n * (m + 1) / ((j + 1) * o)
                n = t - weight[j] * z * (m - j) / (m + 1)
            else:
                weight[j] = weight[j] * (m + 1) / (z * (m - j)) if z != 0.0 else 0.0
        for j in range(i, m):
            d_feat[j] = d_feat[j + 1]
            z_frac[j] = z_frac[j + 1]
            o_frac[j] = o_frac[j + 1]

    def unwound_sum(m: int, i: int) -> float:
        """Sum of path weights with feature at position i removed."""
        o = o_frac[i]
        z = z_frac[i]
        n = weight[m]
        total = 0.0
        if o != 0.0:
            for j in range(m - 1, -1, -1):
                t = n / ((j + 1) * o / (m + 1))
                total += t
                n = weight[j] - t * z * (m - j) / (m + 1)
        else:
            if z != 0.0:
                for j in range(m - 1, -1, -1):
                    total += weight[j] / (z * (m - j) / (m + 1))
        return total

    def recurse(node: int, m: int, pz: float, po: float, pi: int) -> None:
        extend(m, pz, po, pi)
        m += 1
        if feature[node] < 0:
            # leaf: distribute value across features on the path
            for i in range(1, m):
                w = unwound_sum(m - 1, i)
                phi[d_feat[i]] += w * (o_frac[i] - z_frac[i]) * value[node]
            return

        f = feature[node]
        hot = left[node] if xb[f] <= threshold[node] else right[node]
        cold = right[node] if xb[f] <= threshold[node] else left[node]

        # If this feature already appears on the path, fold the previous
        # occurrence in so a feature is never counted twice.
        incoming_zero = 1.0
        incoming_one = 1.0
        prev = -1
        for i in range(1, m):
            if d_feat[i] == f:
                prev = i
                break
        if prev != -1:
            incoming_zero = z_frac[prev]
            incoming_one = o_frac[prev]
            unwind(m - 1, prev)
            m -= 1

        c_parent = cover[node]
        if c_parent <= 0.0:
            return
        c_hot = cover[hot] / c_parent
        c_cold = cover[cold] / c_parent

        # snapshot the mutable path state for the second branch
        sd = d_feat[:m + 1].copy()
        sz = z_frac[:m + 1].copy()
        so = o_frac[:m + 1].copy()
        sw = weight[:m + 1].copy()

        recurse(hot, m, incoming_zero * c_hot, incoming_one, f)

        d_feat[:m + 1] = sd
        z_frac[:m + 1] = sz
        o_frac[:m + 1] = so
        weight[:m + 1] = sw

        recurse(cold, m, incoming_zero * c_cold, 0.0, f)

    recurse(0, 0, 1.0, 1.0, -1)


# --------------------------------------------------------------------------
def tree_expected_value(tree: Tree) -> float:
    """Cover-weighted mean leaf value = E[f(x)] under the path-dependent
    background distribution."""
    leaves = tree.feature < 0
    w = tree.cover[leaves]
    v = tree.value[leaves]
    if w.sum() <= 0:
        return float(v.mean()) if v.size else 0.0
    return float((w * v).sum() / w.sum())


def shap_values(model: BaseModel, X: np.ndarray,
                check: bool = True, tol: float = 1e-4
                ) -> Tuple[np.ndarray, float]:
    """SHAP values in the model's *margin* space.

    Returns (phi, base_value) where phi has shape (n_rows, n_features) and

        base_value + phi[i].sum() == model.decision_function(X)[i]

    For the GBDT that margin is the logit; for the forest it is the averaged
    probability (the forest's natural output space).
    """
    X = np.asarray(X, dtype=np.float32)
    if model.binner_ is None:
        raise ValueError("model has no fitted binner")
    Xb = model.binner_.transform(X)
    n, f = Xb.shape
    phi = np.zeros((n, f), dtype=np.float64)

    if isinstance(model, GradientBoostingClassifier):
        scale = model.learning_rate
        base = model.base_score_ + scale * sum(tree_expected_value(t) for t in model.trees_)
    elif isinstance(model, RandomForestClassifier):
        scale = 1.0 / max(1, len(model.trees_))
        base = scale * sum(tree_expected_value(t) for t in model.trees_)
    else:
        raise TypeError(f"unsupported model type {type(model).__name__}")

    for t in model.trees_:
        for i in range(n):
            row = np.zeros(f, dtype=np.float64)
            _tree_shap_single(t, Xb[i], row)
            phi[i] += scale * row

    if check and n:
        if isinstance(model, GradientBoostingClassifier):
            target = model.decision_function(X)
        else:
            target = model.predict_proba(X)
        got = base + phi.sum(axis=1)
        err = float(np.abs(got - target).max())
        if err > tol * max(1.0, float(np.abs(target).max())):
            raise AssertionError(
                f"TreeSHAP local-accuracy check failed: max error {err:.6g}")
    return phi, float(base)


def brute_force_shap(tree: Tree, xb: np.ndarray, n_features: int) -> np.ndarray:
    """Reference implementation: Shapley values straight from the definition.

    Enumerates all 2^M subsets, so only usable for tiny M. Exists purely to
    validate `_tree_shap_single` in the test suite.
    """
    from itertools import combinations
    from math import factorial

    feats = sorted({int(f) for f in tree.feature if f >= 0})
    M = len(feats)
    if M > 14:
        raise ValueError("brute force limited to 14 distinct split features")

    def expectation(subset: frozenset) -> float:
        """E[f(x) | x_S] under the tree's cover distribution."""
        def walk(node: int, weight: float) -> float:
            if weight == 0.0:
                return 0.0
            if tree.feature[node] < 0:
                return weight * float(tree.value[node])
            f = int(tree.feature[node])
            l, r = int(tree.left[node]), int(tree.right[node])
            if f in subset:
                nxt = l if xb[f] <= tree.threshold[node] else r
                return walk(nxt, weight)
            cp = float(tree.cover[node])
            if cp <= 0:
                return 0.0
            return (walk(l, weight * float(tree.cover[l]) / cp) +
                    walk(r, weight * float(tree.cover[r]) / cp))
        return walk(0, 1.0)

    phi = np.zeros(n_features, dtype=np.float64)
    others_cache = {}
    for i in feats:
        others = [g for g in feats if g != i]
        total = 0.0
        for k in range(len(others) + 1):
            coef = factorial(k) * factorial(M - k - 1) / factorial(M)
            for combo in combinations(others, k):
                S = frozenset(combo)
                if S not in others_cache:
                    others_cache[S] = expectation(S)
                with_i = expectation(S | {i})
                total += coef * (with_i - others_cache[S])
        phi[i] = total
    return phi
