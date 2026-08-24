"""
Adversarial leakage audit — the tests that try to break the project's own claims.

These are not unit tests. Each one is an attempt to prove that a reported metric
is an artefact rather than a result. Two real leaks were found and fixed by
exactly this kind of check, and both are pinned here so they cannot return:

  1. `device_reputation` was set to 0.12 for attacker-created devices, making it
     a perfect label oracle.
  2. After fixing (1), newly-registered devices were still drawn from a
     different Beta distribution than the original registry, so the
     *registration event itself* leaked the label (0.41 mean vs 0.80).
"""
from __future__ import annotations

import numpy as np

from conftest import SEED, tiny_world
from sovereignguard.evaluation.metrics import roc_auc
from sovereignguard.schema import FEATURE_COLUMNS, LABEL_COLUMNS

# A single feature scoring above this against the label is not a feature, it is
# a leak. Real behavioural signals top out well below it.
ORACLE_AUC = 0.99


def test_no_single_feature_is_a_label_oracle():
    """The strongest available leakage test.

    A legitimate feature correlates with fraud. A leaked one *separates* it. Any
    single column reaching ~1.0 AUC means the label reached the model by a route
    it should not have.
    """
    w = tiny_world()
    y = w.tx["fraud_label"].to_numpy()
    scores = []
    for c in FEATURE_COLUMNS:
        a = roc_auc(y, w.feats[c].to_numpy())
        if a is not None and not np.isnan(a):
            scores.append((max(a, 1.0 - a), c))
    scores.sort(reverse=True)
    top, name = scores[0]
    assert top < ORACLE_AUC, (
        f"feature '{name}' separates the label almost perfectly (AUC {top:.4f}). "
        f"This is a leak, not a signal. Top 5: "
        f"{[(round(a,4), c) for a, c in scores[:5]]}")


def test_no_binary_feature_equals_the_label():
    w = tiny_world()
    y = w.tx["fraud_label"].to_numpy()
    for c in FEATURE_COLUMNS:
        v = w.feats[c].to_numpy()
        if len(np.unique(v)) != 2:
            continue
        vb = (v > np.median(v)).astype(int)
        assert not np.array_equal(vb, y), f"feature '{c}' IS the label"
        assert not np.array_equal(1 - vb, y), f"feature '{c}' is the inverted label"


def test_attacker_devices_are_registered_indistinguishably():
    """REGRESSION: attacker-created devices must not be identifiable from the
    device registry alone.

    Compares against the legitimate population using a binomial tolerance for
    the rare boolean flags — with ~20 attacker devices and a 2.6% base rate,
    observing zero rooted devices is expected, so a naive ratio test produces a
    false alarm. Reputation is a continuous mean and is compared directly.
    """
    w = tiny_world()
    dv = w.devices
    atk = dv["device_id"].str.startswith(("DEV_ATK_", "DEV_SYN_")).to_numpy()
    if atk.sum() < 3:
        return                                  # nothing to test at this scale

    rep_atk = float(dv.loc[atk, "reputation"].mean())
    rep_leg = float(dv.loc[~atk, "reputation"].mean())
    assert abs(rep_atk - rep_leg) < 0.15, (
        f"attacker devices have mean reputation {rep_atk:.3f} vs {rep_leg:.3f} "
        f"for legitimate devices — the registration event leaks the label")

    n = int(atk.sum())
    for col in ("is_emulator", "is_rooted"):
        p_leg = float(dv.loc[~atk, col].mean())
        k_atk = int(dv.loc[atk, col].sum())
        # Upper bound: 4 standard deviations of Binomial(n, p_leg), floor of 2
        # so tiny samples do not trip on a single observation.
        sd = (n * p_leg * (1 - p_leg)) ** 0.5
        allowed = max(2.0, n * p_leg + 4.0 * sd)
        assert k_atk <= allowed, (
            f"{k_atk}/{n} attacker devices have {col}=1, but the legitimate base "
            f"rate {p_leg:.4f} allows at most ~{allowed:.1f}. This flag leaks.")


def test_synthetic_identity_customers_are_not_trivially_flagged():
    """Fabricated identities SHOULD look different — that is the fraud — but not
    so different that a single threshold separates them perfectly."""
    w = tiny_world()
    cu = w.customers
    syn = cu["is_synthetic_identity"].to_numpy() == 1
    if syn.sum() < 3:
        return
    for col in ("identity_doc_score", "contactability_score", "digital_footprint_days"):
        a = roc_auc(syn.astype(int), cu[col].to_numpy())
        if a is None or np.isnan(a):
            continue
        sep = max(a, 1 - a)
        assert sep < ORACLE_AUC, (
            f"customers.{col} separates synthetic identities at AUC {sep:.4f} — "
            f"the origination signal is too clean to be a realistic problem")


def test_fraud_is_spread_across_the_time_window():
    """REGRESSION: attacks anchored at each victim's last transaction piled all
    fraud at the end of the stream, starving the time-ordered training split."""
    w = tiny_world()
    ts = w.tx["timestamp"].to_numpy()
    y = w.tx["fraud_label"].to_numpy()
    lo, hi = ts.min(), ts.max()
    first_half = float((ts[y == 1] < lo + (hi - lo) * 0.5).mean())
    assert first_half > 0.15, (
        f"only {first_half:.1%} of fraud events fall in the first half of the "
        f"window — a time-ordered split will have almost nothing to train on")


def test_attack_and_legit_transaction_ids_are_not_the_signal():
    """The model must never see identifiers, but check the *shape* of the data
    too: a systematic difference in id format would be a leak if any feature
    were ever derived from it."""
    w = tiny_world()
    assert "transaction_id" not in FEATURE_COLUMNS
    assert "attack_id" not in FEATURE_COLUMNS
    assert "customer_id" not in FEATURE_COLUMNS
    assert "device_id" not in FEATURE_COLUMNS
    assert not (set(FEATURE_COLUMNS) & set(LABEL_COLUMNS))


def test_amount_alone_does_not_solve_the_problem():
    """If raw amount were sufficient, the whole feature engineering effort — and
    the difficulty gradient — would be theatre."""
    w = tiny_world()
    y = w.tx["fraud_label"].to_numpy()
    a = roc_auc(y, w.feats["amount"].to_numpy())
    assert a is None or np.isnan(a) or max(a, 1 - a) < 0.95, (
        f"raw amount alone reaches AUC {a:.4f} — the attacks are not subtle enough "
        f"for the rest of the system to be meaningful")


def test_hard_attacks_are_measurably_harder_than_easy_ones():
    """The difficulty gradient must be real, not a label written on the data."""
    w = tiny_world()
    y = w.tx["fraud_label"].to_numpy()
    diff = w.tx["difficulty"].to_numpy()
    legit = y == 0
    F = w.feats

    def dist_from_legit(mask):
        """Crude multivariate distance: mean |z| of the attack rows against the
        legitimate distribution on the headline behavioural features."""
        cols = ["amount_ratio_customer_median", "is_new_device",
                "distance_from_home_km", "amount_pct_of_credit_limit"]
        tot = 0.0
        for c in cols:
            v = F[c].to_numpy()
            mu, sd = v[legit].mean(), max(v[legit].std(), 1e-9)
            tot += abs((v[mask].mean() - mu) / sd)
        return tot / len(cols)

    easy = (y == 1) & (diff == "EASY")
    hard = (y == 1) & (diff == "HARD")
    if easy.sum() < 5 or hard.sum() < 5:
        return
    d_easy, d_hard = dist_from_legit(easy), dist_from_legit(hard)
    assert d_hard < d_easy, (
        f"HARD attacks ({d_hard:.3f}) are not closer to legitimate behaviour than "
        f"EASY ones ({d_easy:.3f}) — the difficulty levels are not doing anything")
