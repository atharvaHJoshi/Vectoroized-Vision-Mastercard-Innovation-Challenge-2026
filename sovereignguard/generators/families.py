"""
The seven attack-family generators (Phase 9).

Each returns `AttackResult(events, extra_customers, extra_merchants)`.
Most attacks abuse an existing victim; SYNTHETIC_IDENTITY mints a new customer
and MERCHANT_FRAUD mints a new merchant, so those two also return entities that
must be appended to the population before feature building.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from .. import config as C
from ..schema import CUSTOMER_COLUMNS, MERCHANT_COLUMNS
from .attacks import (KNOBS, Knobs, VictimContext, _asn, _base_event, _drain_amount,
                      _merchant_for_cashout, _pick_city, _pick_device, _pick_hour_ts)
from .transactions import DAY, _empty_event


@dataclass
class AttackResult:
    events: List[Dict] = field(default_factory=list)
    extra_customers: List[Dict] = field(default_factory=list)
    extra_merchants: List[Dict] = field(default_factory=list)


# ==========================================================================
# 1. ACCOUNT TAKEOVER
# ==========================================================================
def gen_account_takeover(v: VictimContext, k: Knobs, rng, merchants, cashout_ids,
                         attack_id: str) -> AttackResult:
    """Recon login -> credential change -> payee add -> probe -> escalate -> drain.

    The HARD path reuses one of the victim's own devices (session hijack rather
    than a fresh login), reuses an existing payee, keeps every amount under the
    victim's own 95th percentile, and spreads the drain over days so no single
    24-hour velocity window looks abnormal.
    """
    res = AttackResult()
    device = _pick_device(v, k, rng, attack_id)
    city, lat, lon = _pick_city(v, k, rng)
    t = v.t0 - int(rng.integers(0, 3)) * DAY
    seq = 0

    cred_change = rng.random() < k.p_credential_change
    if k.p_reuse_existing_payee > rng.random() and v.known_beneficiaries:
        payee = str(rng.choice(v.known_beneficiaries))
        new_ben = 0
    else:
        payee = f"BEN_MULE_{attack_id}"
        new_ben = 1

    def step(stage, amount, ttype="TRANSFER", **kw):
        nonlocal t, seq
        t = _pick_hour_ts(v, k, rng, t + int(rng.integers(k.gap_lo_s, k.gap_hi_s + 1)))
        mid, cat = _merchant_for_cashout(v, k, merchants, rng, cashout_ids)
        ev = _base_event(v, k, rng, attack_type="ACCOUNT_TAKEOVER", attack_id=attack_id,
                         stage=stage, ts=t, amount=amount, merchant_id=mid, category=cat,
                         device_id=device, city=city, lat=lat, lon=lon, ttype=ttype,
                         beneficiary=payee if ttype == "TRANSFER" else "",
                         is_new_ben=new_ben if (ttype == "TRANSFER" and seq <= 2) else 0,
                         seq=seq, **kw)
        seq += 1
        res.events.append(ev)
        return ev

    # RECON_LOGIN — a tiny balance-check style event
    step("RECON_LOGIN", max(20.0, round(v.median_amount * 0.05, 2)), ttype="PURCHASE",
         failed_logins_1h=int(rng.integers(2, 7)) if k.label == "EASY" else 0,
         session_duration_s=float(rng.uniform(8, 40)))

    if cred_change:
        step("CREDENTIAL_CHANGE", max(20.0, round(v.median_amount * 0.08, 2)),
             ttype="PURCHASE", password_changed_recently=1, profile_changed_recently=1)

    if new_ben:
        step("PAYEE_ADD", max(20.0, round(v.median_amount * 0.1, 2)), ttype="TRANSFER")

    if rng.random() < k.p_probe:
        step("PROBE", float(round(v.median_amount * rng.uniform(0.15, 0.6), 2)))

    n = int(rng.integers(k.n_drain_lo, k.n_drain_hi + 1))
    # Spread the drain across the allowed number of days.
    day_span = max(1, k.spread_days)
    prev = None
    for j in range(n):
        amt = _drain_amount(v, k, rng)
        if prev is not None and k.label in ("EASY", "MEDIUM"):
            amt = max(amt, prev * float(rng.uniform(1.4, 2.6)))   # visible escalation
            amt = min(amt, v.credit_limit * 0.97)
        prev = amt
        stage = "DRAIN" if j == n - 1 else "ESCALATE"
        step(stage, amt)
        if day_span > 1 and (j + 1) % max(1, n // day_span) == 0:
            t += DAY
    return res


# ==========================================================================
# 2. TRANSACTION MANIPULATION (threshold probing / structuring)
# ==========================================================================
def gen_transaction_manipulation(v: VictimContext, k: Knobs, rng, merchants, cashout_ids,
                                 attack_id: str) -> AttackResult:
    """Probe the decision boundary, then structure the value beneath it.

    The evasive signature is regularity: humans spend in bursts, a script
    spends on a near-constant cadence. `seconds_since_prev_txn` variance is the
    feature that ought to catch this.
    """
    res = AttackResult()
    device = _pick_device(v, k, rng, attack_id)
    city, lat, lon = _pick_city(v, k, rng)
    t = v.t0 - int(rng.integers(0, 2)) * DAY
    seq = 0

    # Attacker's inferred ceiling: just under a round review limit.
    ceiling_base = float(rng.choice([5_000, 10_000, 25_000, 50_000]))
    ceiling = min(ceiling_base, max(v.p95_amount * 1.6, v.median_amount * 6))

    def step(stage, amount, **kw):
        nonlocal t, seq
        gap = int(rng.integers(k.gap_lo_s, k.gap_hi_s + 1))
        if k.label in ("HARD", "ADVERSARIAL"):
            gap = int(gap * rng.uniform(0.85, 1.15))    # near-constant cadence
        t = t + gap
        mid, cat = _merchant_for_cashout(v, k, merchants, rng, cashout_ids)
        res.events.append(_base_event(
            v, k, rng, attack_type="TRANSACTION_MANIPULATION", attack_id=attack_id,
            stage=stage, ts=t, amount=amount, merchant_id=mid, category=cat,
            device_id=device, city=city, lat=lat, lon=lon,
            ttype="TRANSFER" if rng.random() < 0.6 else "PURCHASE", seq=seq, **kw))
        seq += 1

    # PROBE / CALIBRATE — declined attempts reveal the boundary
    n_probe = int(rng.integers(2, 5))
    for _ in range(n_probe):
        over = ceiling * float(rng.uniform(1.05, 1.9))
        step("PROBE", round(min(over, v.credit_limit * 0.98), 2),
             auth_result="DECLINED_LIMIT")
    step("CALIBRATE", round(ceiling * 0.995, 2))

    # STRUCTURE — split the target value into sub-ceiling slices
    target = ceiling * float(rng.uniform(2.5, 7.0))
    n_slices = int(rng.integers(max(3, k.n_drain_lo), k.n_drain_hi + 4))
    slice_amt = target / n_slices
    for j in range(n_slices):
        jitter = float(rng.uniform(0.88, 1.12))
        amt = min(slice_amt * jitter, ceiling * 0.985)
        if k.stay_under_p95:
            amt = min(amt, v.p95_amount * float(rng.uniform(0.7, 1.0)))
        step("STRUCTURE" if j < n_slices - 1 else "REPEAT", round(max(20.0, amt), 2))
        if k.spread_days > 1 and (j + 1) % 3 == 0:
            t += DAY
    return res


# ==========================================================================
# 3. SYNTHETIC IDENTITY (mints a new customer)
# ==========================================================================
def gen_synthetic_identity(v: VictimContext, k: Knobs, rng, merchants, cashout_ids,
                           attack_id: str) -> AttackResult:
    """Fabricated identity onboards, cultivates good behaviour, then busts out.

    Detection here is an *origination* problem: the transaction stream is
    exemplary until the final stage. The signals that carry information are
    identity_doc_score, contactability_score and digital_footprint_days —
    which is exactly why they are features.
    """
    res = AttackResult()
    syn_id = f"CUST_SYN_{attack_id}"
    persona = str(rng.choice(["YOUNG_PROFESSIONAL", "SMALL_BUSINESS", "GIG_WORKER"]))
    p = C.PERSONA_BY_NAME[persona]
    city = str(rng.choice(C.CITY_NAMES))
    lat, lon, _ = C.CITIES[city]
    median_amount = float(np.exp(p.amount_mu + rng.normal(0, 0.2)))
    limit = float(np.clip(median_amount * rng.uniform(20, 60), 25_000, 900_000))
    # Stealth raises the quality of the fabricated evidence.
    #
    # LEAKAGE NOTE: these must OVERLAP the honest population, not sit beside it.
    # An earlier version gave synthetic identities an absolute footprint of
    # 5-900 days while honest customers got account_age + 120..3600, so the two
    # distributions barely intersected and `digital_footprint_days` became a
    # perfect oracle (AUC 1.000). Footprint is now expressed as a *ratio* of the
    # account age, which is the realistic tell: a fabricated identity has a
    # thinner history than its claimed age implies, but the absolute number sits
    # inside the range real customers occupy.
    account_age = int(rng.integers(*{"EASY": (2, 25), "MEDIUM": (20, 90),
                                     "HARD": (80, 260), "ADVERSARIAL": (240, 560)}[k.label]))
    doc_q = {"EASY": (0.05, 0.30), "MEDIUM": (0.25, 0.55),
             "HARD": (0.50, 0.78), "ADVERSARIAL": (0.68, 0.92)}[k.label]
    # honest customers sit at roughly 1.3x-5x their account age
    foot_ratio = {"EASY": (0.15, 0.7), "MEDIUM": (0.4, 1.3),
                  "HARD": (0.9, 2.6), "ADVERSARIAL": (1.4, 4.2)}[k.label]
    footprint = int(max(5, account_age * rng.uniform(*foot_ratio)))

    res.extra_customers.append({
        "customer_id": syn_id, "persona": persona,
        "age": int(rng.integers(24, 46)), "country": "IN",
        "home_city": city, "home_lat": lat, "home_lon": lon,
        "occupation": "Consultant", "account_age_days": account_age,
        "median_amount": round(median_amount, 2),
        "amount_sigma": round(float(p.amount_sigma), 4),
        "txns_per_day": round(float(p.txns_per_day * rng.uniform(0.5, 1.0)), 3),
        "preferred_method": "UPI", "primary_device_id": f"DEV_SYN_{attack_id}",
        "n_devices": 1, "night_activity": p.night_activity,
        "travel_propensity": 0.05, "new_merchant_rate": p.new_merchant_rate,
        "kyc_level": "BASIC" if k.label in ("EASY", "MEDIUM") else "FULL",
        "credit_limit": round(limit, 2),
        "is_synthetic_identity": 1,
        "identity_doc_score": round(float(rng.uniform(*doc_q)), 4),
        "contactability_score": round(float(rng.uniform(*doc_q)) * 0.85, 4),
        "digital_footprint_days": footprint,
    })

    syn_v = VictimContext(
        customer_id=syn_id, persona=persona, median_amount=median_amount,
        p95_amount=median_amount * 3.2, max_amount=median_amount * 4.0,
        credit_limit=limit, home_city=city, home_lat=lat, home_lon=lon,
        known_devices=[f"DEV_SYN_{attack_id}"], known_merchants=[],
        known_categories=[], known_beneficiaries=[], preferred_method="UPI",
        typical_hours=[11, 13, 19], last_ts=v.t0, n_txns=0)

    device = f"DEV_SYN_{attack_id}"
    # ONBOARD + CULTIVATE: normal-looking activity to build a record
    n_cult = {"EASY": 2, "MEDIUM": 6, "HARD": 16, "ADVERSARIAL": 28}[k.label]
    t = v.t0 - int(rng.integers(12, 26)) * DAY
    seq = 0
    for j in range(n_cult):
        t += int(rng.integers(6 * 3600, 30 * 3600))
        mid = str(rng.choice(merchants["merchant_id"].to_numpy()))
        cat = str(merchants.loc[merchants.merchant_id == mid, "category"].iloc[0])
        amt = float(round(median_amount * rng.uniform(0.4, 1.9), 2))
        res.events.append(_base_event(
            syn_v, k, rng, attack_type="SYNTHETIC_IDENTITY", attack_id=attack_id,
            stage="CULTIVATE" if j else "ONBOARD", ts=t, amount=amt,
            merchant_id=mid, category=cat, device_id=device,
            city=city, lat=lat, lon=lon, ttype="PURCHASE", seq=seq))
        seq += 1

    # LIMIT_GROWTH then BUST_OUT — consume the line
    t += int(rng.integers(1, 4)) * DAY
    n_bust = int(rng.integers(max(2, k.n_drain_lo), k.n_drain_hi + 1))
    remaining = limit * float(rng.uniform(0.72, 0.97))
    for j in range(n_bust):
        amt = float(round(remaining / max(1, n_bust - j) * rng.uniform(0.7, 1.15), 2))
        amt = min(amt, remaining)
        remaining -= amt
        t += int(rng.integers(k.gap_lo_s, k.gap_hi_s + 1))
        mid, cat = _merchant_for_cashout(syn_v, k, merchants, rng, cashout_ids)
        res.events.append(_base_event(
            syn_v, k, rng, attack_type="SYNTHETIC_IDENTITY", attack_id=attack_id,
            stage="LIMIT_GROWTH" if j < n_bust - 1 else "BUST_OUT", ts=t,
            amount=max(20.0, amt), merchant_id=mid, category=cat, device_id=device,
            city=city, lat=lat, lon=lon,
            ttype="TRANSFER", beneficiary=f"BEN_MULE_{attack_id}",
            is_new_ben=1 if j == 0 else 0, seq=seq))
        seq += 1
        if remaining <= 20:
            break
    return res


# ==========================================================================
# 4. MERCHANT FRAUD (mints a fraudulent merchant, many victims)
# ==========================================================================
def gen_merchant_fraud(v: VictimContext, k: Knobs, rng, merchants, cashout_ids,
                       attack_id: str, extra_victims: Optional[List[VictimContext]] = None
                       ) -> AttackResult:
    """A fabricated storefront takes volume from many first-time payers.

    The signature is acceptance-side, not customer-side: merchant_age_days,
    merchant_new_customer_share_24h and a ticket distribution inconsistent with
    the declared category. That is why the generator needs several victims.
    """
    res = AttackResult()
    mer_id = f"MER_FRAUD_{attack_id}"
    cat = str(rng.choice(["ECOMMERCE", "GAMING", "CRYPTO_GATEWAY", "FINANCIAL_SERVICES",
                          "TRAVEL", "ENTERTAINMENT"]))
    spec = C.CATEGORY_BY_NAME[cat]
    city = str(rng.choice(C.CITY_NAMES))
    lat, lon, _ = C.CITIES[city]
    # Stealth ages the merchant record and softens its risk profile.
    age = int(rng.integers(*{"EASY": (0, 6), "MEDIUM": (5, 40),
                             "HARD": (35, 200), "ADVERSARIAL": (180, 620)}[k.label]))
    median_ticket = float(np.exp(spec.base_ticket + rng.normal(0, 0.35)))
    res.extra_merchants.append({
        "merchant_id": mer_id, "merchant_name": f"Nova {cat.title()} Store",
        "category": cat, "merchant_size": "SMALL", "merchant_age_days": age,
        "city": city, "lat": lat, "lon": lon,
        "median_ticket": round(median_ticket, 2),
        "ticket_sigma": round(float(spec.ticket_sigma), 4),
        "daily_volume": round(float(rng.uniform(20, 700)), 1),
        "intrinsic_risk": round(float(np.clip(spec.intrinsic_risk * 1.2, 0, 1)), 4),
        "cnp_share": 1.0,
        "chargeback_rate": round(float(rng.uniform(0.02, 0.30)) *
                                 (0.25 if k.label == "ADVERSARIAL" else 1.0), 5),
        "is_fraud_merchant": 1,
        "onboarded_via": "SELF_SERVE" if k.label in ("EASY", "MEDIUM") else "AGGREGATOR",
    })

    victims = [v] + list(extra_victims or [])
    t0 = v.t0 - int(rng.integers(0, 3)) * DAY
    seq = 0
    # SEED_TRAFFIC (stealthy only) then RAMP / CASH_OUT
    n_seed = {"EASY": 0, "MEDIUM": 1, "HARD": 3, "ADVERSARIAL": 5}[k.label]
    for j, vic in enumerate(victims):
        stage = "SEED_TRAFFIC" if j < n_seed else ("RAMP" if j < len(victims) - 1 else "CASH_OUT")
        n_txn = 1 if stage == "SEED_TRAFFIC" else int(rng.integers(1, 3))
        for _ in range(n_txn):
            t = t0 + int(rng.integers(0, max(1, k.spread_days) * DAY))
            if stage == "SEED_TRAFFIC":
                amt = float(round(median_ticket * rng.uniform(0.3, 0.9), 2))
            else:
                amt = _drain_amount(vic, k, rng)
            res.events.append(_base_event(
                vic, k, rng, attack_type="MERCHANT_FRAUD", attack_id=attack_id,
                stage=stage, ts=t, amount=amt, merchant_id=mer_id, category=cat,
                device_id=str(rng.choice(vic.known_devices)) if vic.known_devices
                else f"DEV_ATK_{attack_id}",
                city=vic.home_city, lat=vic.home_lat, lon=vic.home_lon,
                ttype="PURCHASE", channel="ECOM", seq=seq,
                payment_link_referred=1 if rng.random() < 0.5 else 0,
                campaign_id=attack_id))
            seq += 1
    return res


# ==========================================================================
# 5. PHISHING / PAYMENT LINK
# ==========================================================================
def gen_phishing_payment_link(v: VictimContext, k: Knobs, rng, merchants, cashout_ids,
                              attack_id: str) -> AttackResult:
    """Customer authorises a payment they were deceived into making.

    Every authentication control passes — own device, own city, own credentials.
    The only evidence is contextual: link-referred initiation, an unfamiliar
    counterparty, and a compressed session.
    """
    res = AttackResult()
    # Victim uses their own device and location: this is the whole point.
    device = str(rng.choice(v.known_devices)) if v.known_devices else f"DEV_ATK_{attack_id}"
    if rng.random() < k.p_new_device * 0.3:
        device = f"DEV_ATK_{attack_id}"
    city, lat, lon = (v.home_city, v.home_lat, v.home_lon)

    mer_id = f"MER_PHISH_{attack_id}"
    cat = str(rng.choice(["ECOMMERCE", "UTILITIES", "FINANCIAL_SERVICES", "TRAVEL"]))
    spec = C.CATEGORY_BY_NAME[cat]
    res.extra_merchants.append({
        "merchant_id": mer_id, "merchant_name": "Secure Payments Portal",
        "category": cat, "merchant_size": "SMALL",
        "merchant_age_days": int(rng.integers(*{"EASY": (0, 4), "MEDIUM": (3, 30),
                                                "HARD": (25, 160),
                                                "ADVERSARIAL": (150, 500)}[k.label])),
        "city": city, "lat": lat, "lon": lon,
        "median_ticket": round(float(np.exp(spec.base_ticket)), 2),
        "ticket_sigma": round(float(spec.ticket_sigma), 4),
        "daily_volume": round(float(rng.uniform(5, 200)), 1),
        "intrinsic_risk": round(float(np.clip(spec.intrinsic_risk * 1.15, 0, 1)), 4),
        "cnp_share": 1.0,
        "chargeback_rate": round(float(rng.uniform(0.01, 0.22)), 5),
        "is_fraud_merchant": 1, "onboarded_via": "SELF_SERVE",
    })

    t = _pick_hour_ts(v, k, rng, v.t0 - int(rng.integers(0, 2)) * DAY)
    seq = 0
    n = int(rng.integers(1, max(2, k.n_drain_hi - 1)))
    for j in range(n):
        amt = _drain_amount(v, k, rng)
        stage = "AUTHORISE" if j == 0 else "SETTLE"
        res.events.append(_base_event(
            v, k, rng, attack_type="PHISHING_PAYMENT_LINK", attack_id=attack_id,
            stage=stage, ts=t, amount=amt, merchant_id=mer_id, category=cat,
            device_id=device, city=city, lat=lat, lon=lon,
            ttype="PURCHASE" if rng.random() < 0.6 else "TRANSFER",
            channel="ECOM", beneficiary=f"BEN_PHISH_{attack_id}" if rng.random() < 0.4 else "",
            is_new_ben=1 if j == 0 else 0, seq=seq,
            payment_link_referred=1,
            session_duration_s=float(rng.uniform(9, 55)),   # compressed session
            ip_asn_type="MOBILE"))
        seq += 1
        t += int(rng.integers(k.gap_lo_s, k.gap_hi_s + 1))
    return res


# ==========================================================================
# 6. SOCIAL ENGINEERING / VOICE CLONE
# ==========================================================================
def gen_social_engineering(v: VictimContext, k: Knobs, rng, merchants, cashout_ids,
                           attack_id: str) -> AttackResult:
    """Victim is coached through the payment on a live call.

    Nothing is compromised: own device, own city, valid credentials. The
    distinguishing context is `inbound_call_active`, a payee created during the
    call, elevated biometric deviation from stress, and an amount near the
    account's practical ceiling.
    """
    res = AttackResult()
    device = str(rng.choice(v.known_devices)) if v.known_devices else f"DEV_ATK_{attack_id}"
    city, lat, lon = v.home_city, v.home_lat, v.home_lon

    if v.known_beneficiaries and rng.random() < k.p_reuse_existing_payee:
        payee, new_ben = str(rng.choice(v.known_beneficiaries)), 0
    else:
        payee, new_ben = f"BEN_MULE_{attack_id}", 1

    t = _pick_hour_ts(v, k, rng, v.t0 - int(rng.integers(0, 2)) * DAY)
    seq = 0
    lo, hi = k.biometric_dev

    def step(stage, amount, **kw):
        nonlocal t, seq
        mid, cat = _merchant_for_cashout(v, k, merchants, rng, cashout_ids)
        res.events.append(_base_event(
            v, k, rng, attack_type="SOCIAL_ENGINEERING", attack_id=attack_id,
            stage=stage, ts=t, amount=amount, merchant_id=mid, category=cat,
            device_id=device, city=city, lat=lat, lon=lon, ttype="TRANSFER",
            beneficiary=payee, is_new_ben=new_ben if seq == 0 else 0, seq=seq,
            inbound_call_active=1,
            typing_cadence_dev=float(rng.uniform(lo, hi) * 1.35),
            session_duration_s=float(rng.uniform(180, 1500)),   # long call
            ip_asn_type="MOBILE", **kw))
        seq += 1
        t += int(rng.integers(max(60, k.gap_lo_s // 6), max(300, k.gap_hi_s // 4)))

    # PRETEXT: a small "verification" transfer the caller talks the victim into
    if rng.random() < k.p_probe:
        step("PRETEXT", float(round(v.median_amount * rng.uniform(0.2, 0.8), 2)))
    # TRANSFER: the main event, pushed toward the account ceiling
    main = _drain_amount(v, k, rng)
    if k.label in ("EASY", "MEDIUM"):
        main = max(main, v.credit_limit * float(rng.uniform(0.35, 0.85)))
    step("TRANSFER", float(round(min(main, v.credit_limit * 0.97), 2)))
    # REINFORCE: the story escalates, further transfers follow
    for _ in range(int(rng.integers(0, max(1, k.n_drain_hi - 2)))):
        step("REINFORCE", _drain_amount(v, k, rng))
    return res


# ==========================================================================
# 7. MULTI-STAGE COMPOSITE
# ==========================================================================
def gen_multi_stage(v: VictimContext, k: Knobs, rng, merchants, cashout_ids,
                    attack_id: str) -> AttackResult:
    """Recon -> foothold -> mule prep -> test -> fan-out -> consolidate.

    Every stage is individually defensible. Only the ordering is incriminating,
    and the fan-out converges on mules that share a beneficiary in-degree
    signature. A per-row classifier is structurally unable to see this, which
    is the point of including it.
    """
    res = AttackResult()
    device_known = str(rng.choice(v.known_devices)) if v.known_devices else f"DEV_ATK_{attack_id}"
    device_new = f"DEV_ATK_{attack_id}"
    t = v.t0 - int(rng.integers(k.spread_days, k.spread_days + 4)) * DAY
    seq = 0
    n_mules = int(rng.integers(2, 5))
    mules = [f"BEN_MULE_{attack_id}_{i}" for i in range(n_mules)]

    def step(stage, amount, device, city_tuple, ttype="TRANSFER", ben="", new_ben=0, **kw):
        nonlocal t, seq
        city, lat, lon = city_tuple
        mid, cat = _merchant_for_cashout(v, k, merchants, rng, cashout_ids)
        res.events.append(_base_event(
            v, k, rng, attack_type="MULTI_STAGE", attack_id=attack_id, stage=stage,
            ts=t, amount=amount, merchant_id=mid, category=cat, device_id=device,
            city=city, lat=lat, lon=lon, ttype=ttype, beneficiary=ben,
            is_new_ben=new_ben, seq=seq, campaign_id=attack_id, **kw))
        seq += 1

    home = (v.home_city, v.home_lat, v.home_lon)
    away = _pick_city(v, k, rng)

    # RECON — a trivial purchase on a known device, deliberately unremarkable
    step("RECON", float(round(v.median_amount * rng.uniform(0.3, 1.1), 2)),
         device_known, home, ttype="PURCHASE")
    t += int(rng.integers(k.gap_lo_s, k.gap_hi_s + 1))

    # FOOTHOLD — device or credential change, still no value movement
    step("FOOTHOLD", float(round(v.median_amount * rng.uniform(0.3, 1.2), 2)),
         device_new if rng.random() < k.p_new_device else device_known, away,
         ttype="PURCHASE",
         password_changed_recently=1 if rng.random() < k.p_credential_change else 0,
         profile_changed_recently=1)
    t += DAY + int(rng.integers(0, DAY))

    # MULE_PREP — payees created, nothing sent yet
    for i, mu in enumerate(mules):
        step("MULE_PREP", float(round(v.median_amount * rng.uniform(0.05, 0.3), 2)),
             device_known, home, ben=mu, new_ben=1)
        t += int(rng.integers(600, 9_000))
    t += int(rng.integers(0, k.spread_days) * DAY)

    # TEST — one small transfer to confirm the rail works
    step("TEST", float(round(v.median_amount * rng.uniform(0.2, 0.7), 2)),
         device_known, home, ben=mules[0])
    t += int(rng.integers(k.gap_lo_s, k.gap_hi_s + 1))

    # FAN_OUT — value split across the mules
    total = min(v.credit_limit * float(rng.uniform(0.4, 0.9)),
                v.p95_amount * n_mules * (1.2 if k.stay_under_p95 else 6.0))
    for i in range(int(rng.integers(k.n_drain_lo, k.n_drain_hi + 1))):
        mu = mules[i % n_mules]
        amt = total / max(1, k.n_drain_hi) * float(rng.uniform(0.7, 1.3))
        if k.stay_under_p95:
            amt = min(amt, v.p95_amount * float(rng.uniform(0.6, 1.0)))
        step("FAN_OUT", float(round(max(20.0, amt), 2)), device_known, home, ben=mu)
        t += int(rng.integers(k.gap_lo_s, k.gap_hi_s + 1))

    # CONSOLIDATE — mules converge on one collector
    collector = f"BEN_COLLECT_{attack_id}"
    step("CONSOLIDATE", float(round(min(total * 0.4, v.credit_limit * 0.9), 2)),
         device_known, home, ben=collector, new_ben=1)
    return res


# ==========================================================================
GENERATORS: Dict[str, Callable] = {
    "ACCOUNT_TAKEOVER": gen_account_takeover,
    "TRANSACTION_MANIPULATION": gen_transaction_manipulation,
    "SYNTHETIC_IDENTITY": gen_synthetic_identity,
    "MERCHANT_FRAUD": gen_merchant_fraud,
    "PHISHING_PAYMENT_LINK": gen_phishing_payment_link,
    "SOCIAL_ENGINEERING": gen_social_engineering,
    "MULTI_STAGE": gen_multi_stage,
}

# Attacks that need several victims per scenario (acceptance-side fraud).
MULTI_VICTIM = {"MERCHANT_FRAUD"}
