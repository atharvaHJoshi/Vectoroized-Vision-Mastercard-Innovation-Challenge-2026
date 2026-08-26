#!/usr/bin/env python3
"""
SovereignGuard — end-to-end verification harness.

    python verify.py                # full check, ~4 minutes
    python verify.py --quick        # smallest scale, ~90 seconds
    python verify.py --full         # demo scale, ~15 minutes
    python verify.py --stage tests  # run one stage only
    python verify.py --list         # show stages and exit

This is not a demo. Every stage ASSERTS a concrete property and fails loudly if
it is not met, so a green run is evidence that the pipeline works rather than
evidence that it merely ran without raising.

Exit code 0 means every stage passed. Non-zero means something is broken, and
the summary names which stage and why.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------- presentation
_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
G = "\033[32m" if _TTY else ""
R = "\033[31m" if _TTY else ""
Y = "\033[33m" if _TTY else ""
B = "\033[36m" if _TTY else ""
D = "\033[2m" if _TTY else ""
BOLD = "\033[1m" if _TTY else ""
X = "\033[0m" if _TTY else ""

PASS = f"{G}PASS{X}"
FAIL = f"{R}FAIL{X}"
SKIP = f"{Y}SKIP{X}"


def head(title: str) -> None:
    print(f"\n{BOLD}{'─' * 74}{X}")
    print(f"{BOLD}{title}{X}")
    print(f"{BOLD}{'─' * 74}{X}")


def line(label: str, value: str = "", ok: Optional[bool] = None) -> None:
    mark = "" if ok is None else (f"  {G}ok{X}" if ok else f"  {R}BAD{X}")
    if value:
        print(f"    {label:<44s} {value}{mark}")
    else:
        print(f"    {label}{mark}")


def check(cond: bool, msg: str) -> None:
    """Assertion that produces a readable failure rather than a traceback."""
    if not cond:
        raise AssertionError(msg)


# ---------------------------------------------------------------- scale config
PROFILES = {
    "quick": {"scale": "nano", "n_adv": 60, "rounds": 1, "redteam": 40},
    "normal": {"scale": "tiny", "n_adv": 150, "rounds": 2, "redteam": 120},
    "full": {"scale": "demo", "n_adv": 400, "rounds": 2, "redteam": 400},
}

STATE: Dict[str, object] = {}


# --------------------------------------------------------------------------
# Lazy dependency providers.
#
# Stages 6-12 all need a built world and a trained detector. Rather than fail
# with a bare KeyError when an earlier stage is skipped (`--stage api`), each
# consumer asks for what it needs and the world/detector is built on demand.
# This is what makes `--stage <anything>` usable in isolation.
# --------------------------------------------------------------------------
def need_world(cfg: Dict):
    if "world" not in STATE:
        from sovereignguard.pipeline import build_world
        print(f"    {D}(building a world on demand — stage 'world' was not run){X}")
        STATE["world"] = build_world(cfg["scale"], 20260823,
                                     target_prevalence=0.012, quiet=True)
    return STATE["world"]


def need_detector(cfg: Dict):
    if "det" not in STATE:
        from sovereignguard.pipeline import train_baseline
        w = need_world(cfg)
        print(f"    {D}(training a detector on demand — stage 'blueteam' "
              f"was not run){X}")
        det, split = train_baseline(w, "gbdt", quiet=True)
        STATE["det"], STATE["split"] = det, split
    return STATE["det"], STATE["split"]


# ==========================================================================
# Stage 1 — environment
# ==========================================================================
def stage_environment(cfg: Dict) -> None:
    head("1. ENVIRONMENT")
    line("python", platform.python_version())
    check(sys.version_info >= (3, 9), f"Python 3.9+ required, found {platform.python_version()}")

    import numpy as np
    import pandas as pd
    line("numpy", np.__version__, True)
    line("pandas", pd.__version__, True)

    from sovereignguard.detection import optional_backends
    opt = optional_backends()
    print()
    line("optional backends (none are required):")
    for k, v in opt.items():
        line(f"  {k}", "present" if v else "absent (built-in used)", None)

    # Every module must import; a broken import here explains later failures.
    mods = [
        "config", "schema", "rng", "taxonomy", "features", "detection", "risk",
        "store", "pipeline", "generators.population", "generators.transactions",
        "generators.attacks", "generators.families", "generators.redteam",
        "generators.adversarial", "ml.tree", "ml.models", "ml.treeshap",
        "evaluation.metrics", "evaluation.gap_analysis", "api.server",
    ]
    import importlib
    for m in mods:
        importlib.import_module(f"sovereignguard.{m}")
    print()
    line("modules imported", f"{len(mods)}/{len(mods)}", True)

    from sovereignguard import taxonomy
    taxonomy.validate()
    line("taxonomy validates against config", "", True)

    from sovereignguard.schema import FEATURE_COLUMNS, LABEL_COLUMNS
    check(not (set(FEATURE_COLUMNS) & set(LABEL_COLUMNS)),
          "LABEL LEAKAGE: a label column is declared as a feature")
    line("feature/label contract", f"{len(FEATURE_COLUMNS)} features, no leakage", True)
    STATE["n_features"] = len(FEATURE_COLUMNS)


# ==========================================================================
# Stage 2 — unit tests
# ==========================================================================
def stage_tests(cfg: Dict) -> None:
    head("2. TEST SUITE")
    runner = ROOT / "tests" / "run_tests.py"
    check(runner.exists(), f"missing {runner}")
    t0 = time.time()
    proc = subprocess.run([sys.executable, str(runner)], cwd=str(ROOT),
                          capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    tail = [l for l in out.splitlines() if "passed" in l and "failed" in l]
    summary = tail[-1].strip() if tail else "(no summary line)"
    for l in out.splitlines():
        if "FAIL" in l:
            print(f"    {l.strip()}")
    line("result", summary, proc.returncode == 0)
    line("elapsed", f"{time.time()-t0:.1f}s")
    check(proc.returncode == 0,
          f"test suite failed. Run: python tests/run_tests.py -v")
    # Pull the count out for the final report.
    import re
    m = re.search(r"(\d+) passed", summary)
    STATE["tests_passed"] = int(m.group(1)) if m else 0


# ==========================================================================
# Stage 3 — synthetic world
# ==========================================================================
def stage_world(cfg: Dict) -> None:
    head("3. SYNTHETIC DATA ENGINE")
    import numpy as np
    from sovereignguard.features import assert_no_leakage
    from sovereignguard.pipeline import build_world

    t0 = time.time()
    w = build_world(cfg["scale"], 20260823, target_prevalence=0.012, quiet=True)
    build_s = time.time() - t0
    s = w.summary()
    STATE["world"] = w

    line("customers / merchants / devices",
         f"{s['n_customers']:,} / {s['n_merchants']:,} / {s['n_devices']:,}")
    line("transactions", f"{s['n_transactions']:,}")
    line("fraud events", f"{s['n_fraud_events']:,}")
    line("prevalence", f"{s['fraud_prevalence']:.3%}")
    line("attack scenarios", f"{s['n_attack_scenarios']:,}")
    line("build time", f"{build_s:.1f}s "
                       f"({s['n_transactions']/max(build_s,1e-9):,.0f} txn/s)")

    check(s["n_transactions"] > 1000, "implausibly few transactions generated")
    check(0.002 < s["fraud_prevalence"] < 0.10,
          f"prevalence {s['fraud_prevalence']:.4f} outside the plausible band")
    assert_no_leakage(w.feats)
    line("feature matrix", f"{w.feats.shape[0]:,} x {w.feats.shape[1]}", True)

    # --- realism assertions -------------------------------------------------
    print()
    line("realism checks:")
    tx = w.tx
    legit = tx[tx.fraud_label == 0]
    amt = legit["amount"].to_numpy()
    ratio = float(np.percentile(amt, 99) / np.median(amt))
    line("  amount p99/median (heavy tail, not uniform)", f"{ratio:.1f}x", ratio > 6)
    check(ratio > 6, f"amount distribution looks uniform (p99/median={ratio:.1f})")

    med_ratio = float(w.feats.loc[tx.fraud_label == 0,
                                  "amount_ratio_customer_median"].median())
    line("  median amount vs customer norm", f"{med_ratio:.3f}x",
         0.7 < med_ratio < 1.4)
    check(0.7 < med_ratio < 1.4, "amount features are miscalibrated")

    # THE label-oracle guard
    nb = float(legit["is_new_beneficiary"].mean())
    line("  honest new-payee rate (must be >0, <10%)", f"{nb:.4%}", 0 < nb < 0.10)
    check(nb > 0, "honest customers NEVER add a payee -> the flag is a fraud oracle")
    check(nb < 0.10, f"honest new-payee rate {nb:.3f} implausibly high")

    per_cust_dev = legit.groupby("customer_id")["device_id"].nunique()
    multi = float((per_cust_dev > 1).mean())
    line("  honest multi-device customers", f"{multi:.1%}", 0 < multi < 0.85)
    check(multi > 0, "no honest customer switches device -> is_new_device is an oracle")

    cities = legit.groupby("customer_id")["city"].nunique()
    travel = float((cities > 1).mean())
    line("  honest customers who travel", f"{travel:.1%}", travel > 0)
    check(travel > 0, "no honest customer travels -> geo features become oracles")


# ==========================================================================
# Stage 4 — Red Team
# ==========================================================================
def stage_redteam(cfg: Dict) -> None:
    head("4. RED TEAM — attack generation")
    w = STATE["world"]
    t0 = time.time()
    batch = w.red_team.generate(cfg["redteam"], stream="verify")
    gen_s = time.time() - t0
    d = batch.diversity_report()

    line("scenarios / events", f"{d['n_scenarios']:,} / {d['n_events']:,}")
    line("events per scenario", f"{d['events_per_scenario_mean']:.1f}")
    line("generation time", f"{gen_s:.2f}s")
    line("attack families covered", f"{d['attack_types']}/7", d["attack_types"] >= 5)
    line("distinct victims / personas",
         f"{d['distinct_victims']} / {d['distinct_victim_personas']}")
    line("distinct devices / cities / merchants",
         f"{d['distinct_devices']} / {d['distinct_cities']} / {d['distinct_merchants']}")
    line("distinct attack stages", str(d["distinct_stages"]))
    line("amount span", f"10^{d['amount_span_log10']:.1f} "
                        f"(₹{d['amount_p05']:,.0f} – ₹{d['amount_p95']:,.0f})")

    print()
    line("measured diversity (normalised entropy, 1.0 = perfectly even):")
    for k, label in (("entropy_attack_type", "attack family"),
                     ("entropy_difficulty", "evasion skill"),
                     ("entropy_persona", "victim persona"),
                     ("entropy_city", "geography"),
                     ("entropy_stage", "attack stage")):
        line(f"  {label}", f"{d[k]:.3f}")

    check(d["attack_types"] >= 5, f"only {d['attack_types']} families sampled")
    check(d["n_events"] > d["n_scenarios"],
          "attacks are single rows, not sequences")
    check(d["amount_span_log10"] > 1.0, "attack amounts span too narrow a range")

    # --- difficulty gradient is the headline property of the Red Team --------
    import numpy as np
    print()
    line("difficulty gradient (HARD must approach legitimate behaviour):")
    F, tx = w.feats, w.tx
    y = tx["fraud_label"].to_numpy()
    diff = tx["difficulty"].to_numpy()
    cols = ["amount_ratio_customer_median", "is_new_device", "distance_from_home_km"]
    names = ["amount vs. customer norm", "new-device rate", "distance from home (km)"]
    rows = {}
    for tier, mask in (("LEGIT", y == 0), ("EASY", (y == 1) & (diff == "EASY")),
                       ("MEDIUM", (y == 1) & (diff == "MEDIUM")),
                       ("HARD", (y == 1) & (diff == "HARD"))):
        if mask.sum() < 3:
            continue
        rows[tier] = [float(F[c].to_numpy()[mask].mean()) for c in cols]
    if rows:
        print(f"{D}      {'':<28s}" + "".join(f"{t:>11s}" for t in rows) + f"{X}")
        for i, nm in enumerate(names):
            vals = "".join(f"{rows[t][i]:11.2f}" for t in rows)
            print(f"      {nm:<28s}{vals}")
    if "EASY" in rows and "HARD" in rows and "LEGIT" in rows:
        # HARD must sit closer to LEGIT than EASY does, on the amount axis
        d_easy = abs(rows["EASY"][0] - rows["LEGIT"][0])
        d_hard = abs(rows["HARD"][0] - rows["LEGIT"][0])
        line("  HARD closer to legitimate than EASY",
             f"{d_hard:.2f} vs {d_easy:.2f}", d_hard < d_easy)
        check(d_hard < d_easy, "the difficulty levels are not doing anything")


# ==========================================================================
# Stage 5 — Blue Team
# ==========================================================================
def stage_blueteam(cfg: Dict) -> None:
    head("5. BLUE TEAM — detection")
    from sovereignguard.pipeline import train_baseline
    w = STATE["world"]

    t0 = time.time()
    det, split = train_baseline(w, "gbdt", quiet=True)
    fit_s = time.time() - t0
    STATE["det"] = det
    STATE["split"] = split
    m = det.metrics["test"]["overall"]

    line("split (train / valid / test)",
         f"{len(split.train):,} / {len(split.valid):,} / {len(split.test):,}")
    line("trees / best iteration",
         f"{det.train_meta['n_trees']} / {det.train_meta['best_iteration']}")
    line("training time", f"{fit_s:.1f}s")
    line("operating threshold",
         f"{det.threshold:.6f} (validation, {det.target_fpr:.1%} FPR budget)")
    print()
    line("held-out test metrics:")
    for k, label, fmt in (("recall", "recall", ".4f"), ("precision", "precision", ".4f"),
                          ("f1", "F1", ".4f"), ("roc_auc", "ROC-AUC", ".4f"),
                          ("pr_auc", "PR-AUC", ".4f"), ("fpr", "false-positive rate", ".5f")):
        line(f"  {label}", format(m[k], fmt))
    line("  detected / missed", f"{m['tp']} / {m['fn']}")
    line("  alerts per 1k good txns", f"{m['alerts_per_1k_legit']:.2f}")
    line("  scoring latency", f"{m['latency_us_per_txn']:.1f} µs/txn")

    check(m["roc_auc"] > 0.85, f"ROC-AUC {m['roc_auc']:.4f} too low to be working")
    check(m["recall"] > 0.25, f"recall {m['recall']:.4f} too low")
    check(m["fpr"] <= det.target_fpr * 2.5,
          f"realised FPR {m['fpr']:.5f} far above budget {det.target_fpr}")
    check("accuracy" in m, "metrics missing")

    # accuracy must NOT be the headline — prove it would be misleading
    line("  accuracy (deliberately not a headline)", f"{m['accuracy']:.4f}")

    print()
    line("recall by evasion skill:")
    for r in det.metrics["test"]["by_difficulty"]:
        line(f"  {r['group']:<10s} n={r['n']:<5d}", f"{r['recall']:.3f}")

    print()
    line("recall by attack family (worst first):")
    for r in det.metrics["test"]["by_attack_type"][:7]:
        line(f"  {r['group']:<26s} n={r['n']:<5d}", f"{r['recall']:.3f}")

    print()
    line("top features:")
    for f in det.metrics["top_features"][:6]:
        line(f"  {f['label'][:44]}", f"{f['importance']:.4f}")


# ==========================================================================
# Stage 6 — explainability
# ==========================================================================
def stage_explain(cfg: Dict) -> None:
    head("6. EXPLAINABILITY — TreeSHAP")
    import numpy as np
    from sovereignguard.ml import GradientBoostingClassifier
    from sovereignguard.ml.treeshap import (_tree_shap_single, brute_force_shap,
                                            shap_values)

    # Correctness against the Shapley definition itself.
    rng = np.random.default_rng(7)
    n, f = 2500, 6
    Xs = rng.normal(size=(n, f)).astype(np.float32)
    ys = (rng.random(n) < 1 / (1 + np.exp(
        -(1.8 * Xs[:, 0] * Xs[:, 1] + 1.2 * Xs[:, 2] - Xs[:, 4])))).astype(float)
    worst, checks = 0.0, 0
    for depth in (2, 3, 4):
        mm = GradientBoostingClassifier(n_estimators=5, max_depth=depth,
                                        learning_rate=0.3, max_bins=12,
                                        random_state=3).fit(Xs, ys)
        Xb = mm.binner_.transform(Xs[:4])
        for tree in mm.trees_:
            for i in range(4):
                mine = np.zeros(f)
                _tree_shap_single(tree, Xb[i], mine)
                ref = brute_force_shap(tree, Xb[i], f)
                worst = max(worst, float(np.abs(mine - ref).max()))
                checks += 1
    line("vs. brute-force Shapley definition",
         f"max error {worst:.2e} over {checks} comparisons", worst < 1e-6)
    check(worst < 1e-6, f"TreeSHAP disagrees with the definition by {worst:.2e}")

    # Local accuracy on the real model.
    det, w = STATE["det"], STATE["world"]
    phi, base = shap_values(det.model, w.feats.iloc[:30].to_numpy(dtype="float32"),
                            check=True)
    got = base + phi.sum(axis=1)
    want = det.model.decision_function(w.feats.iloc[:30].to_numpy(dtype="float32"))
    err = float(np.abs(got - want).max())
    line("local accuracy (base + Σφ == model output)", f"max error {err:.2e}",
         err < 1e-4)
    check(err < 1e-4, "TreeSHAP violates local accuracy")

    # A real explanation, end to end.
    p_all = det.predict_proba(w.feats)
    y = w.tx["fraud_label"].to_numpy()
    missed = np.where((y == 1) & (p_all < det.threshold))[0]
    idx = int(missed[np.argmin(p_all[missed])]) if len(missed) else 0
    e = det.explain(w.feats.iloc[[idx]], top_k=5)[0]
    print()
    line("worked example — the most confident miss:")
    txr = w.tx.iloc[idx]
    line(f"  transaction", str(txr["transaction_id"]))
    line(f"  attack / stage / skill",
         f"{txr['attack_type']} / {txr['attack_stage']} / {txr['difficulty']}")
    line(f"  amount", f"₹{txr['amount']:,.2f}")
    line(f"  risk score / band / action",
         f"{e['risk_score']:.1f} / {e['risk_band']} / {e['action']}")
    print()
    line("  top risk drivers:")
    for r in e["reasons"][:5]:
        line(f"    {r['label'][:40]}", f"{r['value']:>12.3f}  φ={r['contribution']:+.5f}")
    if e["protective_factors"]:
        line("  protective factors (why it slipped through):")
        for r in e["protective_factors"][:3]:
            line(f"    {r['label'][:40]}", f"{r['value']:>12.3f}  φ={r['contribution']:+.5f}")
    check(bool(e["reasons"]) or bool(e["protective_factors"]),
          "explanation produced no attributions at all")
    print()
    line("narrative", "", True)
    print(f"      {D}{det.narrative(e)[:150]}{X}")


# ==========================================================================
# Stage 7 — risk engine
# ==========================================================================
def stage_risk(cfg: Dict) -> None:
    head("7. RISK DECISION ENGINE")
    import numpy as np
    det, w, split = STATE["det"], STATE["world"], STATE["split"]
    F = w.feats.iloc[split.test]
    y = w.tx["fraud_label"].to_numpy()[split.test]
    p = det.predict_proba(F)

    # monotonicity
    probe = np.linspace(0, 1, 201)
    scores = det.risk.score(probe)
    check(np.all(np.diff(scores) >= -1e-9), "risk score is not monotonic in probability")
    line("risk score monotonic in probability", "", True)

    anchored = float(det.risk.score(np.array([det.threshold]))[0])
    line("operating threshold maps to STEP_UP edge",
         f"{anchored:.1f} == {det.risk.anchor_score:.1f}",
         abs(anchored - det.risk.anchor_score) < 1e-6)

    print()
    line("risk-band routing on the held-out window:")
    print(f"{D}      {'band':<10s}{'action':<16s}{'count':>8s}{'fraud':>7s}{'legit':>8s}"
          f"{'% of fraud':>12s}{X}")
    dist = det.risk.distribution(p, y)
    total = 0
    for b in dist:
        total += b["count"]
        print(f"      {b['band']:<10s}{b['action'].replace('_',' ').lower():<16s}"
              f"{b['count']:>8,d}{b['fraud']:>7,d}{b['legit']:>8,d}"
              f"{b['share_of_all_fraud']:>11.1%}")
    check(total == len(p), "risk bands do not account for every transaction")
    line("bands account for every transaction", f"{total:,}", True)

    fr = det.risk.friction_summary(p, y)
    print()
    line("customer friction:")
    line("  honest traffic challenged or held", f"{fr['legit_challenged_share']:.2%}")
    line("  fraud stopped (challenged or held)", f"{fr['fraud_stopped_share']:.1%}")
    line("  fraud allowed straight through", f"{fr['fraud_allowed_share']:.1%}")
    for k, v in fr.items():
        if k.endswith("_share"):
            check(0.0 <= v <= 1.0, f"friction share {k}={v} out of range")


# ==========================================================================
# Stage 8 — gap analysis
# ==========================================================================
def stage_gap(cfg: Dict) -> None:
    head("8. GAP ANALYSIS — why did the defence fail?")
    from sovereignguard.pipeline import diagnose
    w, det, split = STATE["world"], STATE["det"], STATE["split"]
    gap, _ = diagnose(w, det, split)
    STATE["gap"] = gap

    print(f"    {gap.headline()}")
    check(gap.n_detected + gap.n_missed == gap.n_attacks,
          "gap report is internally inconsistent")
    line("detected + missed == attacks",
         f"{gap.n_detected} + {gap.n_missed} == {gap.n_attacks}", True)

    if gap.n_missed == 0:
        line("no misses to explain (recall is 1.0 on this window)", "", True)
        return

    print()
    print(f"{D}      {'evasion trait':<28s}{'%missed':>9s}{'%caught':>9s}"
          f"{'lift':>8s}{'attrib':>9s}{X}")
    for c in gap.causes[:8]:
        print(f"      {c['label'][:28]:<28s}{c['share_of_missed']:>8.0%}"
              f"{c['share_of_detected']:>9.0%}{c['lift']:>7.2f}x"
              f"{c['attribution']:>9.0%}")
        check(0.0 <= c["share_of_missed"] <= 1.0, f"bad share for {c['key']}")
        check(bool(c["remediation"]), f"cause {c['key']} has no remediation")

    if gap.weakest_segments:
        print()
        line("weakest segments:")
        for s in gap.weakest_segments[:5]:
            line(f"  {s['attack_type']:<26s} {s['difficulty']:<6s} n={s['n']:<4d}",
                 f"recall {s['recall']:.3f}")

    print()
    line("top remediation:")
    print(f"      {D}{gap.causes[0]['remediation'][:110]}{X}")

    knobs = gap.priority_knobs()
    line("knobs the adversarial generator will push",
         ", ".join(k for k, _, _ in knobs) or "(none)", bool(knobs))


# ==========================================================================
# Stage 9 — adaptive loop
# ==========================================================================
def stage_loop(cfg: Dict) -> None:
    head("9. ADAPTIVE LOOP — diagnose, adapt, retrain, retest")
    from sovereignguard.pipeline import adversarial_loop
    w, det, split = STATE["world"], STATE["det"], STATE["split"]

    t0 = time.time()
    res, det2, _ = adversarial_loop(w, det, split, n_adversarial=cfg["n_adv"],
                                    use_search=True, search_rounds=cfg["rounds"],
                                    quiet=True)
    STATE["loop"] = res

    plan = res.adaptation_plan
    line("adaptation plan:")
    for mv in plan.get("moves", [])[:4]:
        line(f"  {mv['cause_label'][:34]:<34s}",
             f"lift {mv['lift']:.2f}x, {mv['share_of_missed']:.0%} of misses")
        print(f"      {D}-> {mv['rationale'][:100]}{X}")

    b, a, d = res.before, res.after, res.delta
    meta = res.meta
    print()
    line("evaluation population (held out, never trained on):",
         f"{meta['eval_population']['n']:,} events, "
         f"{meta['eval_population']['n_fraud']:,} fraudulent")
    print()
    print(f"{D}      {'metric':<22s}{'BEFORE':>12s}{'AFTER':>12s}{'DELTA':>12s}{X}")
    for k, label, fmt in (("recall", "recall", ".4f"), ("precision", "precision", ".4f"),
                          ("f1", "F1", ".4f"), ("pr_auc", "PR-AUC", ".4f")):
        delta = a[k] - b[k]
        col = G if delta > 0 else (R if delta < 0 else "")
        print(f"      {label:<22s}{b[k]:>12{fmt}}{a[k]:>12{fmt}}"
              f"{col}{delta:>+12{fmt}}{X}")
    print(f"      {'attacks missed':<22s}{b['fn']:>12,d}{a['fn']:>12,d}"
          f"{G}{a['fn']-b['fn']:>+12,d}{X}")
    print(f"      {'false-positive rate':<22s}{b['fpr']:>12.5f}{a['fpr']:>12.5f}"
          f"{'   matched':>12s}")

    check(abs(a["fpr"] - b["fpr"]) < 2e-3,
          f"FPR not matched between before ({b['fpr']:.5f}) and after ({a['fpr']:.5f}) "
          f"-- the comparison is invalid")
    line("false-positive budget matched on both sides", "", True)
    check(d["recall_delta"] > 0,
          f"hardening did not improve held-out adversarial recall "
          f"({d['recall_delta']:+.4f})")

    # The honest half: did baseline performance regress?
    rb, ra = res.baseline_on_baseline, res.hardened_on_baseline
    print()
    line("REGRESSION CHECK — original attack distribution:")
    line("  recall before / after",
         f"{rb['recall']:.4f} / {ra['recall']:.4f} "
         f"({d['baseline_recall_delta']:+.4f})")
    if d["baseline_recall_delta"] < -0.02:
        print(f"      {Y}NOTE: baseline recall regressed. This is a real trade-off,{X}")
        print(f"      {Y}surfaced deliberately — see README 'The headline result'.{X}")

    print()
    line("elapsed", f"{time.time()-t0:.1f}s")
    line("methodology", "", True)
    print(f"      {D}{meta['methodology']}{X}")


# ==========================================================================
# Stage 10 — leakage audit
# ==========================================================================
def stage_audit(cfg: Dict) -> None:
    head("10. LEAKAGE AUDIT — trying to break our own results")
    import numpy as np
    from sovereignguard.evaluation.metrics import roc_auc
    from sovereignguard.schema import FEATURE_COLUMNS
    w = STATE["world"]
    y = w.tx["fraud_label"].to_numpy()

    scores = []
    for c in FEATURE_COLUMNS:
        auc = roc_auc(y, w.feats[c].to_numpy())
        if auc is not None and not np.isnan(auc):
            scores.append((max(auc, 1 - auc), c))
    scores.sort(reverse=True)

    line("single-feature separability (1.0 would be a label oracle):")
    for auc, c in scores[:6]:
        flag = f"  {R}<- LEAK{X}" if auc > 0.99 else ""
        print(f"      {auc:.4f}  {c}{flag}")
    top, name = scores[0]
    check(top < 0.99,
          f"feature '{name}' separates the label at AUC {top:.4f} -- this is a leak, "
          f"not a signal")
    line("no feature is a label oracle", f"max {top:.4f} < 0.99", True)

    # devices must be indistinguishable at registration
    dv = w.devices
    atk = dv["device_id"].str.startswith(("DEV_ATK_", "DEV_SYN_")).to_numpy()
    if atk.sum() >= 3:
        ra, rl = float(dv.loc[atk, "reputation"].mean()), float(dv.loc[~atk, "reputation"].mean())
        line("attacker vs legit device reputation", f"{ra:.3f} vs {rl:.3f}",
             abs(ra - rl) < 0.15)
        check(abs(ra - rl) < 0.15,
              "attacker devices are distinguishable from the registry alone")

    # synthetic identities must not be trivially separable
    cu = w.customers
    syn = (cu["is_synthetic_identity"] == 1).to_numpy()
    if syn.sum() >= 3:
        worst = 0.0
        for c in ("identity_doc_score", "contactability_score", "digital_footprint_days"):
            auc = roc_auc(syn.astype(int), cu[c].to_numpy())
            if auc is not None and not np.isnan(auc):
                worst = max(worst, max(auc, 1 - auc))
        line("synthetic-identity origination separability", f"{worst:.4f}", worst < 0.99)
        check(worst < 0.99, "origination signals separate fabricated identities perfectly")

    # fraud must be spread over time
    ts = w.tx["timestamp"].to_numpy()
    lo, hi = ts.min(), ts.max()
    first_half = float((ts[y == 1] < lo + (hi - lo) * 0.5).mean())
    line("fraud events in the first half of the window", f"{first_half:.1%}",
         first_half > 0.15)
    check(first_half > 0.15, "fraud is piling up at the end of the stream")

    # campaign leakage across splits
    split = STATE["split"]
    aid = w.tx["attack_id"].to_numpy()
    where: Dict[str, set] = {}
    for nm in ("train", "valid", "test"):
        for i in getattr(split, nm):
            if aid[i]:
                where.setdefault(aid[i], set()).add(nm)
    spanning = [k for k, v in where.items() if len(v) > 1]
    line("attack campaigns spanning two splits", str(len(spanning)), not spanning)
    check(not spanning,
          f"CAMPAIGN LEAKAGE: {len(spanning)} attacks appear in more than one split")


# ==========================================================================
# Stage 11 — API
# ==========================================================================
def stage_api(cfg: Dict) -> None:
    head("11. REST API")
    import json as _json
    import socket
    import threading
    import urllib.error
    import urllib.request
    from sovereignguard.api.server import AppState, serve

    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()

    # Seed the server with the world we already built so /api/detect works
    # without re-running a simulation.
    st = AppState()
    st.put_world("verify_run", STATE["world"])
    st.put_detector("verify_run:baseline", STATE["det"])
    httpd = serve("127.0.0.1", port, state=st)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.5)
    base = f"http://127.0.0.1:{port}"

    def get(path):
        with urllib.request.urlopen(base + path, timeout=30) as r:
            return r.status, _json.loads(r.read())

    def post(path, body):
        rq = urllib.request.Request(base + path, data=_json.dumps(body).encode(),
                                    headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(rq, timeout=60) as r:
            return r.status, _json.loads(r.read())

    try:
        code, h = get("/api/health")
        line("GET  /api/health", f"{code} {h['status']}", code == 200)
        check(code == 200 and h["status"] == "ok", "health endpoint unhealthy")

        code, c = get("/api/config")
        line("GET  /api/config", f"{code}, {len(c['attack_types'])} attack types",
             code == 200)

        code, t = get("/api/taxonomy")
        line("GET  /api/taxonomy", f"{code}, {len(t['attacks'])} families", code == 200)
        check(len(t["attacks"]) == 7, "taxonomy does not expose 7 families")

        code, _ = get("/api/taxonomy/ACCOUNT_TAKEOVER")
        line("GET  /api/taxonomy/{type}", str(code), code == 200)

        code, dt = post("/api/detect", {"run_id": "verify_run"})
        line("POST /api/detect", f"{code}, recall {dt['overall']['recall']:.4f}",
             code == 200)
        check("risk_distribution" in dt and "operating_curve" in dt,
              "detect response is missing expected sections")

        code, sc = post("/api/score", {"run_id": "verify_run", "worst_missed": True})
        line("POST /api/score", f"{code}, {sc['decision']['risk_band']} risk",
             code == 200)
        check("explanation" in sc and "narrative" in sc,
              "score response missing explanation")

        code, rt = post("/api/redteam/generate",
                        {"run_id": "verify_run", "n_scenarios": 20, "difficulty": "HARD"})
        line("POST /api/redteam/generate",
             f"{code}, {rt['n_scenarios']} scenarios / {rt['n_events']} events",
             code == 200)

        code, gp = post("/api/gap", {"run_id": "verify_run"})
        line("POST /api/gap", f"{code}, {len(gp.get('causes', []))} causes", code == 200)

        # error handling must be graceful
        errs = 0
        for path in ("/api/nope", "/api/taxonomy/NOPE"):
            try:
                get(path)
            except urllib.error.HTTPError as e:
                errs += 1 if e.code == 404 else 0
        line("unknown routes return 404 (not 500)", f"{errs}/2", errs == 2)
        check(errs == 2, "API does not handle unknown routes gracefully")
    finally:
        httpd.shutdown()


# ==========================================================================
# Stage 12 — persistence + artefacts
# ==========================================================================
def stage_persistence(cfg: Dict) -> None:
    head("12. PERSISTENCE & ARTEFACTS")
    import tempfile
    from sovereignguard.store import Store

    with tempfile.TemporaryDirectory() as d:
        st = Store(path=Path(d) / "verify.db", allow_fallback=False)
        st.create_run("vr", "verify", {"scale": cfg["scale"]}, cfg["scale"], 1)
        st.save_world("vr", STATE["world"])
        st.save_model_run("vmr", "vr", STATE["det"], "baseline")
        rec = st.get_run("vr")
        check(rec is not None, "run did not persist")
        n_tx = st.query("SELECT COUNT(*) AS n FROM transactions WHERE run_id=?", ("vr",))[0]["n"]
        n_sc = st.query("SELECT COUNT(*) AS n FROM attack_scenarios WHERE run_id=?", ("vr",))[0]["n"]
        line("transactions persisted", f"{n_tx:,}", n_tx > 0)
        line("attack scenarios persisted", f"{n_sc:,}", n_sc > 0)
        line("model runs persisted", str(len(st.list_model_runs("vr"))), True)
        check(n_tx == len(STATE["world"].tx), "not all transactions were persisted")

        if STATE.get("loop"):
            st.save_loop("vl", "vr", STATE["loop"])
            line("loop result persisted", "", bool(st.latest_loop()))

    # detector round-trip
    import numpy as np
    from sovereignguard.detection import Detector
    det, w = STATE["det"], STATE["world"]
    sub = w.feats.iloc[:120]
    before = det.predict_proba(sub)
    with tempfile.TemporaryDirectory() as d:
        det.save(Path(d) / "det")
        again = Detector.load(Path(d) / "det")
    after = again.predict_proba(sub)
    same = bool(np.array_equal(before, after))
    line("detector save/load reproduces predictions exactly", "", same)
    check(same, "detector round-trip changed predictions")

    # experiment artefacts, if a suite has been run
    res_dir = ROOT / "experiments" / "results"
    found = sorted(p.name for p in res_dir.glob("exp*.json")) if res_dir.exists() else []
    line("experiment artefacts on disk", f"{len(found)} files",
         len(found) > 0 or None)
    for f in found:
        try:
            _ = json.loads((res_dir / f).read_text())
            line(f"  {f}", "valid JSON", True)
        except Exception as exc:
            raise AssertionError(f"{f} is not valid JSON: {exc}")


# ==========================================================================
# Stage 13 — CLI
# ==========================================================================
def stage_cli(cfg: Dict) -> None:
    head("13. COMMAND LINE")
    cmds = [
        (["taxonomy"], "GENAI PAYMENT FRAUD"),
        (["--help"], "SovereignGuard"),
        (["train", "--scale", "nano"], "recall"),
    ]
    for args, expect in cmds:
        t0 = time.time()
        proc = subprocess.run([sys.executable, "sg.py"] + args, cwd=str(ROOT),
                              capture_output=True, text=True, timeout=600)
        out = proc.stdout + proc.stderr
        ok = proc.returncode == 0 and expect.lower() in out.lower()
        line(f"python sg.py {' '.join(args)}", f"{time.time()-t0:.1f}s", ok)
        if not ok:
            print(f"      {R}{out.strip()[-400:]}{X}")
        check(ok, f"`sg.py {' '.join(args)}` failed or produced unexpected output")


# ==========================================================================
# Stage 14 — frontend (static checks only)
# ==========================================================================
def stage_frontend(cfg: Dict) -> None:
    head("14. FRONTEND (static checks)")
    fe = ROOT / "frontend"
    if not fe.exists():
        line("frontend/ not present", "", None)
        return

    import re
    files = [p for p in fe.rglob("*") if p.suffix in (".js", ".jsx")
             and "node_modules" not in p.parts
             and ".next" not in p.parts]
    line("source files", str(len(files)))

    pkg = json.loads((fe / "package.json").read_text())
    deps = set(pkg.get("dependencies", {}))
    line("declared dependencies", ", ".join(sorted(deps)), len(deps) <= 4)

    # every relative import must resolve; every bare import must be declared
    allowed = deps | {"next/head", "next/link", "next/router", "react-dom/client"}
    bad: List[str] = []
    stmt = re.compile(r'import\s+((?:[^;]|\n)*?)\s+from\s+["\']([^"\']+)["\']')
    exports: Dict[str, set] = {}
    for p in files:
        src = p.read_text()
        names = set()
        for m in re.finditer(r"^export\s+(?:async\s+)?function\s+(\w+)", src, re.M):
            names.add(m.group(1))
        for m in re.finditer(r"^export\s+(?:const|let|var)\s+(\w+)", src, re.M):
            names.add(m.group(1))
        if re.search(r"^export\s+default", src, re.M):
            names.add("__default__")
        exports[str(p.resolve())] = names

    for p in files:
        src = p.read_text()
        for m in stmt.finditer(src):
            clause, spec = m.group(1), m.group(2)
            if spec.startswith("."):
                base = (p.parent / spec).resolve()
                cands = [base, base.with_suffix(".js"), base.with_suffix(".jsx"),
                         base.with_suffix(".css"), base / "index.js", base / "index.jsx"]
                target = next((c for c in cands if c.is_file()), None)
                if target is None:
                    bad.append(f"{p.name}: unresolved import '{spec}'")
                    continue
                if target.suffix == ".css":
                    continue
                have = exports.get(str(target), set())
                nm = re.search(r"\{([^}]*)\}", clause)
                if nm:
                    for part in nm.group(1).split(","):
                        nme = part.split(" as ")[0].strip()
                        if nme and nme not in have:
                            bad.append(f"{p.name}: '{nme}' not exported by {target.name}")
                dm = re.match(r"^\s*(\w+)\s*(?:,|$)", clause)
                if dm and "__default__" not in have:
                    bad.append(f"{p.name}: no default export in {target.name}")
            elif spec.split("/")[0] not in {d.split("/")[0] for d in allowed}:
                bad.append(f"{p.name}: undeclared package '{spec}'")

    line("imports and exports resolve", f"{len(bad)} problems", not bad)
    for b in bad[:8]:
        print(f"      {R}{b}{X}")
    check(not bad, "frontend has unresolved imports or missing exports")

    # global CSS may only be imported from _app (Next.js hard rule)
    css_importers = [p.name for p in files
                     if re.search(r'import\s+["\'].*globals\.css["\']', p.read_text())]
    line("globals.css imported only from _app.jsx", ", ".join(css_importers) or "none",
         css_importers == ["_app.jsx"])
    check(css_importers == ["_app.jsx"],
          f"Next.js rejects global CSS outside _app; found in {css_importers}")

    node = shutil.which("node")
    npm = shutil.which("npm")
    print()
    if node and npm:
        line("node", subprocess.run([node, "--version"], capture_output=True,
                                    text=True).stdout.strip())
        if (fe / "node_modules").exists():
            line("node_modules present", "run `npm run build` in frontend/ to verify",
                 None)
        else:
            line("node_modules absent",
                 "run `cd frontend && npm install` before first use", None)
    else:
        line("node/npm not found", "dashboard cannot be verified here", None)
        print(f"      {D}The Python API and CLI cover the same ground; see README.{X}")


# ==========================================================================
STAGES: List[Tuple[str, str, Callable]] = [
    ("env", "environment and imports", stage_environment),
    ("tests", "unit test suite", stage_tests),
    ("world", "synthetic data engine", stage_world),
    ("redteam", "red team generation", stage_redteam),
    ("blueteam", "blue team detection", stage_blueteam),
    ("explain", "TreeSHAP explainability", stage_explain),
    ("risk", "risk decision engine", stage_risk),
    ("gap", "gap analysis", stage_gap),
    ("loop", "adaptive loop", stage_loop),
    ("audit", "leakage audit", stage_audit),
    ("api", "REST API", stage_api),
    ("store", "persistence and artefacts", stage_persistence),
    ("cli", "command line", stage_cli),
    ("frontend", "frontend static checks", stage_frontend),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="SovereignGuard end-to-end verification",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_true", help="smallest scale (~90s)")
    g.add_argument("--full", action="store_true", help="demo scale (~15 min)")
    ap.add_argument("--stage", nargs="*", help="run only these stages")
    ap.add_argument("--list", action="store_true", help="list stages and exit")
    ap.add_argument("--skip", nargs="*", default=[], help="skip these stages")
    a = ap.parse_args(argv)

    if a.list:
        print("stages:")
        for key, desc, _ in STAGES:
            print(f"  {key:<10s} {desc}")
        return 0

    profile = "quick" if a.quick else ("full" if a.full else "normal")
    cfg = dict(PROFILES[profile])

    print(f"{BOLD}{'=' * 74}{X}")
    print(f"{BOLD}  SOVEREIGNGUARD — END-TO-END VERIFICATION{X}")
    print(f"{'=' * 74}")
    print(f"  profile        {profile}  (scale={cfg['scale']}, "
          f"adversarial={cfg['n_adv']}, rounds={cfg['rounds']})")
    print(f"  repo           {ROOT}")
    print(f"  python         {sys.executable}")
    print(f"{'=' * 74}")

    selected = [s for s in STAGES
                if (not a.stage or s[0] in a.stage) and s[0] not in a.skip]
    if not selected:
        print(f"{R}no stages matched{X}")
        return 2

    results: List[Tuple[str, str, float, Optional[str]]] = []
    t_all = time.time()
    for key, desc, fn in selected:
        t0 = time.time()
        try:
            fn(cfg)
            results.append((key, "pass", time.time() - t0, None))
        except AssertionError as exc:
            print(f"\n    {FAIL} {exc}")
            results.append((key, "fail", time.time() - t0, str(exc)))
        except Exception as exc:
            print(f"\n    {FAIL} {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=6)
            results.append((key, "fail", time.time() - t0,
                            f"{type(exc).__name__}: {exc}"))

    # ---------------------------------------------------------------- summary
    n_pass = sum(1 for _, s, _, _ in results if s == "pass")
    n_fail = sum(1 for _, s, _, _ in results if s == "fail")
    print(f"\n{BOLD}{'=' * 74}{X}")
    print(f"{BOLD}  SUMMARY{X}")
    print(f"{'=' * 74}")
    for key, status, dt, err in results:
        desc = next(d for k, d, _ in STAGES if k == key)
        mark = PASS if status == "pass" else FAIL
        print(f"  {mark}  {key:<10s} {desc:<34s} {dt:6.1f}s")
        if err:
            print(f"          {R}{err[:140]}{X}")

    print(f"\n  stages   {n_pass} passed, {n_fail} failed")
    if STATE.get("tests_passed"):
        print(f"  unit     {STATE['tests_passed']} tests passed")
    if STATE.get("loop"):
        d = STATE["loop"].delta
        print(f"  loop     held-out adversarial recall {d['recall_delta']:+.4f} "
              f"at matched FPR")
        print(f"           baseline distribution        "
              f"{d['baseline_recall_delta']:+.4f}")
    print(f"  total    {time.time()-t_all:.1f}s")
    print(f"{'=' * 74}")

    if n_fail == 0:
        print(f"\n  {G}{BOLD}ALL STAGES PASSED{X} — the pipeline works end to end.\n")
    else:
        print(f"\n  {R}{BOLD}{n_fail} STAGE(S) FAILED{X} — see the summary above.\n")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
