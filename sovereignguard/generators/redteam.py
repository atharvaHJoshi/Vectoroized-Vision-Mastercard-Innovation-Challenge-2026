"""
Red Team orchestrator (Phase 11).

    RedTeam.generate(attack_types, difficulty_mix, n_scenarios) -> AttackBatch

Diversity is deliberate and measured. For every scenario the orchestrator
independently samples the attack family, the difficulty, the victim (stratified
across personas so attacks are not concentrated on one behavioural profile),
and then the family generator itself samples amounts, devices, geography,
pacing, merchants and sequence length. `AttackBatch.diversity_report()`
quantifies the resulting coverage so the claim "we generate diverse attacks"
is a number rather than an assertion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from .. import config as C
from .. import taxonomy
from ..rng import substream
from ..schema import CUSTOMER_COLUMNS, MERCHANT_COLUMNS, TRANSACTION_COLUMNS
from .attacks import KNOBS, Knobs, VictimContext, build_victim_contexts
from .families import GENERATORS, MULTI_VICTIM, AttackResult

CASHOUT_CATEGORIES = ("P2P_TRANSFER", "CRYPTO_GATEWAY", "GAMING",
                      "FINANCIAL_SERVICES", "ECOMMERCE")


@dataclass
class AttackBatch:
    """Result of a Red Team run."""
    events: pd.DataFrame
    extra_customers: pd.DataFrame
    extra_merchants: pd.DataFrame
    scenarios: pd.DataFrame                 # one row per attack_id
    request: Dict = field(default_factory=dict)

    @property
    def n_scenarios(self) -> int:
        return len(self.scenarios)

    @property
    def n_events(self) -> int:
        return len(self.events)

    def diversity_report(self) -> Dict:
        """Quantified attack diversity (Phase 18 / Experiment 2 support)."""
        if self.events.empty:
            return {"n_scenarios": 0, "n_events": 0}
        ev = self.events
        sc = self.scenarios

        def shannon(series) -> float:
            p = series.value_counts(normalize=True).to_numpy()
            p = p[p > 0]
            return float(-(p * np.log(p)).sum())

        def norm_entropy(series) -> float:
            k = series.nunique()
            return float(shannon(series) / np.log(k)) if k > 1 else 0.0

        amt = ev["amount"].to_numpy()
        return {
            "n_scenarios": int(len(sc)),
            "n_events": int(len(ev)),
            "events_per_scenario_mean": round(float(len(ev) / max(1, len(sc))), 2),
            "attack_types": int(sc["attack_type"].nunique()),
            "difficulties": int(sc["difficulty"].nunique()),
            "distinct_victims": int(ev["customer_id"].nunique()),
            "distinct_victim_personas": int(sc["persona"].nunique()),
            "distinct_devices": int(ev["device_id"].nunique()),
            "distinct_cities": int(ev["city"].nunique()),
            "distinct_merchants": int(ev["merchant_id"].nunique()),
            "distinct_stages": int(ev["attack_stage"].nunique()),
            "distinct_methods": int(ev["payment_method"].nunique()),
            "amount_span_log10": round(float(np.log10(max(amt.max(), 1) /
                                                      max(amt.min(), 1))), 2),
            "amount_p05": round(float(np.percentile(amt, 5)), 2),
            "amount_p50": round(float(np.percentile(amt, 50)), 2),
            "amount_p95": round(float(np.percentile(amt, 95)), 2),
            "entropy_attack_type": round(norm_entropy(sc["attack_type"]), 4),
            "entropy_difficulty": round(norm_entropy(sc["difficulty"]), 4),
            "entropy_persona": round(norm_entropy(sc["persona"]), 4),
            "entropy_city": round(norm_entropy(ev["city"]), 4),
            "entropy_stage": round(norm_entropy(ev["attack_stage"]), 4),
            "type_counts": sc["attack_type"].value_counts().to_dict(),
            "difficulty_counts": sc["difficulty"].value_counts().to_dict(),
        }


class RedTeam:
    """Attack generator bound to a specific synthetic population."""

    def __init__(self, customers: pd.DataFrame, merchants: pd.DataFrame,
                 legit_tx: pd.DataFrame, seed: int):
        self.customers = customers
        self.merchants = merchants
        self.seed = seed
        self.contexts = build_victim_contexts(legit_tx, customers)
        self.victim_ids = [v for v, ctx in self.contexts.items() if ctx.n_txns >= 8]
        if not self.victim_ids:
            self.victim_ids = list(self.contexts.keys())
        # Stratify victims by persona so attacks are not concentrated.
        self.by_persona: Dict[str, List[str]] = {}
        for cid in self.victim_ids:
            self.by_persona.setdefault(self.contexts[cid].persona, []).append(cid)
        cats = self.merchants["category"].to_numpy()
        mask = np.isin(cats, CASHOUT_CATEGORIES)
        self.cashout_ids = self.merchants["merchant_id"].to_numpy()[mask]
        if len(self.cashout_ids) == 0:
            self.cashout_ids = self.merchants["merchant_id"].to_numpy()
        taxonomy.validate()

    # ------------------------------------------------------------------
    def _sample_victim(self, rng: np.random.Generator) -> VictimContext:
        personas = list(self.by_persona.keys())
        p = personas[int(rng.integers(0, len(personas)))]
        pool = self.by_persona[p]
        v = self.contexts[pool[int(rng.integers(0, len(pool)))]]
        # Anchor the scenario at a uniformly random point in the victim's own
        # active window rather than at their last transaction. Without this,
        # every attack lands at the end of the simulation and a time-ordered
        # split has almost no fraud to train on.
        lo = v.first_ts + int(0.10 * max(1, v.last_ts - v.first_ts))
        hi = max(lo + 1, v.last_ts)
        return v.anchored(int(rng.integers(lo, hi + 1)))

    def generate(
        self,
        n_scenarios: int,
        attack_types: Optional[Sequence[str]] = None,
        difficulty_mix: Optional[Dict[str, float]] = None,
        *,
        knob_overrides: Optional[Dict[str, Knobs]] = None,
        stream: str = "redteam",
        campaign: str = "",
    ) -> AttackBatch:
        """Generate `n_scenarios` attack sequences.

        knob_overrides lets the adaptive engine substitute measured-weakness
        parameters for a difficulty label without touching the base generators.
        """
        attack_types = list(attack_types or C.ATTACK_TYPES)
        unknown = set(attack_types) - set(C.ATTACK_TYPES)
        if unknown:
            raise ValueError(f"Unknown attack types: {sorted(unknown)}")
        difficulty_mix = dict(difficulty_mix or {"EASY": 0.25, "MEDIUM": 0.40, "HARD": 0.35})
        rng = substream(self.seed, f"{stream}:{','.join(sorted(attack_types))}:{n_scenarios}")

        # Sample family by taxonomy prior restricted to the requested types.
        prior = taxonomy.type_mix()
        tw = np.array([prior[t] for t in attack_types], dtype=float)
        tw /= tw.sum()
        dkeys = list(difficulty_mix.keys())
        dw = np.array([difficulty_mix[k] for k in dkeys], dtype=float)
        dw /= dw.sum()

        all_events: List[Dict] = []
        extra_c: List[Dict] = []
        extra_m: List[Dict] = []
        scen_rows: List[Dict] = []

        for i in range(n_scenarios):
            atype = attack_types[int(rng.choice(len(attack_types), p=tw))]
            diff = dkeys[int(rng.choice(len(dkeys), p=dw))]
            knobs = (knob_overrides or {}).get(diff, KNOBS[diff])
            victim = self._sample_victim(rng)
            attack_id = f"{atype[:3]}{diff[:1]}{i:06d}"
            gen = GENERATORS[atype]

            if atype in MULTI_VICTIM:
                n_extra = int(rng.integers(3, 12))
                extras = [self._sample_victim(rng) for _ in range(n_extra)]
                res: AttackResult = gen(victim, knobs, rng, self.merchants,
                                        self.cashout_ids, attack_id, extra_victims=extras)
            else:
                res = gen(victim, knobs, rng, self.merchants, self.cashout_ids, attack_id)

            if not res.events:
                continue
            if campaign:
                for e in res.events:
                    e["campaign_id"] = campaign
            all_events.extend(res.events)
            extra_c.extend(res.extra_customers)
            extra_m.extend(res.extra_merchants)
            amts = [e["amount"] for e in res.events]
            scen_rows.append({
                "attack_id": attack_id,
                "attack_type": atype,
                "difficulty": diff,
                "victim_customer_id": victim.customer_id,
                "persona": victim.persona,
                "n_events": len(res.events),
                "total_value": round(float(sum(amts)), 2),
                "max_event_value": round(float(max(amts)), 2),
                "span_seconds": int(max(e["timestamp"] for e in res.events) -
                                    min(e["timestamp"] for e in res.events)),
                "stages": "|".join(dict.fromkeys(e["attack_stage"] for e in res.events)),
                "severity": taxonomy.severity(atype),
                "campaign_id": campaign or attack_id,
            })

        ev_df = (pd.DataFrame(all_events)[TRANSACTION_COLUMNS]
                 if all_events else pd.DataFrame(columns=TRANSACTION_COLUMNS))
        ec_df = (pd.DataFrame(extra_c)[CUSTOMER_COLUMNS]
                 if extra_c else pd.DataFrame(columns=CUSTOMER_COLUMNS))
        em_df = (pd.DataFrame(extra_m)[MERCHANT_COLUMNS]
                 if extra_m else pd.DataFrame(columns=MERCHANT_COLUMNS))
        return AttackBatch(
            events=ev_df.reset_index(drop=True),
            extra_customers=ec_df.reset_index(drop=True),
            extra_merchants=em_df.reset_index(drop=True),
            scenarios=pd.DataFrame(scen_rows),
            request={"n_scenarios": n_scenarios, "attack_types": attack_types,
                     "difficulty_mix": difficulty_mix, "stream": stream,
                     "campaign": campaign},
        )


# --------------------------------------------------------------------------
def merge_world(legit_tx: pd.DataFrame, customers: pd.DataFrame, merchants: pd.DataFrame,
                devices: pd.DataFrame, batches: Sequence[AttackBatch]):
    """Splice attack events into the legitimate timeline and extend the
    population with any entities the attacks minted.

    Feature building then runs over the merged stream, which is what gives
    attack rows genuine history-derived features.
    """
    ev_frames = [legit_tx] + [b.events for b in batches if not b.events.empty]
    tx = pd.concat(ev_frames, ignore_index=True)
    tx = tx.sort_values(["timestamp", "transaction_id"], kind="mergesort").reset_index(drop=True)

    c_frames = [customers] + [b.extra_customers for b in batches if not b.extra_customers.empty]
    cu = pd.concat(c_frames, ignore_index=True).drop_duplicates("customer_id", keep="first")
    m_frames = [merchants] + [b.extra_merchants for b in batches if not b.extra_merchants.empty]
    me = pd.concat(m_frames, ignore_index=True).drop_duplicates("merchant_id", keep="first")

    # Devices appearing for the first time in the merged stream must be
    # registered, but they are registered WITHOUT reference to whether an
    # attack created them.
    #
    # This matters more than it looks, and it bit this project twice.
    #
    #   First bug: reputation was set to 0.12 for any device whose id started
    #   with DEV_ATK_, making `device_reputation` a perfect label oracle.
    #
    #   Second bug: after fixing that, newly-registered devices were drawn from
    #   Beta(2,3) (mean 0.40) while the original registry used Beta(7.5,1.7)
    #   (mean 0.80). Since every attacker device is newly-registered, the
    #   *registration event itself* still leaked the label — attacker devices
    #   averaged 0.41 reputation against 0.80 for the rest.
    #
    # A real bank cannot know a device belongs to an attacker the first time it
    # appears; that is precisely what the detector is supposed to work out. So
    # unknown devices are drawn from EXACTLY the same distribution as the
    # legitimate population in population.py. Keep these two in sync.
    known = set(devices["device_id"])
    new_devs = [d for d in tx["device_id"].unique() if d not in known]
    if new_devs:
        drng = np.random.default_rng(abs(hash(("devreg", len(new_devs)))) % (2**31))
        rows = []
        for d in new_devs:
            rows.append({
                "device_id": d,
                "owner_customer_id": "",
                "os_family": str(drng.choice(["ANDROID", "IOS", "WINDOWS", "MACOS"],
                                             p=[0.66, 0.22, 0.09, 0.03])),
                "device_class": str(drng.choice(["PHONE", "TABLET", "DESKTOP"],
                                                p=[0.85, 0.07, 0.08])),
                "first_seen_day": 0,
                # identical to generate_devices() in population.py
                "is_emulator": 0,
                "is_rooted": int(drng.random() < 0.026),
                "reputation": round(float(np.clip(drng.beta(7.5, 1.7), 0.02, 1.0)), 4),
            })
        devices = pd.concat([devices, pd.DataFrame(rows)], ignore_index=True)

    return tx, cu, me, devices
