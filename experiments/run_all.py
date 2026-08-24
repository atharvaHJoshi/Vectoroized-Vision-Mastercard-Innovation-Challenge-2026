"""
The six measured experiments (Phase 25).

Run with:   python sg.py experiments [--scale tiny|demo] [--quick]

Every experiment writes a JSON artefact into experiments/results/ containing the
raw numbers, the configuration that produced them, and enough metadata to
reproduce the run. The README quotes these files rather than restating numbers
by hand, so the documentation cannot drift from the measurements.

  1  Baseline                 precision / recall / F1 / AUC / PR-AUC / FPR
  2  Attack diversity         does performance hold as the attack mix widens?
  3  Unseen attacks           train on some families, test on families never seen
  4  Adversarial attacks      normal synthetic fraud vs. gap-directed fraud
  5  Adaptive training        before vs. after hardening, matched FPR
  6  False positives          what the FPR budget actually costs in friction

All comparisons are made at a MATCHED false-positive budget. Comparing a recall
number at one threshold against a recall number at another is meaningless, and
that is the single easiest way to accidentally overstate a result.
"""
from __future__ import annotations

import json
import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sovereignguard import config as C                       # noqa: E402
from sovereignguard.detection import (Detector, optional_backends,  # noqa: E402
                                      temporal_grouped_split, train_detector,
                                      unseen_attack_split)
from sovereignguard.evaluation.gap_analysis import analyse_gaps  # noqa: E402
from sovereignguard.evaluation.metrics import (bootstrap_ci,     # noqa: E402
                                               choose_threshold_at_fpr,
                                               compute_metrics, operating_curve)
from sovereignguard.pipeline import (adversarial_loop, build_world,  # noqa: E402
                                     diagnose, train_baseline)

RESULTS = C.EXPERIMENTS_DIR
RESULTS.mkdir(parents=True, exist_ok=True)


def _env() -> Dict:
    import pandas as pd
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "ml_backend": "builtin-numpy (histogram GBDT / RF / TreeSHAP)",
        "optional_backends": optional_backends(),
    }


def _save(name: str, payload: Dict) -> Path:
    payload["_meta"] = {**payload.get("_meta", {}), "environment": _env(),
                        "written_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    p = RESULTS / f"{name}.json"
    p.write_text(json.dumps(payload, indent=2, default=str))
    print(f"    -> {p.relative_to(ROOT)}")
    return p


def _hdr(n: int, title: str) -> None:
    print(f"\n{'='*74}\nEXPERIMENT {n} — {title}\n{'='*74}")


def _m(det: Detector, feats, tx, idx) -> Dict:
    y = tx["fraud_label"].to_numpy()[idx]
    p = det.predict_proba(feats.iloc[idx])
    thr = choose_threshold_at_fpr(y, p, det.target_fpr)
    return compute_metrics(y, p, thr, amounts=tx["amount"].to_numpy()[idx]).to_dict()


# ==========================================================================
def exp1_baseline(scale: str, seed: int, prevalences=(0.010, 0.050)) -> Dict:
    """Headline baseline at two fraud prevalences, both models."""
    _hdr(1, "Baseline detection performance")
    out: Dict = {"runs": [], "_meta": {"scale": scale, "seed": seed,
                                       "prevalences": list(prevalences)}}
    for prev in prevalences:
        w = build_world(scale, seed, target_prevalence=prev, quiet=True)
        sp = temporal_grouped_split(w.tx)
        for kind in ("gbdt", "forest"):
            det, _ = train_baseline(w, kind, split=sp, quiet=True)
            m = det.metrics["test"]["overall"]
            ci = bootstrap_ci(w.tx["fraud_label"].to_numpy()[sp.test],
                              det.predict_proba(w.feats.iloc[sp.test]),
                              det.threshold, "recall", n_boot=120, seed=seed)
            row = {
                "prevalence_target": prev,
                "prevalence_actual": round(float(w.y.mean()), 5),
                "model": kind,
                "n_transactions": int(len(w.tx)),
                "n_test": int(len(sp.test)),
                "threshold": det.threshold,
                "metrics": m,
                "recall_ci95": ci,
                "by_difficulty": det.metrics["test"]["by_difficulty"],
                "by_attack_type": det.metrics["test"]["by_attack_type"],
                "top_features": det.metrics["top_features"][:10],
                "fit_seconds": det.train_meta["fit_seconds"],
            }
            out["runs"].append(row)
            print(f"  prevalence {prev:.1%}  {kind:6s}  recall={m['recall']:.4f} "
                  f"prec={m['precision']:.4f} f1={m['f1']:.4f} "
                  f"auc={m['roc_auc']:.4f} pr_auc={m['pr_auc']:.4f} "
                  f"fpr={m['fpr']:.5f}")
    return out


# ==========================================================================
def exp2_diversity(scale: str, seed: int, prevalence=0.010) -> Dict:
    """Does the defence hold up as the attack mix widens from 1 to 7 families?

    Reading this correctly matters: recall usually FALLS as families are added,
    because the problem genuinely gets harder — the model must cover more
    distinct behaviours from a fixed budget of positives. A rising number here
    would be the suspicious result.
    """
    _hdr(2, "Attack diversity — 1, 3, 5, 7 families")
    subsets = [
        ["ACCOUNT_TAKEOVER"],
        ["ACCOUNT_TAKEOVER", "TRANSACTION_MANIPULATION", "PHISHING_PAYMENT_LINK"],
        ["ACCOUNT_TAKEOVER", "TRANSACTION_MANIPULATION", "PHISHING_PAYMENT_LINK",
         "SOCIAL_ENGINEERING", "MERCHANT_FRAUD"],
        list(C.ATTACK_TYPES),
    ]
    out: Dict = {"rows": [], "_meta": {"scale": scale, "seed": seed,
                                       "prevalence": prevalence}}
    for types in subsets:
        w = build_world(scale, seed, target_prevalence=prevalence,
                        attack_types=types, quiet=True)
        det, sp = train_baseline(w, "gbdt", quiet=True)
        m = det.metrics["test"]["overall"]
        div = w.batch.diversity_report()
        row = {"n_families": len(types), "families": types,
               "metrics": m,
               "entropy_attack_type": div.get("entropy_attack_type"),
               "distinct_stages": div.get("distinct_stages"),
               "n_attack_scenarios": div.get("n_scenarios"),
               "by_difficulty": det.metrics["test"]["by_difficulty"]}
        out["rows"].append(row)
        print(f"  {len(types)} families  recall={m['recall']:.4f} "
              f"prec={m['precision']:.4f} f1={m['f1']:.4f} auc={m['roc_auc']:.4f}")
    return out


# ==========================================================================
def exp3_unseen(scale: str, seed: int, prevalence=0.012) -> Dict:
    """Train on some attack families, test on families never seen.

    This is the experiment that speaks to the actual challenge: the future fraud
    pattern is not in the training data. Anything above chance here is genuine
    transfer — the model recognising *anomaly structure* rather than memorised
    attack signatures.
    """
    _hdr(3, "Unseen attack families — generalisation")
    holdouts = [
        ["SOCIAL_ENGINEERING", "MULTI_STAGE"],
        ["SYNTHETIC_IDENTITY", "MERCHANT_FRAUD"],
        ["TRANSACTION_MANIPULATION"],
    ]
    w = build_world(scale, seed, target_prevalence=prevalence, quiet=True)
    out: Dict = {"rows": [], "_meta": {"scale": scale, "seed": seed,
                                       "prevalence": prevalence}}
    for hold in holdouts:
        sp = unseen_attack_split(w.tx, hold)
        if len(sp.train) == 0 or len(sp.test) == 0:
            continue
        y_tr = w.tx["fraud_label"].to_numpy()[sp.train]
        if y_tr.sum() < 10:
            print(f"  skipping {hold}: too few training positives")
            continue
        det = train_detector(w.feats, w.tx, sp, "gbdt", seed=seed)

        # Evaluate only on the held-out families + legitimate traffic.
        atype = w.tx["attack_type"].to_numpy()
        y = w.tx["fraud_label"].to_numpy()
        te = sp.test
        held_mask = np.isin(atype[te], hold) & (y[te] == 1)
        legit_mask = y[te] == 0
        sel = te[held_mask | legit_mask]
        m = _m(det, w.feats, w.tx, sel)

        # Contrast with the SEEN families in the same window, same threshold.
        seen_mask = (~np.isin(atype[te], hold)) & (y[te] == 1)
        sel_seen = te[seen_mask | legit_mask]
        m_seen = _m(det, w.feats, w.tx, sel_seen) if seen_mask.sum() > 5 else None

        row = {"holdout_families": hold,
               "n_train": int(len(sp.train)), "n_train_fraud": int(y_tr.sum()),
               "unseen": m, "seen_reference": m_seen,
               "recall_retention": (round(m["recall"] / m_seen["recall"], 4)
                                    if m_seen and m_seen["recall"] else None)}
        out["rows"].append(row)
        print(f"  holdout {hold}")
        print(f"    UNSEEN  recall={m['recall']:.4f} prec={m['precision']:.4f} "
              f"auc={m['roc_auc']:.4f}  (n_fraud={m['n_positive']})")
        if m_seen:
            print(f"    SEEN    recall={m_seen['recall']:.4f} "
                  f"auc={m_seen['roc_auc']:.4f}   -> retention "
                  f"{row['recall_retention']}")
    return out


# ==========================================================================
def exp4_adversarial(scale: str, seed: int, prevalence=0.012,
                     n_adv=250) -> Dict:
    """Ordinary synthetic fraud vs. gap-directed adversarial fraud.

    Same detector, same threshold, two attack populations. The recall gap
    between them is the measure of how much a static benchmark overstates a
    defence's real durability.
    """
    _hdr(4, "Adversarial attacks vs. ordinary synthetic fraud")
    from sovereignguard.generators.adversarial import AdversarialGenerator

    w = build_world(scale, seed, target_prevalence=prevalence, quiet=True)
    det, sp = train_baseline(w, "gbdt", quiet=True)
    gap, _ = diagnose(w, det, sp)

    # Baseline attacks in the test window.
    y = w.tx["fraud_label"].to_numpy()
    base_metrics = _m(det, w.feats, w.tx, sp.test)

    # Gap-directed adversarial batch, spliced into the same world.
    adv_gen = AdversarialGenerator(w.red_team)
    adv, plan = adv_gen.generate(gap, n_adv, stream="exp4")
    w2 = w.rebuild_with([w.batch, adv])
    aid = w2.tx["attack_id"].to_numpy()
    adv_ids = set(adv.scenarios["attack_id"])
    is_adv = np.isin(aid, list(adv_ids))
    y2 = w2.tx["fraud_label"].to_numpy()
    sp2 = temporal_grouped_split(w2.tx)
    legit_test = np.zeros(len(w2.tx), bool)
    legit_test[sp2.test] = True
    legit_test &= (y2 == 0)
    sel = np.where(is_adv | legit_test)[0]
    adv_metrics = _m(det, w2.feats, w2.tx, sel)

    out = {
        "baseline_attacks": base_metrics,
        "adversarial_attacks": adv_metrics,
        "recall_drop": round(base_metrics["recall"] - adv_metrics["recall"], 4),
        "adaptation_plan": plan.to_dict(),
        "adversarial_diversity": adv.diversity_report(),
        "gap_before": gap.to_dict(),
        "_meta": {"scale": scale, "seed": seed, "prevalence": prevalence,
                  "n_adversarial": n_adv, "threshold_policy":
                  "re-pinned to the same FPR budget on each population"},
    }
    print(f"  ordinary synthetic fraud : recall={base_metrics['recall']:.4f} "
          f"prec={base_metrics['precision']:.4f}")
    print(f"  gap-directed adversarial : recall={adv_metrics['recall']:.4f} "
          f"prec={adv_metrics['precision']:.4f}")
    print(f"  RECALL DROP              : {out['recall_drop']:+.4f}  "
          f"<- how much a static benchmark overstates durability")
    return out


# ==========================================================================
def exp5_adaptive(scale: str, seed: int, prevalence=0.012, n_adv=250,
                  rounds=2) -> Dict:
    """The headline: before vs. after adversarial hardening.

    Measured on an adversarial batch generated independently of the one used for
    retraining, at a matched false-positive budget, with a regression check on
    the original distribution.
    """
    _hdr(5, "Adaptive training — before vs. after hardening")
    w = build_world(scale, seed, target_prevalence=prevalence, quiet=True)
    det, sp = train_baseline(w, "gbdt", quiet=True)
    res, _det2, _w2 = adversarial_loop(w, det, sp, n_adversarial=n_adv,
                                       use_search=True, search_rounds=rounds,
                                       quiet=True)
    d = res.delta
    print(f"  held-out adversarial recall  {res.before['recall']:.4f} -> "
          f"{res.after['recall']:.4f}  ({d['recall_delta']:+.4f})")
    print(f"  held-out adversarial F1      {res.before['f1']:.4f} -> "
          f"{res.after['f1']:.4f}  ({d['f1_delta']:+.4f})")
    print(f"  attacks missed               {d['missed_before']} -> {d['missed_after']}")
    print(f"  FPR (matched)                {d['fpr_before']:.5f} / {d['fpr_after']:.5f}")
    print(f"  regression on baseline dist. {res.baseline_on_baseline['recall']:.4f} -> "
          f"{res.hardened_on_baseline['recall']:.4f} "
          f"({d['baseline_recall_delta']:+.4f})")
    payload = res.to_dict()
    payload["_meta"] = {"scale": scale, "seed": seed, "prevalence": prevalence,
                        "n_adversarial": n_adv, "search_rounds": rounds}
    return payload


# ==========================================================================
def exp6_false_positives(scale: str, seed: int, prevalence=0.010) -> Dict:
    """What the false-positive budget actually costs.

    A fraud system that blocks honest customers destroys more value than it
    saves, so this reports the trade-off in operational units — alerts per
    thousand good transactions, and the share of honest traffic challenged —
    rather than as an abstract rate.
    """
    _hdr(6, "False positives and customer friction")
    w = build_world(scale, seed, target_prevalence=prevalence, quiet=True)
    sp = temporal_grouped_split(w.tx)
    y = w.tx["fraud_label"].to_numpy()
    rows = []
    for budget in (0.001, 0.002, 0.005, 0.010, 0.020, 0.050):
        det = train_detector(w.feats, w.tx, sp, "gbdt", target_fpr=budget, seed=seed)
        p = det.predict_proba(w.feats.iloc[sp.test])
        yt = y[sp.test]
        m = compute_metrics(yt, p, det.threshold,
                            amounts=w.tx["amount"].to_numpy()[sp.test])
        fr = det.risk.friction_summary(p, yt)
        rows.append({"fpr_budget": budget, "threshold": det.threshold,
                     "metrics": m.to_dict(), "friction": fr})
        print(f"  budget {budget:.1%}  realised_fpr={m.fpr:.5f} "
              f"recall={m.recall:.4f} prec={m.precision:.4f} "
              f"alerts/1k_legit={m.alerts_per_1k_legit:.2f} "
              f"legit_challenged={fr.get('legit_challenged_share', 0):.4f}")

    # Also: per-persona false-positive rate — is any customer group over-flagged?
    det = train_detector(w.feats, w.tx, sp, "gbdt", seed=seed)
    p = det.predict_proba(w.feats.iloc[sp.test])
    yt = y[sp.test]
    cust = w.tx["customer_id"].to_numpy()[sp.test]
    persona_map = dict(zip(w.customers["customer_id"], w.customers["persona"]))
    persona = np.array([persona_map.get(c, "?") for c in cust])
    flagged = p >= det.threshold
    per_persona = []
    for pn in sorted(set(persona.tolist())):
        mask = (persona == pn) & (yt == 0)
        if mask.sum() < 20:
            continue
        per_persona.append({"persona": pn, "n_legit": int(mask.sum()),
                            "fpr": round(float(flagged[mask].mean()), 5)})
    per_persona.sort(key=lambda r: -r["fpr"])
    print("\n  false-positive rate by customer persona (fairness check):")
    for r in per_persona:
        print(f"    {r['persona']:20s} n={r['n_legit']:6d}  fpr={r['fpr']:.5f}")
    return {"budget_sweep": rows, "fpr_by_persona": per_persona,
            "_meta": {"scale": scale, "seed": seed, "prevalence": prevalence}}


# ==========================================================================
def run_all(scale: str = "tiny", seed: int = C.SEED, quick: bool = False,
            only: Optional[List[str]] = None) -> Dict:
    """Run the suite. `only` restricts to named experiments (1..6 or names),
    which lets each one be run in a separate short-lived process."""
    t0 = time.time()
    n_adv = 120 if quick else 250
    rounds = 1 if quick else 2
    prevs = (0.010,) if quick else (0.010, 0.050)

    print("=" * 74)
    print("SOVEREIGNGUARD — EXPERIMENT SUITE")
    print(f"scale={scale} seed={seed} quick={quick}")
    print("All comparisons at a MATCHED false-positive budget.")
    print("=" * 74)

    index: Dict[str, Dict] = {}
    steps = [
        ("exp1_baseline", lambda: exp1_baseline(scale, seed, prevs)),
        ("exp2_attack_diversity", lambda: exp2_diversity(scale, seed)),
        ("exp3_unseen_attacks", lambda: exp3_unseen(scale, seed)),
        ("exp4_adversarial", lambda: exp4_adversarial(scale, seed, n_adv=n_adv)),
        ("exp5_adaptive_training",
         lambda: exp5_adaptive(scale, seed, n_adv=n_adv, rounds=rounds)),
        ("exp6_false_positives", lambda: exp6_false_positives(scale, seed)),
    ]
    if only:
        keep = {str(o).lower() for o in only}
        steps = [(n, f) for i, (n, f) in enumerate(steps, 1)
                 if str(i) in keep or n.lower() in keep
                 or n.lower().lstrip("exp").split("_")[0] in keep]
        if not steps:
            raise SystemExit(f"no experiments matched {only!r}")

    for name, fn in steps:
        try:
            t = time.time()
            payload = fn()
            payload["_meta"] = {**payload.get("_meta", {}),
                                "elapsed_seconds": round(time.time() - t, 1)}
            _save(name, payload)
            index[name] = {"status": "complete",
                           "elapsed_seconds": round(time.time() - t, 1)}
        except Exception as exc:                              # keep going
            import traceback
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=3)
            index[name] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    # Merge into any existing index so partial runs accumulate.
    idx_path = RESULTS / "index.json"
    prior = {}
    if idx_path.exists():
        try:
            prior = json.loads(idx_path.read_text()).get("experiments", {})
        except Exception:
            prior = {}
    summary = {"experiments": {**prior, **index}, "scale": scale, "seed": seed,
               "quick": quick, "total_seconds": round(time.time() - t0, 1)}
    _save("index", summary)
    print(f"\n{'='*74}\nDONE in {summary['total_seconds']:.0f}s")
    for k, v in index.items():
        print(f"  {v['status']:9s} {k}")
    print("=" * 74)
    return summary


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="SovereignGuard experiment suite")
    ap.add_argument("--scale", default="tiny", choices=sorted(C.SCALES))
    ap.add_argument("--seed", type=int, default=C.SEED)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", nargs="*",
                    help="run only these experiments, e.g. --only 3 4")
    a = ap.parse_args()
    run_all(a.scale, a.seed, a.quick, a.only)
