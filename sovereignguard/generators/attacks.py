"""
Red Team attack synthesis (Phases 8-11).

CONTRACT
--------
An attack generator receives a victim (or creates a synthetic entity), a
difficulty knob, and an RNG, and returns a list of *event* dicts using exactly
the same columns as legitimate traffic. It never writes features and never
touches the label columns beyond stamping fraud_label / attack_type /
attack_stage / difficulty / attack_id.

Events are injected into the victim's existing timeline and features are then
recomputed over the merged stream. That is what makes an attack row's velocity,
device-novelty and beneficiary-age features genuinely earned rather than
asserted — and it is why a HARD attack is actually hard.

DIFFICULTY
----------
`Knobs` translates a difficulty level into concrete evasion behaviour:

  EASY         unfamiliar device + unfamiliar geography + huge amount + burst
  MEDIUM       controls one or two obvious signals, trips the rest
  HARD         familiar device / home city / in-range amounts / patient pacing
  ADVERSARIAL  maximal stealth; the adaptive engine overrides these knobs with
               parameters measured to defeat the deployed detector

Safety: every generator produces rows in a synthetic dataset. Nothing here
sends a message, contacts a person, or touches a payment rail. The taxonomy
deliberately describes attacks at the level of their effect on a transaction
stream rather than as operational instructions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .. import config as C
from ..schema import TRANSACTION_COLUMNS
from .transactions import DAY, SIM_EPOCH, _empty_event

# --------------------------------------------------------------------------
# Difficulty knobs
# --------------------------------------------------------------------------
@dataclass
class Knobs:
    """Evasion parameters. Higher stealth => harder for the detector."""
    # amount discipline
    amount_mult_lo: float          # multiple of victim's median for the drain
    amount_mult_hi: float
    stay_under_p95: bool           # never exceed the victim's own 95th pct
    # device / geography
    p_new_device: float
    p_new_city: float
    p_high_risk_city: float
    p_hosting_ip: float
    # pacing
    gap_lo_s: int                  # inter-event gap
    gap_hi_s: int
    spread_days: int               # how many days the sequence spans
    # sequence shape
    n_drain_lo: int
    n_drain_hi: int
    p_probe: float                 # include a small test transaction
    p_reuse_existing_payee: float  # avoid the new-beneficiary signal
    p_credential_change: float     # leave a password/profile-change trace
    biometric_dev: Tuple[float, float]
    p_round_amount: float
    label: str = "MEDIUM"


KNOBS: Dict[str, Knobs] = {
    # biometric_dev note: legitimate traffic draws typing_cadence_dev from
    # Beta(2,12) (mean ~0.14, tail to ~0.5). The attack ranges below deliberately
    # OVERLAP that, because an earlier version used (0.45, 0.85) for EASY, which
    # put attack values almost entirely outside the honest range and turned the
    # biometric into a near-perfect oracle (measured AUC 0.9997 on EASY alone).
    # Stressed or unfamiliar genuine users do produce high deviation too.
    "EASY": Knobs(
        amount_mult_lo=12.0, amount_mult_hi=45.0, stay_under_p95=False,
        p_new_device=0.95, p_new_city=0.85, p_high_risk_city=0.55, p_hosting_ip=0.60,
        gap_lo_s=25, gap_hi_s=240, spread_days=1,
        n_drain_lo=3, n_drain_hi=7, p_probe=0.30, p_reuse_existing_payee=0.02,
        p_credential_change=0.90, biometric_dev=(0.10, 0.60), p_round_amount=0.70,
        label="EASY"),
    "MEDIUM": Knobs(
        amount_mult_lo=4.0, amount_mult_hi=14.0, stay_under_p95=False,
        p_new_device=0.60, p_new_city=0.45, p_high_risk_city=0.20, p_hosting_ip=0.22,
        gap_lo_s=600, gap_hi_s=7_200, spread_days=2,
        n_drain_lo=2, n_drain_hi=5, p_probe=0.55, p_reuse_existing_payee=0.18,
        p_credential_change=0.55, biometric_dev=(0.06, 0.42), p_round_amount=0.45,
        label="MEDIUM"),
    "HARD": Knobs(
        amount_mult_lo=1.4, amount_mult_hi=4.5, stay_under_p95=True,
        p_new_device=0.18, p_new_city=0.12, p_high_risk_city=0.04, p_hosting_ip=0.05,
        gap_lo_s=5_400, gap_hi_s=64_800, spread_days=6,
        n_drain_lo=3, n_drain_hi=9, p_probe=0.75, p_reuse_existing_payee=0.55,
        p_credential_change=0.20, biometric_dev=(0.03, 0.26), p_round_amount=0.12,
        label="HARD"),
    "ADVERSARIAL": Knobs(
        amount_mult_lo=0.9, amount_mult_hi=2.4, stay_under_p95=True,
        p_new_device=0.06, p_new_city=0.04, p_high_risk_city=0.01, p_hosting_ip=0.01,
        gap_lo_s=18_000, gap_hi_s=150_000, spread_days=12,
        n_drain_lo=4, n_drain_hi=12, p_probe=0.85, p_reuse_existing_payee=0.80,
        p_credential_change=0.06, biometric_dev=(0.02, 0.16), p_round_amount=0.04,
        label="ADVERSARIAL"),
}


# --------------------------------------------------------------------------
@dataclass
class VictimContext:
    """Everything a generator needs to know about the account it is abusing.

    Built from the *legitimate* history so that an attack can be made to look
    like that specific customer rather than like a generic fraud template.
    """
    customer_id: str
    persona: str
    median_amount: float
    p95_amount: float
    max_amount: float
    credit_limit: float
    home_city: str
    home_lat: float
    home_lon: float
    known_devices: List[str]
    known_merchants: List[str]
    known_categories: List[str]
    known_beneficiaries: List[str]
    preferred_method: str
    typical_hours: List[int]
    last_ts: int
    n_txns: int
    first_ts: int = 0
    # Anchor for THIS scenario. Sampled per attack across the whole simulation
    # window so fraud is spread over time rather than piling up at the end of
    # the stream (which would starve a time-ordered training split of positives).
    anchor_ts: int = 0

    def anchored(self, ts: int) -> "VictimContext":
        import dataclasses
        return dataclasses.replace(self, anchor_ts=int(ts))

    @property
    def t0(self) -> int:
        """Start time for a scenario: the sampled anchor, else last activity."""
        return int(self.anchor_ts or self.last_ts)


def build_victim_contexts(tx: pd.DataFrame, customers: pd.DataFrame) -> Dict[str, VictimContext]:
    """One pass over legitimate history to build per-customer attack context."""
    ctx: Dict[str, VictimContext] = {}
    cust_rows = {c.customer_id: c for c in customers.itertuples(index=False)}
    if len(tx) == 0:
        return ctx

    g = tx.groupby("customer_id", sort=False)
    for cid, sub in g:
        c = cust_rows.get(cid)
        if c is None:
            continue
        amts = sub["amount"].to_numpy()
        hours = ((sub["timestamp"].to_numpy() // 3600) % 24).astype(int)
        hist = np.bincount(hours, minlength=24)
        top_hours = [int(h) for h in np.argsort(-hist)[:6] if hist[h] > 0]
        bens = [b for b in sub["beneficiary_id"].unique().tolist() if b]
        ctx[cid] = VictimContext(
            customer_id=cid,
            persona=c.persona,
            median_amount=float(np.median(amts)),
            p95_amount=float(np.percentile(amts, 95)),
            max_amount=float(amts.max()),
            credit_limit=float(c.credit_limit),
            home_city=c.home_city,
            home_lat=float(c.home_lat),
            home_lon=float(c.home_lon),
            known_devices=sub["device_id"].unique().tolist(),
            known_merchants=sub["merchant_id"].unique().tolist(),
            known_categories=sub["mcc_category"].unique().tolist(),
            known_beneficiaries=bens,
            preferred_method=c.preferred_method,
            typical_hours=top_hours or [12],
            last_ts=int(sub["timestamp"].max()),
            n_txns=len(sub),
            first_ts=int(sub["timestamp"].min()),
        )
    return ctx


# --------------------------------------------------------------------------
# helpers shared by generators
# --------------------------------------------------------------------------
def _pick_city(v: VictimContext, k: Knobs, rng: np.random.Generator) -> Tuple[str, float, float]:
    u = rng.random()
    if u < k.p_high_risk_city:
        city = str(rng.choice(C.HIGH_RISK_LOCATIONS))
    elif u < k.p_new_city:
        choices = [c for c in C.CITY_NAMES if c != v.home_city]
        city = str(rng.choice(choices))
    else:
        return v.home_city, v.home_lat, v.home_lon
    lat, lon, _ = C.CITIES[city]
    return city, lat, lon


def _pick_device(v: VictimContext, k: Knobs, rng: np.random.Generator, attack_id: str) -> str:
    if rng.random() < k.p_new_device or not v.known_devices:
        return f"DEV_ATK_{attack_id}"
    return str(rng.choice(v.known_devices))


def _pick_hour_ts(v: VictimContext, k: Knobs, rng: np.random.Generator, base_ts: int) -> int:
    """Anchor to one of the victim's habitual hours when being stealthy."""
    if k.label in ("HARD", "ADVERSARIAL") and rng.random() < 0.8:
        hour = int(rng.choice(v.typical_hours))
    else:
        hour = int(rng.integers(0, 24)) if rng.random() < 0.5 else int(rng.choice([1, 2, 3, 4]))
    day_start = (base_ts // DAY) * DAY
    return int(day_start + hour * 3600 + rng.integers(0, 3600))


def _drain_amount(v: VictimContext, k: Knobs, rng: np.random.Generator) -> float:
    mult = float(rng.uniform(k.amount_mult_lo, k.amount_mult_hi))
    amt = v.median_amount * mult
    if k.stay_under_p95:
        amt = min(amt, v.p95_amount * float(rng.uniform(0.72, 1.02)))
    amt = min(amt, v.credit_limit * 0.97)
    if rng.random() < k.p_round_amount:
        for base in (50_000, 25_000, 10_000, 5_000, 1_000, 500):
            if amt >= base:
                amt = float(base * max(1, round(amt / base)))
                break
    return float(max(20.0, round(amt, 2)))


def _asn(k: Knobs, rng: np.random.Generator) -> str:
    u = rng.random()
    if u < k.p_hosting_ip:
        return "HOSTING"
    if u < k.p_hosting_ip + 0.18:
        return "VPN"
    return "MOBILE" if rng.random() < 0.6 else "RESIDENTIAL"


def _base_event(v: VictimContext, k: Knobs, rng: np.random.Generator, *,
                attack_type: str, attack_id: str, stage: str, ts: int,
                amount: float, merchant_id: str, category: str,
                device_id: str, city: str, lat: float, lon: float,
                ttype: str = "TRANSFER", method: Optional[str] = None,
                channel: Optional[str] = None, beneficiary: str = "",
                is_new_ben: int = 0, seq: int = 0,
                campaign_id: str = "", **overrides) -> Dict:
    ev = _empty_event()
    lo, hi = k.biometric_dev
    method = method or (v.preferred_method if rng.random() < 0.65
                        else str(rng.choice(C.PAYMENT_METHODS)))
    if channel is None:
        channel = "APP" if method in ("UPI", "WALLET") else "ECOM"
    ev.update({
        "transaction_id": f"TXN_ATK_{attack_id}_{seq:02d}",
        "customer_id": v.customer_id,
        "merchant_id": merchant_id,
        "timestamp": int(ts),
        "amount": float(amount),
        "payment_method": method,
        "channel": channel,
        "transaction_type": ttype,
        "device_id": device_id,
        "city": city, "lat": float(lat), "lon": float(lon),
        "beneficiary_id": beneficiary,
        "auth_result": "APPROVED",
        "mcc_category": category,
        "session_id": f"SES_ATK_{attack_id}_{seq:02d}",
        "typing_cadence_dev": float(rng.uniform(lo, hi)),
        "ip_asn_type": _asn(k, rng),
        "is_new_beneficiary": int(is_new_ben),
        "session_duration_s": float(rng.uniform(15, 260)),
        "fraud_label": 1,
        "attack_type": attack_type,
        "attack_id": attack_id,
        "attack_stage": stage,
        "difficulty": k.label,
        "generator": "redteam",
        "campaign_id": campaign_id or attack_id,
    })
    ev.update(overrides)
    return ev


def _merchant_for_cashout(v: VictimContext, k: Knobs, merchants: pd.DataFrame,
                          rng: np.random.Generator, cashout_ids: np.ndarray) -> Tuple[str, str]:
    """Where the value goes. Stealthy attacks route through merchants the
    victim already uses; blatant ones use obvious cash-out categories."""
    if k.label in ("HARD", "ADVERSARIAL") and v.known_merchants and rng.random() < 0.6:
        mid = str(rng.choice(v.known_merchants))
        cat = str(merchants.loc[merchants.merchant_id == mid, "category"].iloc[0]) \
            if (merchants.merchant_id == mid).any() else "P2P_TRANSFER"
        return mid, cat
    mid = str(rng.choice(cashout_ids))
    cat = str(merchants.loc[merchants.merchant_id == mid, "category"].iloc[0])
    return mid, cat
