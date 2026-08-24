"""Metrics, risk engine, and the threshold policy — known-answer tests."""
from __future__ import annotations

import numpy as np

from sovereignguard import config as C
from sovereignguard.evaluation.metrics import (average_precision, bootstrap_ci,
                                               choose_threshold_at_fpr,
                                               choose_threshold_max_f1,
                                               compute_metrics, operating_curve,
                                               per_group_metrics, roc_auc)
from sovereignguard.risk import RiskEngine


# ---------------------------------------------------------------- metrics
def test_roc_auc_known_answer():
    """Reference value from scikit-learn's documented example."""
    y = np.array([0, 0, 1, 1])
    s = np.array([0.1, 0.4, 0.35, 0.8])
    assert abs(roc_auc(y, s) - 0.75) < 1e-9


def test_average_precision_known_answer():
    y = np.array([0, 0, 1, 1])
    s = np.array([0.1, 0.4, 0.35, 0.8])
    assert abs(average_precision(y, s) - 0.8333333) < 1e-4


def test_roc_auc_perfect_and_tied():
    y = np.r_[np.zeros(50), np.ones(50)]
    assert roc_auc(y, y) == 1.0
    assert abs(roc_auc(y, np.ones(100)) - 0.5) < 1e-12, "all-tied scores must give 0.5"
    assert abs(roc_auc(y, 1 - y) - 0.0) < 1e-12, "perfectly inverted must give 0.0"


def test_roc_auc_undefined_for_single_class():
    assert np.isnan(roc_auc(np.zeros(10), np.random.random(10)))


def test_confusion_matrix_hand_computed():
    #      score>=0.5 :  T  T  F  F
    y = np.array([1, 0, 1, 0])
    p = np.array([0.9, 0.8, 0.2, 0.1])
    m = compute_metrics(y, p, 0.5)
    assert (m.tp, m.fp, m.tn, m.fn) == (1, 1, 1, 1), (m.tp, m.fp, m.tn, m.fn)
    assert abs(m.precision - 0.5) < 1e-12
    assert abs(m.recall - 0.5) < 1e-12
    assert abs(m.f1 - 0.5) < 1e-12
    assert abs(m.fpr - 0.5) < 1e-12
    assert abs(m.fnr - 0.5) < 1e-12
    assert abs(m.accuracy - 0.5) < 1e-12


def test_metrics_never_report_accuracy_alone():
    """Guard against regression: at 1% prevalence a trivial model scores 99%."""
    y = np.r_[np.zeros(9900), np.ones(100)]
    p = np.zeros(10000)                      # predict "legitimate" for everything
    m = compute_metrics(y, p, 0.5)
    assert m.accuracy >= 0.98, "sanity: the trivial model does score high accuracy"
    assert m.recall == 0.0 and m.f1 == 0.0, \
        "recall/F1 must expose the trivial model as useless"


def test_threshold_respects_the_fpr_budget():
    rng = np.random.default_rng(0)
    y = np.r_[np.zeros(10000), np.ones(500)]
    p = np.r_[rng.beta(2, 8, 10000), rng.beta(6, 3, 500)]
    for budget in (0.0005, 0.001, 0.005, 0.01, 0.02, 0.05):
        thr = choose_threshold_at_fpr(y, p, budget)
        m = compute_metrics(y, p, thr)
        assert m.fpr <= budget + 1e-9, \
            f"budget {budget} exceeded: realised FPR {m.fpr:.6f}"


def test_recall_is_monotonic_in_the_fpr_budget():
    rng = np.random.default_rng(1)
    y = np.r_[np.zeros(6000), np.ones(300)]
    p = np.r_[rng.beta(2, 8, 6000), rng.beta(5, 3, 300)]
    curve = operating_curve(y, p)
    recalls = [c["recall"] for c in curve]
    assert recalls == sorted(recalls), f"recall not monotonic in budget: {recalls}"


def test_max_f1_threshold_beats_an_arbitrary_one():
    rng = np.random.default_rng(2)
    y = np.r_[np.zeros(3000), np.ones(200)]
    p = np.r_[rng.beta(2, 8, 3000), rng.beta(5, 3, 200)]
    thr = choose_threshold_max_f1(y, p)
    best = compute_metrics(y, p, thr).f1
    for other in (0.1, 0.3, 0.5, 0.7, 0.9):
        assert best >= compute_metrics(y, p, other).f1 - 1e-9


def test_per_group_metrics_sums_are_consistent():
    rng = np.random.default_rng(3)
    y = np.r_[np.zeros(1000), np.ones(200)]
    p = np.r_[rng.random(1000) * 0.4, rng.random(200)]
    g = np.array(["a"] * 600 + ["b"] * 400 + ["a"] * 100 + ["b"] * 100)
    rows = per_group_metrics(y, p, g, 0.5)
    assert sum(r["n"] for r in rows) == 200, "groups must partition the positives"
    for r in rows:
        assert r["detected"] + r["missed"] == r["n"]
        assert 0.0 <= r["recall"] <= 1.0
    assert [r["recall"] for r in rows] == sorted(r["recall"] for r in rows), \
        "rows should be worst-first so weaknesses are visible"


def test_bootstrap_ci_brackets_the_point_estimate():
    rng = np.random.default_rng(4)
    y = np.r_[np.zeros(2000), np.ones(200)]
    p = np.r_[rng.beta(2, 8, 2000), rng.beta(6, 3, 200)]
    ci = bootstrap_ci(y, p, 0.5, "recall", n_boot=80, seed=4)
    assert ci["lo"] <= ci["point"] <= ci["hi"], ci
    assert ci["hi"] - ci["lo"] < 0.5, "CI implausibly wide"


# ------------------------------------------------------------------- risk
def test_risk_score_is_monotonic_in_probability():
    eng = RiskEngine(operating_threshold=0.2)
    p = np.linspace(0, 1, 501)
    s = eng.score(p)
    assert np.all(np.diff(s) >= -1e-9), "risk score must be non-decreasing"
    assert abs(s[0]) < 1e-9 and abs(s[-1] - 100.0) < 1e-9


def test_operating_threshold_maps_to_the_step_up_edge():
    """The policy bands must stay aligned with the model's calibration, so the
    tuned threshold has to land exactly on the challenge boundary."""
    for thr in (0.02, 0.1, 0.35, 0.8):
        eng = RiskEngine(operating_threshold=thr)
        edge = eng.anchor_score
        got = float(eng.score(np.array([thr]))[0])
        assert abs(got - edge) < 1e-6, f"threshold {thr} -> {got}, expected {edge}"
        d = eng.decide(thr)
        assert d.action == "STEP_UP_AUTH", f"threshold decides {d.action}"


def test_bands_cover_every_score():
    eng = RiskEngine(operating_threshold=0.3)
    for v in np.linspace(0, 100, 401):
        b = eng.band_for(float(v))
        assert b is not None and b.lower <= v < b.upper or v >= 100


def test_distribution_and_friction_are_well_formed():
    rng = np.random.default_rng(5)
    y = np.r_[np.zeros(1500), np.ones(150)]
    p = np.r_[rng.beta(2, 9, 1500), rng.beta(6, 3, 150)]
    eng = RiskEngine(operating_threshold=0.4)
    dist = eng.distribution(p, y)
    assert sum(r["count"] for r in dist) == len(p), "bands must account for every row"
    assert abs(sum(r["share"] for r in dist) - 1.0) < 1e-9
    assert abs(sum(r["share_of_all_fraud"] for r in dist) - 1.0) < 1e-6
    fr = eng.friction_summary(p, y)
    for k, v in fr.items():
        if k.endswith("_share"):
            assert 0.0 <= v <= 1.0, f"{k}={v} out of range"


def test_low_risk_allows_and_critical_holds():
    eng = RiskEngine(operating_threshold=0.5)
    assert eng.decide(0.0).action == "ALLOW"
    assert eng.decide(1.0).action == "HOLD_REVIEW"
