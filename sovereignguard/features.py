"""
Behavioural feature engineering (Phase 6).

CAUSALITY CONTRACT
------------------
Every feature for transaction *t* is computed using only information available
strictly before *t* (plus static entity attributes a bank would already hold:
the customer's account age and KYC level, the merchant's registry record, the
device's reputation). No feature may look forward in time, and no feature may
read a label column.

This is enforced structurally: the per-customer pass appends the current
transaction to its history only *after* emitting that transaction's features.
`assert_no_leakage()` re-checks the column contract.

Implementation is a single streaming pass per customer plus one global pass for
cross-account graph features. Pure Python at ~60-100k rows/s, which is fast
enough at the scales this lab runs and far easier to verify than a stack of
pandas rolling windows with off-by-one closure semantics.
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Dict, List

import numpy as np
import pandas as pd

from . import config as C
from .schema import FEATURE_COLUMNS, KYC_LEVELS, LABEL_COLUMNS

DAY = 86_400
W10M, W1H, W24H, W7D, W30D = 600, 3_600, 86_400, 7 * DAY, 30 * DAY

_METHODS = ("UPI", "CARD", "WALLET", "NETBANKING")
_CHANNELS = ("ECOM", "POS", "APP", "API")
_TYPES = ("TRANSFER", "WITHDRAWAL", "PURCHASE", "TOPUP")


def _haversine(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def _is_round(amount: float) -> int:
    """Round-number heuristic: exact hundreds/thousands, or parked just under
    a round figure (4,999 / 9,990) which is a structuring tell."""
    a = round(amount, 2)
    if a >= 100 and abs(a - round(a / 100.0) * 100) < 0.01:
        return 1
    for base in (1_000, 5_000, 10_000, 25_000, 50_000, 100_000):
        if 0 < base - a <= max(2.0, base * 0.002):
            return 1
    return 0


def _circ_hour_dev(hour: int, hour_hist: np.ndarray) -> float:
    """Circular distance from the customer's mean transaction hour."""
    total = hour_hist.sum()
    if total < 3:
        return 0.0
    ang = (np.arange(24) / 24.0) * 2 * math.pi
    x = float((hour_hist * np.cos(ang)).sum())
    y = float((hour_hist * np.sin(ang)).sum())
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return 0.0
    mean_h = (math.atan2(y, x) / (2 * math.pi)) * 24.0 % 24.0
    d = abs(hour - mean_h)
    return float(min(d, 24.0 - d))


# --------------------------------------------------------------------------
def _global_graph_features(tx: pd.DataFrame) -> Dict[str, np.ndarray]:
    """Cross-account features. Causal: each row sees only earlier rows.

    beneficiary_indegree_24h  – how many *distinct* accounts paid this
        beneficiary in the preceding 24h. Mule accounts collect from many
        unrelated payers; a family payee collects from one or two.

    merchant_new_customer_share_24h – of the payers this merchant saw in the
        preceding 24h, what share were transacting with it for the first time.
        A fraudulent storefront is ~100% first-timers; a real shop has regulars.
    """
    n = len(tx)
    ts = tx["timestamp"].to_numpy()
    cust = tx["customer_id"].to_numpy()
    ben = tx["beneficiary_id"].to_numpy()
    mer = tx["merchant_id"].to_numpy()

    ben_indeg = np.zeros(n, dtype=np.float32)
    mer_new_share = np.zeros(n, dtype=np.float32)

    # beneficiary -> deque of (ts, payer)
    ben_hist: Dict[str, deque] = defaultdict(deque)
    # merchant -> deque of (ts, payer, was_new_at_the_time)
    mer_hist: Dict[str, deque] = defaultdict(deque)
    # merchant -> set of customers ever seen (before current row)
    mer_seen: Dict[str, set] = defaultdict(set)

    for i in range(n):
        t = ts[i]
        b = ben[i]
        if b:
            dq = ben_hist[b]
            while dq and t - dq[0][0] > W24H:
                dq.popleft()
            ben_indeg[i] = len({p for _, p in dq})

        m = mer[i]
        dq2 = mer_hist[m]
        while dq2 and t - dq2[0][0] > W24H:
            dq2.popleft()
        if dq2:
            mer_new_share[i] = sum(1 for _, _, nw in dq2 if nw) / len(dq2)
        else:
            mer_new_share[i] = 1.0

        # append after emitting
        c = cust[i]
        was_new = c not in mer_seen[m]
        mer_seen[m].add(c)
        dq2.append((t, c, was_new))
        if b:
            ben_hist[b].append((t, c))

    return {"beneficiary_indegree_24h": ben_indeg,
            "merchant_new_customer_share_24h": mer_new_share}


# --------------------------------------------------------------------------
def build_features(
    tx: pd.DataFrame,
    customers: pd.DataFrame,
    merchants: pd.DataFrame,
    devices: pd.DataFrame,
) -> pd.DataFrame:
    """Return a DataFrame of FEATURE_COLUMNS aligned to `tx` (same order)."""
    if len(tx) == 0:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    tx = tx.sort_values(["timestamp", "transaction_id"], kind="mergesort").reset_index(drop=True)

    # ---- static lookups --------------------------------------------------
    cust_idx = {c: i for i, c in enumerate(customers["customer_id"].to_numpy())}
    c_home_lat = customers["home_lat"].to_numpy()
    c_home_lon = customers["home_lon"].to_numpy()
    c_med = customers["median_amount"].to_numpy()
    c_tpd = customers["txns_per_day"].to_numpy()
    c_acct = customers["account_age_days"].to_numpy()
    c_kyc = np.array([KYC_LEVELS.get(k, 1) for k in customers["kyc_level"].to_numpy()])
    c_lim = customers["credit_limit"].to_numpy()
    c_doc = customers["identity_doc_score"].to_numpy()
    c_con = customers["contactability_score"].to_numpy()
    c_foot = customers["digital_footprint_days"].to_numpy()

    mer_idx = {m: i for i, m in enumerate(merchants["merchant_id"].to_numpy())}
    m_med = merchants["median_ticket"].to_numpy()
    m_risk = merchants["intrinsic_risk"].to_numpy()
    m_age = merchants["merchant_age_days"].to_numpy()
    m_cb = merchants["chargeback_rate"].to_numpy()
    m_cnp = merchants["cnp_share"].to_numpy()
    m_vol = merchants["daily_volume"].to_numpy()

    dev_info: Dict[str, tuple] = {}
    for d in devices.itertuples(index=False):
        dev_info[d.device_id] = (int(d.is_emulator), int(d.is_rooted), float(d.reputation))

    high_risk = set(C.HIGH_RISK_LOCATIONS)

    # ---- raw event arrays -------------------------------------------------
    n = len(tx)
    a_cust = tx["customer_id"].to_numpy()
    a_mer = tx["merchant_id"].to_numpy()
    a_ts = tx["timestamp"].to_numpy().astype(np.int64)
    a_amt = tx["amount"].to_numpy().astype(np.float64)
    a_meth = tx["payment_method"].to_numpy()
    a_chan = tx["channel"].to_numpy()
    a_type = tx["transaction_type"].to_numpy()
    a_dev = tx["device_id"].to_numpy()
    a_city = tx["city"].to_numpy()
    a_lat = tx["lat"].to_numpy().astype(np.float64)
    a_lon = tx["lon"].to_numpy().astype(np.float64)
    a_ben = tx["beneficiary_id"].to_numpy()
    a_auth = tx["auth_result"].to_numpy()
    a_cat = tx["mcc_category"].to_numpy()
    a_pw = tx["password_changed_recently"].to_numpy().astype(np.int8)
    a_pf = tx["profile_changed_recently"].to_numpy().astype(np.int8)
    a_fl = tx["failed_logins_1h"].to_numpy().astype(np.float32)
    a_sd = tx["session_duration_s"].to_numpy().astype(np.float32)
    a_tc = tx["typing_cadence_dev"].to_numpy().astype(np.float32)
    a_asn = tx["ip_asn_type"].to_numpy()
    a_nb = tx["is_new_beneficiary"].to_numpy().astype(np.int8)
    a_sim = tx["sim_swapped_recently"].to_numpy().astype(np.int8)
    a_call = tx["inbound_call_active"].to_numpy().astype(np.int8)
    a_link = tx["payment_link_referred"].to_numpy().astype(np.int8)

    # ---- output buffers ---------------------------------------------------
    F: Dict[str, np.ndarray] = {
        k: np.zeros(n, dtype=np.float32) for k in FEATURE_COLUMNS
    }

    # ---- per-customer state ----------------------------------------------
    order = np.argsort(a_cust, kind="mergesort")   # groups rows by customer, stable in time

    class CustState:
        __slots__ = ("tl", "al", "p10", "p1h", "p24", "p7", "s1h", "s24", "maxdq",
                     "cum_n", "cum_sum", "cum_sq", "mer_cnt", "dev_cnt",
                     "city_cnt", "cat_cnt", "dev_first", "ben_first", "hour_hist",
                     "prev_ts", "prev_lat", "prev_lon", "prev_amt", "esc_run",
                     "declines", "risk_events", "first_ts",
                     "q_med", "q_p95", "q_stale", "w30_lo")

        def __init__(self):
            # Append-only timeline + monotonically advancing window pointers.
            # This makes every velocity feature amortised O(1) per transaction.
            self.tl: List[int] = []
            self.al: List[float] = []
            self.p10 = self.p1h = self.p24 = self.p7 = 0
            self.w30_lo = 0
            self.s1h = 0.0
            self.s24 = 0.0
            self.maxdq: deque = deque()   # indices, amounts decreasing (7d sliding max)
            self.cum_n = 0
            self.cum_sum = 0.0
            self.cum_sq = 0.0
            self.mer_cnt = defaultdict(int)
            self.dev_cnt = defaultdict(int)
            self.city_cnt = defaultdict(int)
            self.cat_cnt = defaultdict(int)
            self.dev_first = {}
            self.ben_first = {}
            self.hour_hist = np.zeros(24, dtype=np.float64)
            self.prev_ts = None
            self.prev_lat = None
            self.prev_lon = None
            self.prev_amt = None
            self.esc_run = 0
            self.declines = deque()
            self.risk_events = deque()
            self.first_ts = None
            # 30-day distribution profile, refreshed periodically rather than
            # per transaction (a production system refreshes a stored profile
            # on a schedule too). Always built from strictly past data.
            self.q_med = 0.0
            self.q_p95 = 0.0
            self.q_stale = 0

    states: Dict[str, CustState] = {}

    for i in order:
        cid = a_cust[i]
        st = states.get(cid)
        if st is None:
            st = states[cid] = CustState()
        ts = int(a_ts[i]); amt = float(a_amt[i])
        ci = cust_idx.get(cid, -1)
        mi = mer_idx.get(a_mer[i], -1)

        if st.first_ts is None:
            st.first_ts = ts

        # ---- advance window pointers (amortised O(1))
        tl, al, hn = st.tl, st.al, len(st.tl)
        while st.p7 < hn and ts - tl[st.p7] > W7D:
            st.p7 += 1
        while st.p24 < hn and ts - tl[st.p24] > W24H:
            st.s24 -= al[st.p24]
            st.p24 += 1
        while st.p1h < hn and ts - tl[st.p1h] > W1H:
            st.s1h -= al[st.p1h]
            st.p1h += 1
        while st.p10 < hn and ts - tl[st.p10] > W10M:
            st.p10 += 1
        while st.w30_lo < hn and ts - tl[st.w30_lo] > W30D:
            st.w30_lo += 1
        while st.declines and ts - st.declines[0] > W24H:
            st.declines.popleft()
        while st.risk_events and ts - st.risk_events[0] > W24H:
            st.risk_events.popleft()
        while st.maxdq and st.maxdq[0] < st.p7:
            st.maxdq.popleft()

        c10 = hn - st.p10
        c1h = hn - st.p1h
        c24 = hn - st.p24
        c7 = hn - st.p7
        s1h = st.s1h
        s24 = st.s24
        max7 = al[st.maxdq[0]] if st.maxdq else 0.0

        F["txns_last_10min"][i] = c10
        F["txns_last_1h"][i] = c1h
        F["txns_last_24h"][i] = c24
        F["txns_last_7d"][i] = c7
        F["amount_sum_1h"][i] = s1h
        F["amount_sum_24h"][i] = s24
        F["declines_last_24h"][i] = len(st.declines)
        F["customer_risk_events_24h"][i] = len(st.risk_events)
        F["seq_stage_index"][i] = c24            # position within the 24h burst

        # ---- amount features
        F["amount"][i] = amt
        F["amount_log"][i] = math.log1p(amt)
        prof_med = float(c_med[ci]) if ci >= 0 else max(amt, 1.0)
        if st.cum_n >= 5:
            past_mean = st.cum_sum / st.cum_n
            var = max(st.cum_sq / st.cum_n - past_mean ** 2, 1e-9)
            past_sd = math.sqrt(var)
            if st.q_stale <= 0 or st.q_med <= 0.0:
                win = al[st.w30_lo:hn]
                if win:
                    arr = np.asarray(win, dtype=np.float64)
                    st.q_med = float(np.median(arr))
                    st.q_p95 = float(np.percentile(arr, 95))
                else:
                    st.q_med, st.q_p95 = past_mean, past_mean * 3.0
                st.q_stale = 5
            st.q_stale -= 1
            med, p95 = st.q_med, st.q_p95
        else:
            past_mean, past_sd = prof_med, max(prof_med * 0.8, 1.0)
            med, p95 = prof_med, prof_med * 3.0
        F["amount_ratio_customer_median"][i] = amt / max(med, 1.0)
        F["amount_zscore_customer"][i] = (amt - past_mean) / max(past_sd, 1.0)
        F["amount_ratio_p95_30d"][i] = amt / max(p95, 1.0)
        F["amount_ratio_max_7d"][i] = amt / max(max7, 1.0) if max7 > 0 else 1.0
        F["amount_ratio_merchant_median"][i] = amt / max(float(m_med[mi]) if mi >= 0 else amt, 1.0)
        F["amount_round_number"][i] = _is_round(amt)
        F["amount_pct_of_credit_limit"][i] = amt / max(float(c_lim[ci]) if ci >= 0 else amt, 1.0)
        exp_day_value = max(prof_med * float(c_tpd[ci]) if ci >= 0 else prof_med, 1.0)
        F["amount_sum_24h_ratio_median_day"][i] = (s24 + amt) / exp_day_value

        # ---- escalation run
        if st.prev_amt is not None and amt > st.prev_amt * 1.15:
            st.esc_run += 1
        else:
            st.esc_run = 0
        F["escalating_amount_run"][i] = st.esc_run

        # ---- inter-arrival
        if st.prev_ts is None:
            F["seconds_since_prev_txn"][i] = float(W7D)
        else:
            F["seconds_since_prev_txn"][i] = float(ts - st.prev_ts)

        # ---- device
        dv = a_dev[i]
        dcnt = st.dev_cnt[dv]
        F["is_new_device"][i] = 1.0 if dcnt == 0 else 0.0
        F["device_txn_count"][i] = dcnt
        F["device_age_days"][i] = 0.0 if dv not in st.dev_first else (ts - st.dev_first[dv]) / DAY
        F["device_share_of_customer"][i] = dcnt / max(st.cum_n, 1)
        em, ro, rep = dev_info.get(dv, (0, 0, 0.35))   # unknown device: mediocre reputation
        F["is_emulator"][i] = em
        F["is_rooted"][i] = ro
        F["device_reputation"][i] = rep

        # ---- location
        cty = a_city[i]
        ccnt = st.city_cnt[cty]
        F["is_new_city"][i] = 1.0 if ccnt == 0 else 0.0
        F["city_txn_count"][i] = ccnt
        if ci >= 0:
            F["distance_from_home_km"][i] = _haversine(a_lat[i], a_lon[i],
                                                       c_home_lat[ci], c_home_lon[ci])
        if st.prev_lat is not None:
            dkm = _haversine(a_lat[i], a_lon[i], st.prev_lat, st.prev_lon)
            F["distance_from_prev_txn_km"][i] = dkm
            dt_h = max((ts - st.prev_ts) / 3600.0, 1.0 / 60.0)
            F["implied_speed_kmh"][i] = dkm / dt_h
        F["is_high_risk_location"][i] = 1.0 if cty in high_risk else 0.0

        # ---- merchant
        mcnt = st.mer_cnt[a_mer[i]]
        F["is_new_merchant"][i] = 1.0 if mcnt == 0 else 0.0
        F["customer_merchant_txn_count"][i] = mcnt
        if mi >= 0:
            F["merchant_intrinsic_risk"][i] = m_risk[mi]
            F["merchant_age_days"][i] = m_age[mi]
            F["merchant_chargeback_rate"][i] = m_cb[mi]
            F["merchant_cnp_share"][i] = m_cnp[mi]
            F["merchant_daily_volume_log"][i] = math.log1p(float(m_vol[mi]))
        cat = a_cat[i]
        F["category_affinity_score"][i] = st.cat_cnt[cat] / max(st.cum_n, 1)

        # ---- temporal
        hour = int((ts // 3600) % 24)
        dow = int(((ts // DAY) + 3) % 7)
        F["hour_of_day"][i] = hour
        F["day_of_week"][i] = dow
        F["is_night"][i] = 1.0 if hour < 6 else 0.0
        F["is_weekend"][i] = 1.0 if dow >= 5 else 0.0
        F["hour_deviation_from_profile"][i] = _circ_hour_dev(hour, st.hour_hist)
        tot_h = st.hour_hist.sum()
        F["is_unusual_hour_for_customer"][i] = (
            1.0 if tot_h >= 10 and (st.hour_hist[hour] / tot_h) < 0.015 else 0.0)

        # ---- account / identity
        if ci >= 0:
            elapsed_days = (ts - (st.first_ts or ts)) / DAY
            F["account_age_days"][i] = float(c_acct[ci]) + elapsed_days
            F["kyc_level_ord"][i] = c_kyc[ci]
            F["identity_doc_score"][i] = c_doc[ci]
            F["contactability_score"][i] = c_con[ci]
            F["digital_footprint_days"][i] = c_foot[ci]
        F["customer_lifetime_txns"][i] = st.cum_n

        # ---- session / auth passthrough
        F["password_changed_recently"][i] = a_pw[i]
        F["profile_changed_recently"][i] = a_pf[i]
        F["failed_logins_1h"][i] = a_fl[i]
        F["session_duration_s"][i] = a_sd[i]
        F["typing_cadence_dev"][i] = a_tc[i]
        F["ip_asn_is_hosting"][i] = 1.0 if a_asn[i] == "HOSTING" else 0.0
        F["ip_asn_is_vpn"][i] = 1.0 if a_asn[i] == "VPN" else 0.0
        F["is_new_beneficiary"][i] = a_nb[i]
        bid = a_ben[i]
        if bid:
            F["beneficiary_age_seconds"][i] = float(ts - st.ben_first.get(bid, ts))
        else:
            F["beneficiary_age_seconds"][i] = float(W30D)   # n/a sentinel
        F["sim_swapped_recently"][i] = a_sim[i]
        F["inbound_call_active"][i] = a_call[i]
        F["payment_link_referred"][i] = a_link[i]

        # ---- one-hots
        for m in _METHODS:
            F[f"method_{m}"][i] = 1.0 if a_meth[i] == m else 0.0
        for ch in _CHANNELS:
            F[f"channel_{ch}"][i] = 1.0 if a_chan[i] == ch else 0.0
        for tp in _TYPES:
            F[f"type_{tp}"][i] = 1.0 if a_type[i] == tp else 0.0

        # ================= APPEND TO HISTORY (never before emit) ===========
        is_risky = (dcnt == 0) or (ccnt == 0) or a_nb[i] or a_pw[i] or a_pf[i] \
            or (a_auth[i] != "APPROVED")
        if is_risky:
            st.risk_events.append(ts)
        if a_auth[i] != "APPROVED":
            st.declines.append(ts)
        tl.append(ts)
        al.append(amt)
        st.s1h += amt
        st.s24 += amt
        # sliding-window maximum over the 7-day window
        while st.maxdq and al[st.maxdq[-1]] <= amt:
            st.maxdq.pop()
        st.maxdq.append(hn)
        st.cum_n += 1
        st.cum_sum += amt
        st.cum_sq += amt * amt
        st.mer_cnt[a_mer[i]] += 1
        st.dev_cnt[dv] += 1
        st.city_cnt[cty] += 1
        st.cat_cnt[cat] += 1
        if dv not in st.dev_first:
            st.dev_first[dv] = ts
        if bid and bid not in st.ben_first:
            st.ben_first[bid] = ts
        st.hour_hist[hour] += 1.0
        st.prev_ts, st.prev_lat, st.prev_lon, st.prev_amt = ts, a_lat[i], a_lon[i], amt

    # ---- distinct-entity windows (second per-customer pass, vectorised) ---
    _fill_distinct_windows(tx, F)

    # ---- global graph features -------------------------------------------
    g = _global_graph_features(tx)
    for k, v in g.items():
        F[k] = v.astype(np.float32)

    feats = pd.DataFrame(F, columns=FEATURE_COLUMNS)
    feats = feats.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(np.float32)
    return feats


def _fill_distinct_windows(tx: pd.DataFrame, F: Dict[str, np.ndarray]) -> None:
    """distinct_{merchants,devices,cities}_24h via a sliding window per customer."""
    ts = tx["timestamp"].to_numpy().astype(np.int64)
    cust = tx["customer_id"].to_numpy()
    cols = {
        "distinct_merchants_24h": tx["merchant_id"].to_numpy(),
        "distinct_devices_24h": tx["device_id"].to_numpy(),
        "distinct_cities_24h": tx["city"].to_numpy(),
    }
    by_cust: Dict[str, List[int]] = defaultdict(list)
    for i in range(len(ts)):
        by_cust[cust[i]].append(i)

    for _, idxs in by_cust.items():
        for name, values in cols.items():
            out = F[name]
            dq: deque = deque()
            counts: Dict[str, int] = defaultdict(int)
            for i in idxs:
                t = ts[i]
                while dq and t - ts[dq[0]] > W24H:
                    j = dq.popleft()
                    counts[values[j]] -= 1
                    if counts[values[j]] <= 0:
                        del counts[values[j]]
                out[i] = len(counts)          # emit before appending self
                dq.append(i)
                counts[values[i]] += 1


def assert_no_leakage(feats: pd.DataFrame) -> None:
    bad = set(feats.columns) & set(LABEL_COLUMNS)
    if bad:
        raise AssertionError(f"Label columns leaked into features: {sorted(bad)}")
    missing = [c for c in FEATURE_COLUMNS if c not in feats.columns]
    if missing:
        raise AssertionError(f"Feature matrix missing columns: {missing}")
    extra = [c for c in feats.columns if c not in FEATURE_COLUMNS]
    if extra:
        raise AssertionError(f"Feature matrix has unexpected columns: {extra}")
    if not np.isfinite(feats.to_numpy()).all():
        raise AssertionError("Non-finite values in feature matrix")
