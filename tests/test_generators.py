"""Generators: population realism, and the label-oracle guard."""
from __future__ import annotations

import numpy as np

from conftest import SEED, tiny_legit_tx, tiny_population
from sovereignguard import config as C
from sovereignguard.generators.attacks import KNOBS
from sovereignguard.generators.families import GENERATORS
from sovereignguard.generators.transactions import DAY, SIM_EPOCH
from sovereignguard.schema import (CUSTOMER_COLUMNS, DEVICE_COLUMNS,
                                   MERCHANT_COLUMNS, TRANSACTION_COLUMNS)


def test_population_schemas():
    cu, me, dv = tiny_population()
    assert list(cu.columns) == CUSTOMER_COLUMNS
    assert list(me.columns) == MERCHANT_COLUMNS
    assert list(dv.columns) == DEVICE_COLUMNS
    assert cu["customer_id"].is_unique and me["merchant_id"].is_unique
    assert dv["device_id"].is_unique
    assert (cu["account_age_days"] > 0).all()
    assert (cu["median_amount"] > 0).all()
    assert (me["median_ticket"] > 0).all()


def test_personas_are_economically_ordered():
    """A student and a high-net-worth customer must not look alike, or the
    per-customer amount features carry no information."""
    cu, _, _ = tiny_population()
    by = cu.groupby("persona")["median_amount"].median()
    if "STUDENT" in by and "HIGH_NET_WORTH" in by:
        assert by["STUDENT"] < by["HIGH_NET_WORTH"], by.to_dict()
    if "STUDENT" in by and "SMALL_BUSINESS" in by:
        assert by["STUDENT"] < by["SMALL_BUSINESS"], by.to_dict()


def test_generated_customers_are_not_synthetic_identities():
    cu, _, _ = tiny_population()
    assert (cu["is_synthetic_identity"] == 0).all(), \
        "the honest population must contain no fabricated identities"


def test_transactions_are_well_formed():
    tx = tiny_legit_tx()
    assert list(tx.columns) == TRANSACTION_COLUMNS
    assert len(tx) > 500
    assert tx["transaction_id"].is_unique
    assert (tx["amount"] > 0).all() and np.isfinite(tx["amount"]).all()
    assert (tx["fraud_label"] == 0).all(), "legit generator must not emit fraud"
    assert tx["timestamp"].is_monotonic_increasing


def test_transactions_fall_inside_the_simulation_window():
    tx = tiny_legit_tx()
    assert tx["timestamp"].min() >= SIM_EPOCH
    assert tx["timestamp"].max() < SIM_EPOCH + 13 * DAY   # 12-day window + slack


def test_amount_distribution_is_heavy_tailed_not_uniform():
    """`amount = random(1, 100000)` would make the whole project meaningless."""
    tx = tiny_legit_tx()
    a = tx["amount"].to_numpy()
    med, p99 = np.median(a), np.percentile(a, 99)
    assert p99 / med > 8, f"tail too thin (p99/median={p99/med:.1f}) — looks uniform"
    # a uniform sample would put ~50% of mass above the midpoint of the range
    frac_above_mid = float((a > (a.min() + a.max()) / 2).mean())
    assert frac_above_mid < 0.05, f"{frac_above_mid:.3f} of mass above midpoint"


def test_legitimate_traffic_has_low_but_nonzero_risk_events():
    """THE LABEL-ORACLE GUARD.

    If honest customers never changed device, added a payee or travelled, those
    flags would perfectly identify fraud and every reported metric would be a
    lie. They must occur — rarely.
    """
    tx = tiny_legit_tx()
    checks = {
        "is_new_beneficiary": (0.0, 0.10),
        "password_changed_recently": (0.0, 0.35),
        "profile_changed_recently": (0.0, 0.45),
        "payment_link_referred": (0.0, 0.25),
    }
    for col, (lo, hi) in checks.items():
        rate = float(tx[col].mean())
        assert rate > lo, (
            f"'{col}' never occurs in honest traffic — it becomes a perfect "
            f"fraud oracle and invalidates every metric")
        assert rate < hi, f"'{col}' rate {rate:.4f} implausibly high for honest traffic"

    # devices: at least one customer must legitimately use more than one
    per_cust = tx.groupby("customer_id")["device_id"].nunique()
    assert (per_cust > 1).any(), "no honest customer ever switches device"
    assert float((per_cust > 1).mean()) < 0.8, "too many multi-device customers"

    # geography: some customers travel
    cities = tx.groupby("customer_id")["city"].nunique()
    assert (cities > 1).any(), "no honest customer ever travels"


def test_all_seven_attack_generators_produce_sequences():
    from sovereignguard.generators.attacks import build_victim_contexts
    cu, me, dv = tiny_population()
    tx = tiny_legit_tx()
    ctx = build_victim_contexts(tx, cu)
    assert ctx, "no victim contexts built"
    victim = list(ctx.values())[0]
    rng = np.random.default_rng(SEED)
    cashout = me["merchant_id"].to_numpy()

    assert set(GENERATORS) == set(C.ATTACK_TYPES)
    for name, gen in GENERATORS.items():
        for diff in ("EASY", "HARD"):
            k = KNOBS[diff]
            v = victim.anchored(victim.last_ts)
            if name == "MERCHANT_FRAUD":
                extras = [list(ctx.values())[i] for i in range(1, min(5, len(ctx)))]
                res = gen(v, k, rng, me, cashout, f"T{name[:3]}{diff[:1]}", extra_victims=extras)
            else:
                res = gen(v, k, rng, me, cashout, f"T{name[:3]}{diff[:1]}")
            assert res.events, f"{name}/{diff} produced no events"
            for e in res.events:
                assert e["fraud_label"] == 1, f"{name} emitted an unlabelled event"
                assert e["attack_type"] == name
                assert e["difficulty"] == diff
                assert e["amount"] > 0
                assert set(e) == set(TRANSACTION_COLUMNS), \
                    f"{name} event has wrong columns"
            # multi-event sequences are the point; most families must exceed 1
            if name not in ("PHISHING_PAYMENT_LINK",):
                assert len(res.events) >= 2, f"{name}/{diff} is not a sequence"


def test_difficulty_knobs_are_ordered_by_stealth():
    """HARD must be strictly stealthier than EASY on every axis that matters."""
    e, h, a = KNOBS["EASY"], KNOBS["HARD"], KNOBS["ADVERSARIAL"]
    assert h.p_new_device < e.p_new_device
    assert h.p_new_city < e.p_new_city
    assert h.p_hosting_ip < e.p_hosting_ip
    assert h.amount_mult_hi < e.amount_mult_hi
    assert h.gap_lo_s > e.gap_lo_s, "hard attacks must be more patient"
    assert h.spread_days > e.spread_days
    assert a.p_new_device <= h.p_new_device
    assert a.amount_mult_hi <= h.amount_mult_hi
    assert h.stay_under_p95 and a.stay_under_p95


def test_redteam_diversity_is_measured():
    from sovereignguard.generators.redteam import RedTeam
    cu, me, dv = tiny_population()
    rt = RedTeam(cu, me, tiny_legit_tx(), SEED)
    b = rt.generate(60)
    assert b.n_scenarios > 0 and b.n_events > b.n_scenarios
    d = b.diversity_report()
    assert d["attack_types"] >= 5, f"only {d['attack_types']} families sampled"
    assert d["distinct_victims"] > 5
    assert 0.0 <= d["entropy_attack_type"] <= 1.0
    assert d["amount_span_log10"] > 1.0, "attack amounts span too narrow a range"


def test_attacks_are_spread_over_time_not_piled_at_the_end():
    """Regression test for a real bug: anchoring every attack at the victim's
    last transaction starved the time-ordered training split of positives."""
    from sovereignguard.generators.redteam import RedTeam
    cu, me, dv = tiny_population()
    tx = tiny_legit_tx()
    rt = RedTeam(cu, me, tx, SEED)
    b = rt.generate(80)
    ts = b.events["timestamp"].to_numpy()
    lo, hi = tx["timestamp"].min(), tx["timestamp"].max()
    span = hi - lo
    early = float((ts < lo + span * 0.5).mean())
    assert early > 0.15, (
        f"only {early:.1%} of attack events land in the first half of the "
        f"window — attacks are piling up at the end")
