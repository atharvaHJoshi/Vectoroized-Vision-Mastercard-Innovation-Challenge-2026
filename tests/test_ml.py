"""ML core: binning, trees, GBDT, RF, and TreeSHAP against the definition."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from sovereignguard.ml import (Binner, GradientBoostingClassifier,
                               RandomForestClassifier, sigmoid)
from sovereignguard.ml.models import BaseModel
from sovereignguard.ml.treeshap import (_tree_shap_single, brute_force_shap,
                                        shap_values)
from sovereignguard.evaluation.metrics import roc_auc

SEED = 20260823


def _problem(n=6000, f=8, seed=SEED):
    """Logistic problem with a known signal: an interaction, a linear term, a
    quadratic term, and pure-noise columns that must rank below them."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, f)).astype(np.float32)
    logit = 2.2 * X[:, 0] * X[:, 1] + 1.5 * X[:, 2] - 0.8 * X[:, 3] ** 2
    p = 1.0 / (1.0 + np.exp(-logit))
    y = (rng.random(n) < p).astype(float)
    return X, y, p


def test_binner_is_monotonic_and_round_trips():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(2000, 4)).astype(np.float32)
    b = Binner(max_bins=32).fit(X)
    Xb = b.transform(X)
    assert Xb.dtype == np.uint8
    assert Xb.min() >= 1, "bin 0 is reserved as the missing sentinel"
    assert Xb.max() <= b.n_bins - 1
    # binning must preserve order within a column
    for j in range(X.shape[1]):
        order = np.argsort(X[:, j])
        codes = Xb[order, j]
        assert np.all(np.diff(codes.astype(int)) >= 0), f"column {j} not monotonic"


def test_binner_transform_is_stable_for_single_rows():
    """Scoring one transaction must use exactly the training discretisation."""
    rng = np.random.default_rng(1)
    X = rng.normal(size=(500, 3)).astype(np.float32)
    b = Binner(16).fit(X)
    full = b.transform(X)
    for i in (0, 17, 499):
        one = b.transform(X[i:i + 1])
        assert np.array_equal(one[0], full[i])


def test_gbdt_approaches_bayes_optimal():
    X, y, p = _problem()
    tr, va, te = slice(0, 4000), slice(4000, 5000), slice(5000, 6000)
    m = GradientBoostingClassifier(n_estimators=300, learning_rate=0.1, max_depth=5,
                                   random_state=SEED)
    m.fit(X[tr], y[tr], eval_set=(X[va], y[va]),
          feature_names=[f"x{i}" for i in range(X.shape[1])])
    auc = roc_auc(y[te], m.predict_proba(X[te]))
    bayes = roc_auc(y[te], p[te])
    assert auc > 0.85, f"GBDT AUC {auc:.4f} too low"
    # Within 6 points of the theoretical ceiling on this problem.
    assert auc > bayes - 0.06, f"GBDT {auc:.4f} vs Bayes-optimal {bayes:.4f}"


def test_gbdt_beats_a_constant_predictor():
    X, y, _ = _problem(n=3000)
    m = GradientBoostingClassifier(n_estimators=60, max_depth=4, random_state=SEED).fit(X, y)
    probs = m.predict_proba(X)
    assert probs.std() > 0.01, "model output is nearly constant"
    assert (probs >= 0).all() and (probs <= 1).all(), "probabilities out of range"


def test_random_forest_learns_the_signal():
    X, y, _ = _problem(n=5000)
    tr, te = slice(0, 3800), slice(3800, 5000)
    m = RandomForestClassifier(n_estimators=60, max_depth=12, random_state=SEED)
    m.fit(X[tr], y[tr])
    auc = roc_auc(y[te], m.predict_proba(X[te]))
    assert auc > 0.72, f"RF AUC {auc:.4f} too low"


def test_importance_ranks_signal_above_noise():
    X, y, _ = _problem()
    names = [f"x{i}" for i in range(X.shape[1])]
    m = GradientBoostingClassifier(n_estimators=150, max_depth=5, random_state=SEED)
    m.fit(X, y, feature_names=names)
    imp = m.feature_importances_()
    assert abs(imp.sum() - 1.0) < 1e-6, "normalised importance must sum to 1"
    signal = imp[[0, 1, 2, 3]].sum()
    noise = imp[[4, 5, 6, 7]].sum()
    assert signal > noise, f"signal importance {signal:.3f} <= noise {noise:.3f}"
    top4 = {names[i] for i in np.argsort(-imp)[:4]}
    hits = len(top4 & {"x0", "x1", "x2", "x3"})
    assert hits >= 3, f"only {hits}/4 true features in the top 4: {top4}"


def test_save_load_round_trip_is_exact():
    X, y, _ = _problem(n=2500)
    for model in (GradientBoostingClassifier(n_estimators=40, max_depth=4, random_state=SEED),
                  RandomForestClassifier(n_estimators=25, max_depth=8, random_state=SEED)):
        model.fit(X, y, feature_names=[f"x{i}" for i in range(X.shape[1])])
        before = model.predict_proba(X[:200])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.json.gz"
            model.save(p)
            reloaded = BaseModel.load(p)
        after = reloaded.predict_proba(X[:200])
        np.testing.assert_allclose(before, after, rtol=0, atol=0,
                                   err_msg=f"{model.kind} round-trip changed predictions")


def test_early_stopping_truncates_to_best_iteration():
    X, y, _ = _problem(n=3000)
    m = GradientBoostingClassifier(n_estimators=400, learning_rate=0.2, max_depth=4,
                                   early_stopping_rounds=10, random_state=SEED)
    m.fit(X[:2200], y[:2200], eval_set=(X[2200:], y[2200:]))
    assert len(m.trees_) == m.best_iteration_, "stored model is not the best model"
    assert len(m.trees_) <= 400


def test_sigmoid_is_numerically_stable():
    z = np.array([-800.0, -50.0, 0.0, 50.0, 800.0])
    s = sigmoid(z)
    assert np.isfinite(s).all(), "sigmoid overflowed"
    assert s[0] >= 0.0 and s[-1] <= 1.0
    assert abs(s[2] - 0.5) < 1e-12


# ==========================================================================
# TreeSHAP — verified against the Shapley definition itself.
# ==========================================================================
def test_treeshap_matches_brute_force_shapley():
    """The decisive correctness test.

    `brute_force_shap` enumerates all 2^M subsets straight from the Shapley
    definition. Agreement means the fast algorithm is right.

    Tolerance note: the path-dependent recursion involves subtractive
    cancellation, so ~1e-8 residuals on values of magnitude ~0.3 are expected
    and are NOT a bug. A real indexing error produces O(1) errors that grow with
    depth, which is why depths 2-5 are all checked.
    """
    rng = np.random.default_rng(7)
    n, f = 4000, 6
    X = rng.normal(size=(n, f)).astype(np.float32)
    y = (rng.random(n) < 1.0 / (1.0 + np.exp(
        -(1.8 * X[:, 0] * X[:, 1] + 1.2 * X[:, 2] - X[:, 4])))).astype(float)

    worst = 0.0
    checks = 0
    for depth in (2, 3, 4, 5):
        m = GradientBoostingClassifier(n_estimators=6, max_depth=depth,
                                       learning_rate=0.3, max_bins=12,
                                       random_state=3).fit(X, y)
        Xb = m.binner_.transform(X[:5])
        for tree in m.trees_:
            for i in range(5):
                mine = np.zeros(f)
                _tree_shap_single(tree, Xb[i], mine)
                ref = brute_force_shap(tree, Xb[i], f)
                worst = max(worst, float(np.abs(mine - ref).max()))
                checks += 1
    assert checks > 100, "not enough comparisons to be meaningful"
    assert worst < 1e-6, (
        f"TreeSHAP disagrees with the Shapley definition by {worst:.3e} "
        f"across {checks} tree/row comparisons")


def test_treeshap_local_accuracy():
    """base + sum(phi) must equal the model's own output."""
    X, y, _ = _problem(n=2500, f=6)
    m = GradientBoostingClassifier(n_estimators=30, max_depth=4, random_state=SEED)
    m.fit(X, y, feature_names=[f"x{i}" for i in range(6)])
    phi, base = shap_values(m, X[:40], check=True)   # raises if violated
    got = base + phi.sum(axis=1)
    want = m.decision_function(X[:40])
    np.testing.assert_allclose(got, want, atol=1e-4,
                               err_msg="local accuracy (efficiency) violated")
    assert phi.shape == (40, 6)


def test_treeshap_zero_for_unused_features():
    """A feature the ensemble never splits on must receive exactly zero credit."""
    rng = np.random.default_rng(11)
    n = 2000
    X = np.zeros((n, 5), dtype=np.float32)
    X[:, 0] = rng.normal(size=n)
    X[:, 1] = rng.normal(size=n)
    # columns 2..4 are constant, so no split can ever use them
    y = (X[:, 0] + 0.5 * X[:, 1] > 0).astype(float)
    m = GradientBoostingClassifier(n_estimators=20, max_depth=3, random_state=SEED).fit(X, y)
    phi, _ = shap_values(m, X[:30], check=False)
    assert np.abs(phi[:, 2:]).max() < 1e-9, "constant features received attribution"
