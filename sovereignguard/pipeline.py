"""
End-to-end pipeline (Phases 15, 18) — the IDENTIFY -> GENERATE -> ATTACK ->
DETECT -> EXPLAIN -> ADAPT -> RETEST loop as executable code.

`build_world`      synthetic population + legitimate traffic + baseline attacks
`train_baseline`   Blue Team v1
`adversarial_loop` the headline experiment: diagnose, adapt, retrain, retest

METHODOLOGICAL GUARD (read this before trusting any number this produces)
------------------------------------------------------------------------
The adversarial loop is easy to fake. If you generate adversarial attacks,
retrain on them, and then evaluate on those same attacks, recall goes up simply
because the model memorised them. That result is worthless.

`adversarial_loop` therefore generates TWO independent adversarial batches from
the same generator and parameters but different RNG streams:

    adv_train  – added to the training set
    adv_eval   – never seen during training, used for every reported number

Both the before and after models are evaluated on the *identical* held-out
`adv_eval` batch at the *same* false-positive budget. That makes the reported
recall delta a genuine generalisation gain rather than memorisation, and it is
why the improvement figures in this project are smaller than the ones a
naive implementation would print.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import config as C
from . import taxonomy
from .detection import (Detector, Split, temporal_grouped_split, train_detector,
                        unseen_attack_split)
from .evaluation.gap_analysis import GapReport, analyse_gaps, compare_gap_reports
from .evaluation.metrics import (choose_threshold_at_fpr, compute_metrics,
                                 operating_curve, per_group_metrics)
from .features import assert_no_leakage, build_features
from .generators.adversarial import AdversarialGenerator, scenario_max_score
from .generators.population import build_population
from .generators.redteam import AttackBatch, RedTeam, merge_world
from .generators.transactions import generate_legitimate_transactions
from .schema import FEATURE_COLUMNS


def _log(msg: str, quiet: bool = False) -> None:
    if not quiet:
        print(f"[sovereignguard] {msg}", flush=True)


def _concat_nonempty(frames: Sequence[pd.DataFrame],
                     empty_like: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate, dropping empty frames first.

    pandas warns (and will change behaviour) when all-NA/empty frames take part
    in a concat, because their dtypes participate in type resolution. Filtering
    them out keeps dtypes stable across rebuilds.
    """
    keep = [f for f in frames if f is not None and len(f) > 0]
    if not keep:
        if empty_like is not None:
            return empty_like.copy()
        return pd.DataFrame()
    return pd.concat(keep, ignore_index=True)


# ==========================================================================
@dataclass
class World:
    """A fully built synthetic payment world with fraud injected."""
    tx: pd.DataFrame
    feats: pd.DataFrame
    customers: pd.DataFrame
    merchants: pd.DataFrame
    devices: pd.DataFrame
    legit_tx: pd.DataFrame
    batch: AttackBatch
    red_team: RedTeam
    config: Dict = field(default_factory=dict)

    @property
    def y(self) -> np.ndarray:
        return self.tx["fraud_label"].to_numpy().astype(int)

    def summary(self) -> Dict:
        return {
            "n_customers": int(len(self.customers)),
            "n_merchants": int(len(self.merchants)),
            "n_devices": int(len(self.devices)),
            "n_transactions": int(len(self.tx)),
            "n_legitimate": int((self.y == 0).sum()),
            "n_fraud_events": int((self.y == 1).sum()),
            "fraud_prevalence": round(float(self.y.mean()), 5),
            "n_attack_scenarios": int(self.batch.n_scenarios),
            "n_features": len(FEATURE_COLUMNS),
            "window_days": self.config.get("n_days"),
            "attack_types": sorted(set(self.batch.scenarios["attack_type"]))
            if not self.batch.scenarios.empty else [],
            "diversity": self.batch.diversity_report(),
        }

    def rebuild_with(self, batches: Sequence[AttackBatch]) -> "World":
        """Splice additional attack batches in and recompute features.

        Features are recomputed over the whole merged stream so the new attacks
        inherit genuine history-derived context.
        """
        tx, cu, me, dv = merge_world(self.legit_tx, self.customers, self.merchants,
                                     self.devices, list(batches))
        tx = tx.sort_values(["timestamp", "transaction_id"],
                            kind="mergesort").reset_index(drop=True)
        feats = build_features(tx, cu, me, dv)
        assert_no_leakage(feats)
        combined = AttackBatch(
            events=_concat_nonempty([b.events for b in batches], self.tx.iloc[0:0]),
            extra_customers=_concat_nonempty(
                [b.extra_customers for b in batches],
                self.customers.iloc[0:0]).drop_duplicates("customer_id"),
            extra_merchants=_concat_nonempty(
                [b.extra_merchants for b in batches],
                self.merchants.iloc[0:0]).drop_duplicates("merchant_id"),
            scenarios=_concat_nonempty([b.scenarios for b in batches], None),
            request={"merged_from": len(batches)})
        return World(tx=tx, feats=feats, customers=cu, merchants=me, devices=dv,
                     legit_tx=self.legit_tx, batch=combined,
                     red_team=self.red_team, config=self.config)


# ==========================================================================
def build_world(
    scale: str = C.DEFAULT_SCALE,
    seed: int = C.SEED,
    *,
    target_prevalence: float = 0.010,
    attack_types: Optional[Sequence[str]] = None,
    difficulty_mix: Optional[Dict[str, float]] = None,
    n_customers: Optional[int] = None,
    n_merchants: Optional[int] = None,
    n_days: Optional[int] = None,
    quiet: bool = False,
) -> World:
    """Steps 1-5: population, legitimate traffic, attack injection, features.

    `target_prevalence` is the fraud share of the final event stream. The number
    of scenarios needed is derived from the measured events-per-scenario rate,
    so prevalence is controlled rather than incidental.
    """
    prof = C.SCALES[scale]
    n_customers = n_customers or prof.n_customers
    n_merchants = n_merchants or prof.n_merchants
    n_days = n_days or prof.n_days
    taxonomy.validate()

    t0 = time.perf_counter()
    _log(f"population: {n_customers} customers, {n_merchants} merchants", quiet)
    customers, merchants, devices = build_population(n_customers, n_merchants, seed)

    _log(f"legitimate traffic over {n_days} days...", quiet)
    legit = generate_legitimate_transactions(customers, merchants, devices, n_days, seed)
    _log(f"  {len(legit):,} legitimate transactions", quiet)

    rt = RedTeam(customers, merchants, legit, seed)

    # Calibrate scenario count to hit the requested prevalence.
    probe = rt.generate(60, attack_types=attack_types, difficulty_mix=difficulty_mix,
                        stream="probe")
    eps = max(probe.n_events / max(probe.n_scenarios, 1), 1.0)
    n_needed = int(round((target_prevalence * len(legit)) /
                         max(eps * (1.0 - target_prevalence), 1e-9)))
    n_needed = max(20, n_needed)
    _log(f"red team: {n_needed} scenarios (~{eps:.1f} events each) "
         f"for {target_prevalence:.1%} prevalence", quiet)
    batch = rt.generate(n_needed, attack_types=attack_types,
                        difficulty_mix=difficulty_mix, stream="baseline",
                        campaign="baseline")

    tx, cu, me, dv = merge_world(legit, customers, merchants, devices, [batch])
    tx = tx.sort_values(["timestamp", "transaction_id"],
                        kind="mergesort").reset_index(drop=True)
    _log(f"features for {len(tx):,} transactions...", quiet)
    feats = build_features(tx, cu, me, dv)
    assert_no_leakage(feats)

    world = World(tx=tx, feats=feats, customers=cu, merchants=me, devices=dv,
                  legit_tx=legit, batch=batch, red_team=rt,
                  config={"scale": scale, "seed": seed, "n_days": n_days,
                          "n_customers": n_customers, "n_merchants": n_merchants,
                          "target_prevalence": target_prevalence,
                          "attack_types": list(attack_types or C.ATTACK_TYPES),
                          "difficulty_mix": difficulty_mix,
                          "build_seconds": round(time.perf_counter() - t0, 2)})
    _log(f"world ready: {len(tx):,} txns, prevalence "
         f"{world.y.mean():.4%}, {time.perf_counter()-t0:.1f}s", quiet)
    return world


# ==========================================================================
def train_baseline(world: World, model_kind: str = "gbdt",
                   target_fpr: float = C.TARGET_FPR_BUDGET,
                   split: Optional[Split] = None,
                   model_params: Optional[Dict] = None,
                   quiet: bool = False) -> Tuple[Detector, Split]:
    """Steps 7-8: Blue Team v1 with an operating point set on validation."""
    split = split or temporal_grouped_split(world.tx)
    _log(f"training {model_kind}: {split.sizes()}", quiet)
    det = train_detector(world.feats, world.tx, split, model_kind=model_kind,
                         target_fpr=target_fpr, model_params=model_params,
                         seed=world.config.get("seed", C.SEED))
    m = det.metrics.get("test", {}).get("overall", {})
    if m:
        _log(f"  test recall={m['recall']:.4f} precision={m['precision']:.4f} "
             f"f1={m['f1']:.4f} fpr={m['fpr']:.5f} auc={m['roc_auc']:.4f}", quiet)
    return det, split


def diagnose(world: World, det: Detector, split: Split,
             on: str = "test") -> Tuple[GapReport, np.ndarray]:
    """Step 9: why did the detector fail?"""
    idx = {"test": split.test, "valid": split.valid, "train": split.train}[on]
    F = world.feats.iloc[idx].reset_index(drop=True)
    tx = world.tx.iloc[idx].reset_index(drop=True)
    p = det.predict_proba(F)
    return analyse_gaps(F, tx, p, det.threshold), p


# ==========================================================================
@dataclass
class LoopResult:
    """Everything needed to report the headline demonstration honestly."""
    gap_before: Dict
    gap_after: Dict
    adaptation_plan: Dict
    before: Dict           # baseline model on held-out adversarial batch
    after: Dict            # retrained model on the SAME held-out batch
    baseline_on_baseline: Dict
    hardened_on_baseline: Dict
    delta: Dict
    search_history: List[Dict] = field(default_factory=list)
    diversity: Dict = field(default_factory=dict)
    meta: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {k: getattr(self, k) for k in
                ("gap_before", "gap_after", "adaptation_plan", "before", "after",
                 "baseline_on_baseline", "hardened_on_baseline", "delta",
                 "search_history", "diversity", "meta")}

    def headline(self) -> str:
        d = self.delta
        return (f"Held-out adversarial recall {self.before['recall']:.4f} -> "
                f"{self.after['recall']:.4f} ({d['recall_delta']:+.4f}) at matched "
                f"FPR budget; baseline-distribution recall "
                f"{self.baseline_on_baseline['recall']:.4f} -> "
                f"{self.hardened_on_baseline['recall']:.4f} "
                f"({d['baseline_recall_delta']:+.4f}).")


def adversarial_loop(
    world: World,
    det: Detector,
    split: Split,
    *,
    n_adversarial: int = 400,
    model_kind: str = "gbdt",
    use_search: bool = True,
    search_rounds: int = 3,
    intensity: float = 0.85,
    quiet: bool = False,
) -> LoopResult:
    """Steps 9-11 + 18: diagnose, adapt, retrain, retest — honestly.

    Returns before/after metrics measured on an adversarial batch that the
    retrained model never saw, plus a regression check on the original
    distribution to prove hardening did not break baseline performance.
    """
    seed = world.config.get("seed", C.SEED)
    t0 = time.perf_counter()

    # ---- 1. diagnose the deployed model -----------------------------------
    gap_before, _ = diagnose(world, det, split, on="test")
    _log(gap_before.headline(), quiet)

    adv_gen = AdversarialGenerator(world.red_team)

    # ---- 2. generate two INDEPENDENT adversarial batches -------------------
    # adv_train goes into training; adv_eval is the honest yardstick.
    history: List[Dict] = []
    if use_search:
        def score_fn(batch: AttackBatch) -> np.ndarray:
            """Score candidate scenarios with the DEPLOYED detector."""
            probe_world = world.rebuild_with([world.batch, batch])
            mask = probe_world.tx["attack_id"].isin(set(batch.scenarios["attack_id"]))
            sub_f = probe_world.feats.loc[mask]
            sub_tx = probe_world.tx.loc[mask]
            if len(sub_tx) == 0:
                return np.ones(len(batch.scenarios))
            p = det.predict_proba(sub_f)
            return scenario_max_score(batch, sub_f, sub_tx, p)

        _log(f"adversarial search ({search_rounds} rounds)...", quiet)
        adv_train, plan, history = adv_gen.search(
            gap_before, n_keep=n_adversarial, score_fn=score_fn,
            rounds=search_rounds, stream="adv_train")
    else:
        adv_train, plan = adv_gen.generate(gap_before, n_adversarial,
                                           intensity=intensity, stream="adv_train")
    # Held-out batch: same generator, same plan, different RNG stream.
    adv_eval, _ = adv_gen.generate(gap_before, n_adversarial, intensity=intensity,
                                   stream="adv_eval_holdout", campaign="adv_eval")
    _log(plan.narrative(), quiet)
    _log(f"adv_train {adv_train.n_scenarios} scenarios / {adv_train.n_events} events; "
         f"adv_eval {adv_eval.n_scenarios} / {adv_eval.n_events} (held out)", quiet)

    # ---- 3. world containing BOTH batches, so features are consistent -----
    w_all = world.rebuild_with([world.batch, adv_train, adv_eval])
    eval_ids = set(adv_eval.scenarios["attack_id"])
    train_ids = set(adv_train.scenarios["attack_id"])
    aid = w_all.tx["attack_id"].to_numpy()
    is_eval = np.isin(aid, list(eval_ids))
    is_advtrain = np.isin(aid, list(train_ids))
    y_all = w_all.y

    # Held-out evaluation set: the unseen adversarial attacks + legitimate
    # traffic from the test window (so precision and FPR stay meaningful).
    base_split = temporal_grouped_split(w_all.tx)
    legit_test = np.zeros(len(w_all.tx), bool)
    legit_test[base_split.test] = True
    legit_test &= (y_all == 0)
    eval_mask = is_eval | legit_test

    # Training split for the hardened model: baseline train window + adv_train,
    # with every held-out adversarial row excluded.
    # Validation includes baseline valid + a held-out fraction of adv_train so
    # that early stopping can detect overfitting to adversarial patterns.
    rng_val = np.random.default_rng(seed + 99)
    adv_indices = np.where(is_advtrain)[0]
    rng_val.shuffle(adv_indices)
    n_adv_val = max(5, int(len(adv_indices) * 0.25))
    adv_val_idx = set(adv_indices[:n_adv_val].tolist())

    train_mask = np.zeros(len(w_all.tx), bool)
    train_mask[base_split.train] = True
    train_mask |= is_advtrain
    train_mask &= ~is_eval
    valid_mask = np.zeros(len(w_all.tx), bool)
    valid_mask[base_split.valid] = True
    valid_mask &= ~is_eval
    for i in adv_val_idx:
        valid_mask[i] = True
    train_mask &= ~valid_mask

    hardened_split = Split(
        train=np.where(train_mask)[0], valid=np.where(valid_mask)[0],
        test=np.where(eval_mask)[0],
        meta={"kind": "adversarial_hardening",
              "n_adv_train_events": int(is_advtrain.sum()),
              "n_adv_eval_events": int(is_eval.sum())})

    # ---- 4. BEFORE: baseline detector on the held-out adversarial batch ----
    F_eval = w_all.feats.iloc[hardened_split.test].reset_index(drop=True)
    tx_eval = w_all.tx.iloc[hardened_split.test].reset_index(drop=True)
    y_eval = tx_eval["fraud_label"].to_numpy().astype(int)
    p_before = det.predict_proba(F_eval)
    # Re-pin the threshold to the SAME FPR budget on this evaluation
    # population, so before/after are compared at matched friction.
    thr_before = choose_threshold_at_fpr(y_eval, p_before, det.target_fpr)
    m_before = compute_metrics(y_eval, p_before, thr_before,
                               amounts=tx_eval["amount"].to_numpy())

    # ---- 5. retrain on baseline + adv_train -------------------------------
    _log("retraining hardened model...", quiet)
    hardened_params: dict = {}
    if model_kind == "gbdt":
        hardened_params = {
            "learning_rate": 0.05,
            "min_samples_leaf": 30,
            "l2": 2.0,
            "early_stopping_rounds": 50,
            "scale_pos_weight": float(getattr(det.model, "scale_pos_weight", 1.0)),
        }
    det2 = train_detector(w_all.feats, w_all.tx, hardened_split,
                          model_kind=model_kind, target_fpr=det.target_fpr,
                          model_params=hardened_params, seed=seed + 17)
    p_after = det2.predict_proba(F_eval)
    thr_after = choose_threshold_at_fpr(y_eval, p_after, det.target_fpr)
    m_after = compute_metrics(y_eval, p_after, thr_after,
                              amounts=tx_eval["amount"].to_numpy())

    # ---- 6. regression check on the ORIGINAL distribution -----------------
    base_only = np.isin(aid, list(set(world.batch.scenarios["attack_id"])))
    reg_mask = (base_only | legit_test)
    reg_mask[hardened_split.train] = False
    reg_mask[hardened_split.valid] = False
    if reg_mask.sum() < 50:
        reg_mask = base_only | legit_test
    F_reg = w_all.feats.iloc[np.where(reg_mask)[0]].reset_index(drop=True)
    tx_reg = w_all.tx.iloc[np.where(reg_mask)[0]].reset_index(drop=True)
    y_reg = tx_reg["fraud_label"].to_numpy().astype(int)
    p1 = det.predict_proba(F_reg)
    p2 = det2.predict_proba(F_reg)
    t1 = choose_threshold_at_fpr(y_reg, p1, det.target_fpr)
    t2 = choose_threshold_at_fpr(y_reg, p2, det.target_fpr)
    m_reg_before = compute_metrics(y_reg, p1, t1)
    m_reg_after = compute_metrics(y_reg, p2, t2)

    # ---- 7. did the diagnosed gap actually close? -------------------------
    gap_after = analyse_gaps(F_eval, tx_eval, p_after, thr_after)

    res = LoopResult(
        gap_before=gap_before.to_dict(),
        gap_after=gap_after.to_dict(),
        adaptation_plan=plan.to_dict(),
        before=m_before.to_dict(),
        after=m_after.to_dict(),
        baseline_on_baseline=m_reg_before.to_dict(),
        hardened_on_baseline=m_reg_after.to_dict(),
        delta={
            "recall_delta": round(m_after.recall - m_before.recall, 4),
            "f1_delta": round(m_after.f1 - m_before.f1, 4),
            "pr_auc_delta": round(m_after.pr_auc - m_before.pr_auc, 4),
            "roc_auc_delta": round(m_after.roc_auc - m_before.roc_auc, 4),
            "fpr_before": m_before.fpr, "fpr_after": m_after.fpr,
            "missed_before": m_before.fn, "missed_after": m_after.fn,
            "baseline_recall_delta": round(m_reg_after.recall - m_reg_before.recall, 4),
            "baseline_f1_delta": round(m_reg_after.f1 - m_reg_before.f1, 4),
        },
        search_history=history,
        diversity=adv_train.diversity_report(),
        meta={
            "n_adversarial_requested": n_adversarial,
            "adv_train_scenarios": adv_train.n_scenarios,
            "adv_eval_scenarios": adv_eval.n_scenarios,
            "adv_train_events": adv_train.n_events,
            "adv_eval_events": adv_eval.n_events,
            "eval_population": {"n": int(len(y_eval)),
                                "n_fraud": int(y_eval.sum()),
                                "n_legit": int((y_eval == 0).sum())},
            "threshold_before": float(thr_before),
            "threshold_after": float(thr_after),
            "target_fpr": det.target_fpr,
            "model_kind": model_kind,
            "used_search": use_search,
            "hardened_split": hardened_split.sizes(),
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
            "methodology": ("Before and after are evaluated on the SAME adversarial "
                            "batch, generated independently of the batch used for "
                            "retraining, at a matched false-positive budget."),
        },
    )
    _log(res.headline(), quiet)
    return res, det2, w_all


# ==========================================================================
def save_world(world: World, directory: Optional[Path] = None) -> Dict[str, str]:
    """Write the dataset in the layout described in the plan (Phase 26)."""
    directory = Path(directory or C.DATA_DIR)
    syn = directory / "synthetic"; syn.mkdir(parents=True, exist_ok=True)
    atk = directory / "attacks"; atk.mkdir(parents=True, exist_ok=True)
    ev = directory / "evaluation"; ev.mkdir(parents=True, exist_ok=True)

    paths: Dict[str, str] = {}
    world.customers.to_csv(syn / "customers.csv", index=False)
    world.merchants.to_csv(syn / "merchants.csv", index=False)
    world.devices.to_csv(syn / "devices.csv", index=False)
    world.tx.to_csv(syn / "transactions.csv", index=False)
    world.feats.to_parquet(syn / "features.parquet") if _has_parquet() else \
        world.feats.to_csv(syn / "features.csv.gz", index=False, compression="gzip")
    for name, p in (("customers", syn / "customers.csv"),
                    ("merchants", syn / "merchants.csv"),
                    ("devices", syn / "devices.csv"),
                    ("transactions", syn / "transactions.csv")):
        paths[name] = str(p)

    if not world.batch.events.empty:
        for atype, sub in world.batch.events.groupby("attack_type"):
            f = atk / f"{atype.lower()}.csv"
            sub.to_csv(f, index=False)
            paths[f"attack_{atype}"] = str(f)
        world.batch.scenarios.to_csv(atk / "scenarios.csv", index=False)
        paths["scenarios"] = str(atk / "scenarios.csv")

    (ev / "world_summary.json").write_text(json.dumps(world.summary(), indent=2, default=str))
    paths["summary"] = str(ev / "world_summary.json")
    return paths


def _has_parquet() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:
        try:
            import fastparquet  # noqa: F401
            return True
        except Exception:
            return False
