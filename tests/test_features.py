"""
The causality tests — the most important file in this suite.

The whole project's credibility rests on features for transaction *t* using only
information available strictly before *t*. `test_causality_under_truncation` is
the test that actually proves it: build features on a stream, then rebuild on the
same stream truncated after row k, and require the first k rows to be identical.

If any feature peeked forward — a full-series mean, a groupby without a shift, a
rolling window with the wrong closure — truncating the future would change the
past and this test would fail.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from conftest import SEED, tiny_features, tiny_legit_tx, tiny_population
from sovereignguard.features import DAY, assert_no_leakage, build_features
from sovereignguard.schema import FEATURE_COLUMNS, LABEL_COLUMNS


def test_feature_matrix_shape_and_finiteness():
    F = tiny_features()
    tx = tiny_legit_tx()
    assert len(F) == len(tx), "one feature row per transaction"
    assert list(F.columns) == FEATURE_COLUMNS, "column order is the model contract"
    arr = F.to_numpy()
    assert np.isfinite(arr).all(), "no NaN or inf may reach the model"


def test_assert_no_leakage_passes_and_catches_injection():
    F = tiny_features()
    assert_no_leakage(F)                      # clean matrix passes

    bad = F.copy()
    bad["fraud_label"] = 0                    # inject a label column
    try:
        assert_no_leakage(bad)
    except AssertionError:
        pass
    else:
        raise AssertionError("assert_no_leakage failed to catch an injected label")

    missing = F.drop(columns=[FEATURE_COLUMNS[0]])
    try:
        assert_no_leakage(missing)
    except AssertionError:
        pass
    else:
        raise AssertionError("assert_no_leakage failed to catch a missing feature")


def test_causality_under_truncation():
    """THE causality guarantee. Truncating the future must not change the past."""
    cu, me, dv = tiny_population()
    tx = tiny_legit_tx().sort_values(
        ["timestamp", "transaction_id"], kind="mergesort").reset_index(drop=True)
    full = build_features(tx, cu, me, dv)

    n = len(tx)
    for frac in (0.25, 0.5, 0.75):
        k = int(n * frac)
        trunc = build_features(tx.iloc[:k].copy(), cu, me, dv)
        a = full.iloc[:k].to_numpy()
        b = trunc.to_numpy()
        assert a.shape == b.shape, f"shape mismatch at k={k}"
        # Exact equality: these are deterministic functions of the past.
        if not np.array_equal(a, b):
            diff = np.argwhere(a != b)
            col = FEATURE_COLUMNS[int(diff[0][1])]
            raise AssertionError(
                f"FEATURE LEAKS THE FUTURE at k={k}: column '{col}' changed when "
                f"later rows were removed ({len(diff)} differing cells). "
                f"first: row {diff[0][0]} full={a[tuple(diff[0])]} "
                f"trunc={b[tuple(diff[0])]}")


def test_is_new_device_marks_only_first_appearance():
    cu, me, dv = tiny_population()
    tx = tiny_legit_tx().sort_values(
        ["timestamp", "transaction_id"], kind="mergesort").reset_index(drop=True)
    F = build_features(tx, cu, me, dv)
    seen = set()
    checked = 0
    for i in range(len(tx)):
        key = (tx["customer_id"].iloc[i], tx["device_id"].iloc[i])
        expected = 0.0 if key in seen else 1.0
        got = float(F["is_new_device"].iloc[i])
        assert got == expected, (
            f"row {i}: is_new_device={got}, expected {expected} for {key}")
        seen.add(key)
        checked += 1
    assert checked > 100


def test_velocity_windows_hand_computed():
    """Hand-built timeline with known answers, so the window maths is verified
    against arithmetic rather than against itself."""
    cu, me, dv = tiny_population()
    cust = cu.iloc[0]
    mer = me.iloc[0]
    base = 1_735_689_600
    # offsets in seconds: 0, 5min, 20min, 2h, 30h
    offsets = [0, 300, 1_200, 7_200, 30 * 3_600]
    rows = []
    for i, off in enumerate(offsets):
        rows.append({
            "transaction_id": f"T{i}", "customer_id": cust.customer_id,
            "merchant_id": mer.merchant_id, "timestamp": base + off,
            "amount": 100.0 * (i + 1), "payment_method": "UPI", "channel": "APP",
            "transaction_type": "PURCHASE", "device_id": cust.primary_device_id,
            "city": cust.home_city, "lat": cust.home_lat, "lon": cust.home_lon,
            "beneficiary_id": "", "auth_result": "APPROVED",
            "mcc_category": mer.category, "session_id": f"S{i}",
            "password_changed_recently": 0, "profile_changed_recently": 0,
            "failed_logins_1h": 0, "session_duration_s": 60.0,
            "typing_cadence_dev": 0.05, "ip_asn_type": "MOBILE",
            "is_new_beneficiary": 0, "sim_swapped_recently": 0,
            "inbound_call_active": 0, "payment_link_referred": 0,
            "fraud_label": 0, "attack_type": "NONE", "attack_id": "",
            "attack_stage": "", "difficulty": "", "generator": "test",
            "campaign_id": "",
        })
    tx = pd.DataFrame(rows)
    F = build_features(tx, cu, me, dv)

    # txns_last_10min counts PRIOR events within 600s (self excluded)
    assert list(F["txns_last_10min"]) == [0, 1, 0, 0, 0], list(F["txns_last_10min"])
    # within 1h: T0; T0,T1; T0,T1,T2 -> then T3 at 2h sees T1,T2? no: 7200-1200=6000 > 3600
    assert list(F["txns_last_1h"]) == [0, 1, 2, 0, 0], list(F["txns_last_1h"])
    # within 24h: cumulative for the first four, then T4 at 30h sees none
    assert list(F["txns_last_24h"]) == [0, 1, 2, 3, 0], list(F["txns_last_24h"])
    # amount_sum_24h excludes self
    assert list(F["amount_sum_24h"]) == [0.0, 100.0, 300.0, 600.0, 0.0], \
        list(F["amount_sum_24h"])
    # seconds_since_prev_txn
    got = [int(x) for x in F["seconds_since_prev_txn"]]
    assert got[1:] == [300, 900, 6000, 100_800], got


def test_amount_ratio_is_centred_for_legitimate_traffic():
    """If the median legitimate transaction were not ~1x the customer's median,
    the amount features would be miscalibrated and the fraud signal illusory."""
    F = tiny_features()
    med = float(F["amount_ratio_customer_median"].median())
    assert 0.7 < med < 1.4, f"median amount ratio {med:.3f} is not near 1.0"


def test_beneficiary_age_sentinel_for_non_transfers():
    F = tiny_features()
    tx = tiny_legit_tx().sort_values(
        ["timestamp", "transaction_id"], kind="mergesort").reset_index(drop=True)
    no_ben = tx["beneficiary_id"].to_numpy() == ""
    if no_ben.any():
        vals = F["beneficiary_age_seconds"].to_numpy()[no_ben]
        assert (vals == 30 * DAY).all(), "non-transfers must use the n/a sentinel"
