"""
Gap analysis (Phase 16) — the module that makes this a lab rather than a benchmark.

A benchmark reports "recall was 0.82". A lab answers "and here is *why* the
other 0.18 got through, ranked by how much of the miss each cause explains".

Method
------
For every missed attack event we test a set of named, human-meaningful evasion
hypotheses (low value, slow pacing, familiar device, familiar geography,
existing payee, merchant mimicry, off-sequence, thin identity). Each hypothesis
is a predicate on the *features* of that row, calibrated against the legitimate
population so "low value" means "inside the range honest customers occupy"
rather than an arbitrary constant.

Two numbers are reported per cause, and the distinction matters:

  share_of_missed – of the attacks that got through, what fraction show this
                    trait. Descriptive.

  lift            – how much more common the trait is among MISSED attacks than
                    among DETECTED ones. This is the causal-ish signal: a trait
                    present in 90% of misses but also 90% of catches explains
                    nothing. Lift is what the adversarial generator targets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from ..schema import FEATURE_LABELS


# --------------------------------------------------------------------------
@dataclass
class Hypothesis:
    """A named, testable reason an attack might evade detection."""
    key: str
    label: str
    description: str
    predicate: Callable[[pd.DataFrame, Dict[str, float]], np.ndarray]
    # Which knob the adversarial generator should push to exploit this gap.
    exploit_knob: str
    remediation: str


def _q(cal: Dict[str, float], name: str, default: float) -> float:
    return float(cal.get(name, default))


HYPOTHESES: List[Hypothesis] = [
    Hypothesis(
        key="LOW_VALUE",
        label="Low-value amounts",
        description=("The attack never moved an amount large enough to stand out. "
                     "Every transaction sat inside the band ordinary customers occupy."),
        predicate=lambda F, cal: F["amount_ratio_customer_median"].to_numpy() <= _q(cal, "amt_ratio_p75", 2.0),
        exploit_knob="amount_mult",
        remediation=("Score cumulative value over 7-30 day windows, not just per-transaction "
                     "amount. Add sub-threshold-repetition features."),
    ),
    Hypothesis(
        key="SLOW_PACING",
        label="Slow / patient pacing",
        description=("Events were spaced far enough apart that no velocity window "
                     "ever saw them together."),
        predicate=lambda F, cal: F["seconds_since_prev_txn"].to_numpy() >= _q(cal, "gap_p50", 3600.0),
        exploit_knob="gap",
        remediation=("Add long-horizon velocity (7d/30d) and per-account risk state that "
                     "decays over days rather than resetting every 24 hours."),
    ),
    Hypothesis(
        key="FAMILIAR_DEVICE",
        label="Familiar device",
        description=("Executed from a device already established on the account, so "
                     "device-novelty signals never fired."),
        predicate=lambda F, cal: (F["is_new_device"].to_numpy() < 0.5) &
                                 (F["device_txn_count"].to_numpy() >= 3),
        exploit_knob="p_new_device",
        remediation=("Behavioural-biometric continuity within the session; detect "
                     "device-familiar but behaviour-anomalous activity."),
    ),
    Hypothesis(
        key="FAMILIAR_GEOGRAPHY",
        label="Familiar geography",
        description=("Ran from the victim's usual location, defeating distance and "
                     "impossible-travel checks."),
        predicate=lambda F, cal: (F["is_new_city"].to_numpy() < 0.5) &
                                 (F["distance_from_home_km"].to_numpy() <= _q(cal, "dist_p75", 50.0)),
        exploit_knob="p_new_city",
        remediation=("Do not treat home geography as exculpatory; weight it lower when "
                     "other context is anomalous."),
    ),
    Hypothesis(
        key="EXISTING_PAYEE",
        label="Existing beneficiary",
        description=("Value was routed to a payee already on file, so new-payee "
                     "controls and cooling-off windows did not apply."),
        predicate=lambda F, cal: (F["is_new_beneficiary"].to_numpy() < 0.5) &
                                 (F["type_TRANSFER"].to_numpy() > 0.5),
        exploit_knob="p_reuse_existing_payee",
        remediation=("Monitor dormant-payee reactivation and sudden step-changes in "
                     "amount to a long-standing payee."),
    ),
    Hypothesis(
        key="MERCHANT_MIMICRY",
        label="Merchant mimicry",
        description=("Cash-out went through merchants the victim already used, or "
                     "through an aged merchant record, so acceptance-side signals stayed clean."),
        predicate=lambda F, cal: (F["is_new_merchant"].to_numpy() < 0.5) |
                                 (F["merchant_age_days"].to_numpy() >= _q(cal, "mer_age_p50", 200.0)),
        exploit_knob="merchant_reuse",
        remediation=("Track per-customer-per-merchant amount distributions, not just "
                     "whether the pair has been seen before."),
    ),
    Hypothesis(
        key="NO_CREDENTIAL_TRACE",
        label="No credential trace",
        description=("No password change, profile edit or failed-login burst preceded "
                     "the fraud, so account-compromise heuristics had nothing to fire on."),
        predicate=lambda F, cal: (F["password_changed_recently"].to_numpy() < 0.5) &
                                 (F["profile_changed_recently"].to_numpy() < 0.5) &
                                 (F["failed_logins_1h"].to_numpy() < 1),
        exploit_knob="p_credential_change",
        remediation=("Cover the authorised-push-payment case explicitly: fraud where "
                     "nothing is compromised needs intent signals, not auth signals."),
    ),
    Hypothesis(
        key="LOW_VELOCITY_FOOTPRINT",
        label="Low velocity footprint",
        description=("Transaction counts stayed inside normal daily rhythm; no burst "
                     "or fan-out was visible in any short window."),
        predicate=lambda F, cal: F["txns_last_24h"].to_numpy() <= _q(cal, "vel24_p75", 8.0),
        exploit_knob="n_drain",
        remediation="Aggregate across the campaign, not the account-hour.",
    ),
    Hypothesis(
        key="THIN_BUT_CLEAN_IDENTITY",
        label="Aged synthetic identity",
        description=("A fabricated identity that had already accumulated enough "
                     "account age and clean history to look established."),
        predicate=lambda F, cal: (F["account_age_days"].to_numpy() >= _q(cal, "acct_age_p25", 200.0)) &
                                 (F["identity_doc_score"].to_numpy() >= 0.5),
        exploit_knob="identity_quality",
        remediation=("Verify against authoritative sources at origination; footprint "
                     "consistency beats behavioural history for thin files."),
    ),
    Hypothesis(
        key="SEQUENCE_ONLY",
        label="Visible only as a sequence",
        description=("Individually unremarkable events whose only incriminating "
                     "property is their ordering — invisible to per-row scoring."),
        predicate=lambda F, cal: (F["seq_stage_index"].to_numpy() <= 2) &
                                 (F["amount_ratio_customer_median"].to_numpy() <= 3.0),
        exploit_knob="spread_days",
        remediation=("Sequence model over the account timeline, plus beneficiary "
                     "in-degree graph features."),
    ),
]

HYPOTHESIS_BY_KEY = {h.key: h for h in HYPOTHESES}


# --------------------------------------------------------------------------
def calibrate(F_legit: pd.DataFrame) -> Dict[str, float]:
    """Derive hypothesis thresholds from the *legitimate* population.

    This is what makes "low value" mean "indistinguishable from honest traffic"
    rather than an arbitrary rupee figure, and keeps the analysis valid when the
    data scale or persona mix changes.
    """
    def q(col: str, p: float, default: float) -> float:
        if col not in F_legit.columns or len(F_legit) == 0:
            return default
        v = F_legit[col].to_numpy()
        v = v[np.isfinite(v)]
        return float(np.quantile(v, p)) if v.size else default

    return {
        "amt_ratio_p75": q("amount_ratio_customer_median", 0.75, 2.0),
        "amt_ratio_p95": q("amount_ratio_customer_median", 0.95, 6.0),
        "gap_p50": q("seconds_since_prev_txn", 0.50, 3600.0),
        "dist_p75": q("distance_from_home_km", 0.75, 50.0),
        "mer_age_p50": q("merchant_age_days", 0.50, 200.0),
        "vel24_p75": q("txns_last_24h", 0.75, 8.0),
        "acct_age_p25": q("account_age_days", 0.25, 200.0),
    }


@dataclass
class GapReport:
    n_attacks: int
    n_detected: int
    n_missed: int
    recall: float
    threshold: float
    causes: List[Dict] = field(default_factory=list)
    by_attack_type: List[Dict] = field(default_factory=list)
    by_difficulty: List[Dict] = field(default_factory=list)
    by_stage: List[Dict] = field(default_factory=list)
    weakest_segments: List[Dict] = field(default_factory=list)
    examples: List[Dict] = field(default_factory=list)
    calibration: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "n_attacks": self.n_attacks, "n_detected": self.n_detected,
            "n_missed": self.n_missed, "recall": self.recall,
            "threshold": self.threshold, "causes": self.causes,
            "by_attack_type": self.by_attack_type,
            "by_difficulty": self.by_difficulty, "by_stage": self.by_stage,
            "weakest_segments": self.weakest_segments,
            "examples": self.examples, "calibration": self.calibration,
        }

    def headline(self) -> str:
        if not self.causes:
            return f"No misses to explain (recall {self.recall:.4f})."
        top = self.causes[0]
        return (f"{self.n_missed} of {self.n_attacks} attacks evaded detection "
                f"(recall {self.recall:.4f}). Dominant evasion trait: "
                f"{top['label']} — present in {top['share_of_missed']:.0%} of misses, "
                f"lift {top['lift']:.2f}x vs. detected.")

    def priority_knobs(self, top_n: int = 3) -> List[Tuple[str, str, float]]:
        """(knob, cause_key, lift) for the adversarial generator to exploit."""
        out = []
        for c in self.causes[:top_n]:
            out.append((c["exploit_knob"], c["key"], float(c["lift"])))
        return out


# --------------------------------------------------------------------------
def analyse_gaps(
    F: pd.DataFrame,
    tx: pd.DataFrame,
    prob: np.ndarray,
    threshold: float,
    *,
    max_examples: int = 12,
    min_support: int = 3,
) -> GapReport:
    """Explain which attacks evaded the detector and why.

    F, tx and prob must be row-aligned.
    """
    y = tx["fraud_label"].to_numpy().astype(int)
    p = np.asarray(prob, dtype=np.float64).ravel()
    pred = (p >= threshold).astype(int)

    is_attack = y == 1
    missed = is_attack & (pred == 0)
    detected = is_attack & (pred == 1)
    n_a, n_m, n_d = int(is_attack.sum()), int(missed.sum()), int(detected.sum())
    recall = float(n_d / n_a) if n_a else 0.0

    cal = calibrate(F.loc[y == 0])

    rep = GapReport(n_attacks=n_a, n_detected=n_d, n_missed=n_m, recall=recall,
                    threshold=float(threshold), calibration=cal)
    if n_m == 0:
        return rep

    F_missed = F.loc[missed]
    F_detected = F.loc[detected] if n_d else F.iloc[0:0]

    # ---- cause attribution ------------------------------------------------
    causes = []
    for h in HYPOTHESES:
        m_hit = h.predicate(F_missed, cal)
        share_missed = float(np.mean(m_hit)) if len(F_missed) else 0.0
        if n_d:
            d_hit = h.predicate(F_detected, cal)
            share_detected = float(np.mean(d_hit))
        else:
            share_detected = 0.0
        lift = float(share_missed / max(share_detected, 1e-6))
        # excess = how many misses this trait explains beyond the detected base rate
        excess = float((share_missed - share_detected) * n_m)
        causes.append({
            "key": h.key, "label": h.label, "description": h.description,
            "share_of_missed": round(share_missed, 4),
            "share_of_detected": round(share_detected, 4),
            "lift": round(min(lift, 999.0), 3),
            "excess_misses_explained": round(excess, 1),
            "n_missed_with_trait": int(m_hit.sum()),
            "exploit_knob": h.exploit_knob,
            "remediation": h.remediation,
        })
    # Rank by how much of the miss the trait actually explains, then by lift.
    causes.sort(key=lambda c: (-c["excess_misses_explained"], -c["lift"]))
    # Normalised attribution over positive-excess causes, for the dashboard chart.
    tot = sum(max(c["excess_misses_explained"], 0.0) for c in causes) or 1.0
    for c in causes:
        c["attribution"] = round(max(c["excess_misses_explained"], 0.0) / tot, 4)
    rep.causes = causes

    # ---- segment breakdowns ----------------------------------------------
    def breakdown(col: str) -> List[Dict]:
        if col not in tx.columns:
            return []
        vals = tx[col].to_numpy()
        rows = []
        for key in sorted(set(vals[is_attack].tolist())):
            m = is_attack & (vals == key)
            cnt = int(m.sum())
            if cnt < min_support:
                continue
            det = int((pred[m] == 1).sum())
            rows.append({"group": str(key), "n": cnt, "detected": det,
                         "missed": cnt - det,
                         "recall": round(float(det / cnt), 4),
                         "share_of_all_misses": round(float((m & missed).sum() / n_m), 4),
                         "mean_score": round(float(p[m].mean()), 5)})
        return sorted(rows, key=lambda r: r["recall"])

    rep.by_attack_type = breakdown("attack_type")
    rep.by_difficulty = breakdown("difficulty")
    rep.by_stage = breakdown("attack_stage")

    # ---- weakest (attack_type x difficulty) segments ---------------------
    if "attack_type" in tx and "difficulty" in tx:
        at = tx["attack_type"].to_numpy()
        df = tx["difficulty"].to_numpy()
        segs = []
        for a in sorted(set(at[is_attack].tolist())):
            for d in sorted(set(df[is_attack].tolist())):
                m = is_attack & (at == a) & (df == d)
                cnt = int(m.sum())
                if cnt < min_support:
                    continue
                det = int((pred[m] == 1).sum())
                segs.append({"attack_type": str(a), "difficulty": str(d),
                             "n": cnt, "detected": det, "missed": cnt - det,
                             "recall": round(float(det / cnt), 4)})
        rep.weakest_segments = sorted(segs, key=lambda r: (r["recall"], -r["missed"]))[:12]

    # ---- worked examples -------------------------------------------------
    idx_missed = np.where(missed)[0]
    # show the most confidently-wrong misses (lowest score) — most instructive
    order = idx_missed[np.argsort(p[idx_missed])][:max_examples]
    for i in order:
        traits = [h.key for h in HYPOTHESES
                  if bool(h.predicate(F.iloc[[i]], cal)[0])]
        rep.examples.append({
            "transaction_id": str(tx["transaction_id"].iloc[i]),
            "attack_id": str(tx["attack_id"].iloc[i]),
            "attack_type": str(tx["attack_type"].iloc[i]),
            "difficulty": str(tx["difficulty"].iloc[i]),
            "attack_stage": str(tx["attack_stage"].iloc[i]),
            "amount": float(tx["amount"].iloc[i]),
            "score": round(float(p[i]), 6),
            "amount_ratio_customer_median": round(
                float(F["amount_ratio_customer_median"].iloc[i]), 3),
            "seconds_since_prev_txn": int(F["seconds_since_prev_txn"].iloc[i]),
            "is_new_device": int(F["is_new_device"].iloc[i]),
            "traits": traits,
        })
    return rep


def compare_gap_reports(before: GapReport, after: GapReport) -> Dict:
    """Did closing the gap actually work, and did new gaps open?"""
    b = {c["key"]: c for c in before.causes}
    a = {c["key"]: c for c in after.causes}
    rows = []
    for key in sorted(set(b) | set(a)):
        bb, aa = b.get(key), a.get(key)
        rows.append({
            "key": key,
            "label": (bb or aa)["label"],
            "share_before": (bb or {}).get("share_of_missed"),
            "share_after": (aa or {}).get("share_of_missed"),
            "lift_before": (bb or {}).get("lift"),
            "lift_after": (aa or {}).get("lift"),
            "excess_before": (bb or {}).get("excess_misses_explained"),
            "excess_after": (aa or {}).get("excess_misses_explained"),
        })
    return {
        "recall_before": before.recall, "recall_after": after.recall,
        "recall_delta": round(after.recall - before.recall, 4),
        "missed_before": before.n_missed, "missed_after": after.n_missed,
        "causes": rows,
    }
