"""
Legitimate transaction simulator.

Design notes that matter for the science of this project
-------------------------------------------------------
1. Amount is a *blend* of the customer's own price point and the merchant
   category's ticket size. A student buying groceries and a business owner
   buying groceries produce different amounts at the same merchant; the same
   customer at a cinema and at a travel agent produces different amounts.
   This is what makes `amount_ratio_customer_median` a real signal rather than
   a trivially separable one.

2. Legitimate customers DO the things fraudsters do — they change devices,
   travel, add payees, change passwords, and occasionally make a purchase 12x
   their normal amount. Rates come from config.LEGIT_EVENT_RATES. Without this
   the "risk flags" become perfect oracles and every metric is meaningless.

3. Merchant choice is habitual: each customer has a favourites basket and only
   occasionally strays, at a persona-specific rate.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .. import config as C
from ..rng import substream
from ..schema import EVENT_COLUMNS, LABEL_COLUMNS, TRANSACTION_COLUMNS

DAY = 86_400
SIM_EPOCH = 1_735_689_600  # 2025-01-01T00:00:00Z — fixed so runs are comparable

# Hour-of-day base profile for retail payments (sums to 1 after normalisation).
HOUR_BASE = np.array([
    0.006, 0.004, 0.003, 0.003, 0.004, 0.009,   # 00-05
    0.018, 0.031, 0.045, 0.055, 0.062, 0.066,   # 06-11
    0.070, 0.062, 0.052, 0.050, 0.055, 0.065,   # 12-17
    0.075, 0.080, 0.072, 0.055, 0.036, 0.022,   # 18-23
])
HOUR_BASE = HOUR_BASE / HOUR_BASE.sum()

NIGHT_HOURS = np.array([0, 1, 2, 3, 4, 5])

DOW_FACTOR = np.array([0.95, 0.96, 0.99, 1.02, 1.14, 1.22, 1.05])  # Mon..Sun

CHANNEL_BY_METHOD = {
    "UPI": {"APP": 0.78, "ECOM": 0.16, "POS": 0.06},
    "CARD": {"POS": 0.44, "ECOM": 0.46, "APP": 0.10},
    "WALLET": {"APP": 0.66, "ECOM": 0.30, "POS": 0.04},
    "NETBANKING": {"ECOM": 0.62, "APP": 0.34, "API": 0.04},
}

# Pre-baked cumulative tables so the inner loop never calls rng.choice(p=...),
# which dominates runtime at scale. Draw one uniform, searchsorted, done.
_CHANNEL_TABLE = {
    m: (list(d.keys()), np.cumsum(np.array(list(d.values())) / sum(d.values())))
    for m, d in CHANNEL_BY_METHOD.items()
}
_METHOD_LIST = C.PAYMENT_METHODS


def _cum(weights) -> np.ndarray:
    w = np.asarray(weights, dtype=float)
    return np.cumsum(w / w.sum())


def _pick(items, cumw: np.ndarray, u: float):
    return items[int(np.searchsorted(cumw, u, side="right"))]


def _empty_event() -> Dict:
    return {
        "transaction_id": "", "customer_id": "", "merchant_id": "", "timestamp": 0,
        "amount": 0.0, "payment_method": "UPI", "channel": "APP",
        "transaction_type": "PURCHASE", "device_id": "", "city": "", "lat": 0.0, "lon": 0.0,
        "beneficiary_id": "", "auth_result": "APPROVED", "mcc_category": "FOOD",
        "session_id": "", "password_changed_recently": 0, "profile_changed_recently": 0,
        "failed_logins_1h": 0, "session_duration_s": 90.0, "typing_cadence_dev": 0.05,
        "ip_asn_type": "MOBILE", "is_new_beneficiary": 0, "sim_swapped_recently": 0,
        "inbound_call_active": 0, "payment_link_referred": 0,
        "fraud_label": 0, "attack_type": "NONE", "attack_id": "", "attack_stage": "",
        "difficulty": "", "generator": "legit", "campaign_id": "",
    }


def _hour_profile(persona: C.Persona, rng: np.random.Generator) -> np.ndarray:
    """Per-customer hour distribution: base curve, night-shifted by persona,
    plus an individual quirk so 'unusual hour for this customer' is meaningful."""
    p = HOUR_BASE.copy()
    # Redistribute mass into the night according to persona night activity.
    target_night = persona.night_activity * rng.uniform(0.7, 1.3)
    cur_night = p[NIGHT_HOURS].sum()
    if target_night > cur_night:
        add = target_night - cur_night
        p[NIGHT_HOURS] += add / len(NIGHT_HOURS)
        day_mask = np.ones(24, dtype=bool)
        day_mask[NIGHT_HOURS] = False
        p[day_mask] -= add / day_mask.sum()
    # Individual quirk: sharpen two random hours (the customer's habit slots).
    quirks = rng.choice(24, size=2, replace=False)
    p[quirks] *= rng.uniform(1.6, 3.0)
    p = np.clip(p, 1e-4, None)
    return p / p.sum()


def _pick_favourites(cust, merchants: pd.DataFrame, cat_index: Dict[str, np.ndarray],
                     rng: np.random.Generator) -> Tuple[np.ndarray, np.ndarray]:
    """Habitual merchant basket, weighted by persona category affinity."""
    persona = C.PERSONA_BY_NAME[cust.persona]
    n_fav = int(np.clip(rng.gamma(4.0, 3.2), 5, 40))
    cats = list(persona.category_affinity.keys())
    cat_p = np.array([persona.category_affinity[c] for c in cats], dtype=float)
    cat_p /= cat_p.sum()

    picks: List[int] = []
    draws = rng.choice(len(cats), size=n_fav, p=cat_p)
    for d in draws:
        pool = cat_index.get(cats[d])
        if pool is None or len(pool) == 0:
            continue
        picks.append(int(rng.choice(pool)))
    if not picks:
        picks = [int(rng.integers(0, len(merchants)))]
    fav = np.unique(np.array(picks, dtype=int))
    # Habit strength: Zipf-like so a few merchants dominate.
    w = 1.0 / (np.arange(1, len(fav) + 1) ** rng.uniform(0.6, 1.3))
    rng.shuffle(w)
    w = w / w.sum()
    return fav, w


def generate_legitimate_transactions(
    customers: pd.DataFrame,
    merchants: pd.DataFrame,
    devices: pd.DataFrame,
    n_days: int,
    seed: int,
) -> pd.DataFrame:
    rng = substream(seed, "legit_txns")

    m_ids = merchants["merchant_id"].to_numpy()
    m_cat = merchants["category"].to_numpy()
    m_city = merchants["city"].to_numpy()
    m_lat = merchants["lat"].to_numpy()
    m_lon = merchants["lon"].to_numpy()
    m_med = merchants["median_ticket"].to_numpy()
    m_sig = merchants["ticket_sigma"].to_numpy()
    m_cnp = merchants["cnp_share"].to_numpy()

    cat_index = {c: np.where(m_cat == c)[0] for c in C.CATEGORY_NAMES}
    cat_city_index = {c: np.where(m_city == c)[0] for c in C.CITY_NAMES}
    dev_by_cust: Dict[str, List[str]] = {}
    for d in devices.itertuples(index=False):
        dev_by_cust.setdefault(d.owner_customer_id, []).append(d.device_id)

    city_names = C.CITY_NAMES
    city_lat = np.array([C.CITIES[n][0] for n in city_names])
    city_lon = np.array([C.CITIES[n][1] for n in city_names])

    rows: List[Dict] = []
    txn_counter = 0
    horizon = n_days * DAY

    for cust in customers.itertuples(index=False):
        persona = C.PERSONA_BY_NAME[cust.persona]
        hour_p = _hour_profile(persona, rng)
        fav, fav_w = _pick_favourites(cust, merchants, cat_index, rng)
        cust_devices = dev_by_cust.get(cust.customer_id, [cust.primary_device_id])
        # Device usage share: primary dominates.
        dev_w = np.array([0.86] + [0.14 / max(1, len(cust_devices) - 1)] * (len(cust_devices) - 1)) \
            if len(cust_devices) > 1 else np.array([1.0])
        dev_w = dev_w / dev_w.sum()
        hour_cum = _cum(hour_p)
        fav_cum = _cum(fav_w)
        log_cust_med = np.log(max(cust.median_amount, 1.0))

        # ---- travel windows -------------------------------------------------
        travel: List[Tuple[int, int, int]] = []  # (start_day, end_day, city_idx)
        n_trips = rng.poisson(persona.travel_propensity * (n_days / 45.0))
        for _ in range(int(n_trips)):
            start = int(rng.integers(0, max(1, n_days - 2)))
            length = int(np.clip(rng.gamma(2.0, 2.0), 1, 12))
            ci = int(rng.integers(0, len(city_names)))
            if city_names[ci] != cust.home_city:
                travel.append((start, min(n_days, start + length), ci))

        # ---- legitimate life events ----------------------------------------
        yr = n_days / 365.0
        pw_days = set(rng.integers(0, n_days, size=rng.poisson(
            C.LEGIT_EVENT_RATES["password_change_per_year"] * yr)).tolist())
        pf_days = set(rng.integers(0, n_days, size=rng.poisson(
            C.LEGIT_EVENT_RATES["profile_change_per_year"] * yr)).tolist())
        fl_days = set(rng.integers(0, n_days, size=rng.poisson(
            C.LEGIT_EVENT_RATES["failed_login_burst_per_year"] * yr)).tolist())
        # A genuine new device appearing mid-window (phone upgrade / reinstall).
        new_dev_day = None
        if rng.random() < persona.device_change_rate:
            new_dev_day = int(rng.integers(int(n_days * 0.15), n_days))
            cust_devices = cust_devices + [f"{cust.primary_device_id}_new"]
            dev_w = np.append(dev_w * 0.999, 0.001)
            dev_w /= dev_w.sum()
        dev_pool = cust_devices[:len(dev_w)]
        dev_cum = _cum(dev_w)

        # Beneficiary book: some pre-existing, some added during the window.
        n_ben0 = int(np.clip(rng.gamma(2.2, 2.0), 1, 25))
        beneficiaries = [f"BEN_{cust.customer_id}_{k}" for k in range(n_ben0)]
        new_ben_days = sorted(rng.integers(0, n_days, size=rng.poisson(
            C.LEGIT_EVENT_RATES["new_beneficiary_per_year"] * yr)).tolist())
        new_ben_ptr = 0
        ben_created_at: Dict[str, int] = {b: -DAY * 400 for b in beneficiaries}

        # ---- day loop -------------------------------------------------------
        for day in range(n_days):
            dow = (day + 3) % 7  # arbitrary but fixed calendar alignment
            lam = cust.txns_per_day * DOW_FACTOR[dow]
            n_txn = int(rng.poisson(max(0.02, lam)))
            if n_txn == 0:
                continue

            # add any beneficiaries scheduled for today
            while new_ben_ptr < len(new_ben_days) and new_ben_days[new_ben_ptr] <= day:
                nb = f"BEN_{cust.customer_id}_n{new_ben_ptr}"
                beneficiaries.append(nb)
                ben_created_at[nb] = SIM_EPOCH + day * DAY + int(rng.integers(0, DAY))
                new_ben_ptr += 1

            # where is the customer today?
            cur_city, cur_lat, cur_lon = cust.home_city, cust.home_lat, cust.home_lon
            for (s, e, ci) in travel:
                if s <= day < e:
                    cur_city, cur_lat, cur_lon = city_names[ci], city_lat[ci], city_lon[ci]
                    break

            hours = rng.choice(24, size=n_txn, p=hour_p)
            mins = rng.integers(0, 3600, size=n_txn)

            pw_recent = int(any(0 <= day - d <= 3 for d in pw_days))
            pf_recent = int(any(0 <= day - d <= 3 for d in pf_days))
            failed_logins = int(rng.integers(1, 4)) if day in fl_days else 0

            # Batched draws: one call each instead of ~14 per transaction.
            U = rng.random((n_txn, 14))
            Z = rng.normal(0.0, 1.0, size=n_txn)
            SESS = np.clip(rng.gamma(3.0, 45.0, size=n_txn), 4, 3600)
            TYPD = np.clip(rng.beta(2.0, 12.0, size=n_txn), 0, 1)
            hours = np.searchsorted(hour_cum, U[:, 12], side="right")
            mins = (U[:, 13] * 3600).astype(int)

            for k in range(n_txn):
                u = U[k]
                # --- merchant choice: habit vs. exploration
                if u[0] < persona.new_merchant_rate:
                    mi = int(u[1] * len(m_ids))
                else:
                    mi = int(fav[int(np.searchsorted(fav_cum, u[1], side="right"))])

                cat = m_cat[mi]
                # --- amount: blend customer price point and merchant ticket
                sig = float(np.sqrt(cust.amount_sigma ** 2 * 0.6 + m_sig[mi] ** 2 * 0.4))
                mu = 0.62 * log_cust_med + 0.38 * np.log(max(m_med[mi], 1.0))
                amount = float(np.exp(mu + sig * Z[k]))
                # occasional genuine large purchase
                if u[2] < C.LEGIT_EVENT_RATES["large_purchase_share"]:
                    amount *= 5.0 + 13.0 * u[3]
                amount = float(np.clip(round(amount, 2), 5.0, 6_000_000.0))

                # --- method / channel / type
                method = cust.preferred_method if u[4] < 0.72 else \
                    _METHOD_LIST[int(u[5] * len(_METHOD_LIST))]
                ch_items, ch_cum = _CHANNEL_TABLE[method]
                channel = _pick(ch_items, ch_cum, u[6])
                if cat == "P2P_TRANSFER" or (u[7] < persona.transfer_share * 0.35):
                    ttype = "TRANSFER"
                elif method == "WALLET" and u[8] < 0.12:
                    ttype = "TOPUP"
                elif u[8] > 0.988:
                    ttype = "WITHDRAWAL"
                else:
                    ttype = "PURCHASE"

                # --- device
                if new_dev_day is not None and day >= new_dev_day and u[9] < 0.55:
                    device_id = dev_pool[-1]
                else:
                    device_id = _pick(dev_pool, dev_cum, u[9])

                # --- location: in-person follows the customer, online can be anywhere
                tx_city, tx_lat, tx_lon = cur_city, cur_lat, cur_lon
                if channel == "POS":
                    near = cat_city_index.get(cur_city)
                    if near is not None and len(near) and u[10] < 0.80:
                        mi = int(near[int(u[11] * len(near))])
                        cat = m_cat[mi]

                # --- beneficiary
                ben = ""
                is_new_ben = 0
                ts = SIM_EPOCH + day * DAY + int(hours[k]) * 3600 + int(mins[k]) % 3600
                if ttype == "TRANSFER":
                    ben = beneficiaries[int(u[3] * len(beneficiaries))]
                    age = ts - ben_created_at.get(ben, ts - DAY * 400)
                    is_new_ben = int(age < DAY * 2)

                # --- auth result
                r = u[2]
                if r < 0.982:
                    auth = "APPROVED"
                elif r < 0.993:
                    auth = "DECLINED_AUTH"
                else:
                    auth = "DECLINED_LIMIT"

                asn = "HOSTING" if u[7] < 0.004 else (
                    "VPN" if u[7] < 0.024 else
                    ("RESIDENTIAL" if channel == "ECOM" and u[6] < 0.45 else "MOBILE"))

                ev = _empty_event()
                ev.update({
                    "transaction_id": f"TXN_{txn_counter:09d}",
                    "customer_id": cust.customer_id,
                    "merchant_id": m_ids[mi],
                    "timestamp": int(ts),
                    "amount": amount,
                    "payment_method": method,
                    "channel": channel,
                    "transaction_type": ttype,
                    "device_id": device_id,
                    "city": tx_city,
                    "lat": float(tx_lat),
                    "lon": float(tx_lon),
                    "beneficiary_id": ben,
                    "auth_result": auth,
                    "mcc_category": cat,
                    "session_id": f"SES_{cust.customer_id}_{day}_{k}",
                    "password_changed_recently": pw_recent,
                    "profile_changed_recently": pf_recent,
                    "failed_logins_1h": failed_logins if k == 0 else 0,
                    "session_duration_s": float(SESS[k]),
                    "typing_cadence_dev": float(TYPD[k]),
                    "ip_asn_type": asn,
                    "is_new_beneficiary": is_new_ben,
                    "sim_swapped_recently": int(u[12] < 0.0012),
                    "inbound_call_active": int(u[13] < 0.006),
                    "payment_link_referred": int(channel == "ECOM" and u[10] > 0.89),
                })
                rows.append(ev)
                txn_counter += 1

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    df = df[TRANSACTION_COLUMNS].sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    return df


def simulation_window(n_days: int) -> Tuple[int, int]:
    return SIM_EPOCH, SIM_EPOCH + n_days * DAY
