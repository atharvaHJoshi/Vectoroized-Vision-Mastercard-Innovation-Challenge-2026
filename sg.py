#!/usr/bin/env python3
"""
SovereignGuard command line.

    python sg.py demo                      # full loop, end to end, one command
    python sg.py build   --scale demo      # build a world, save CSVs
    python sg.py train   --model gbdt      # train + evaluate the Blue Team
    python sg.py redteam --type ACCOUNT_TAKEOVER --difficulty HARD -n 500
    python sg.py gap                       # why did the detector fail?
    python sg.py loop    -n 400            # the adaptive attack/defence loop
    python sg.py experiments               # run all six experiments
    python sg.py serve   --port 8000       # API + dashboard
    python sg.py taxonomy                  # print the attack knowledge base
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sovereignguard import config as C          # noqa: E402
from sovereignguard import taxonomy             # noqa: E402


def _fmt(v, spec=".4f"):
    return "n/a" if v is None else format(v, spec)


def _table(rows, headers):
    if not rows:
        return "(none)"
    try:
        from tabulate import tabulate
        return tabulate(rows, headers=headers, tablefmt="simple", floatfmt=".4f")
    except Exception:
        w = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
        line = "  ".join(str(h).ljust(w[i]) for i, h in enumerate(headers))
        out = [line, "  ".join("-" * x for x in w)]
        for r in rows:
            out.append("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))
        return "\n".join(out)


def _metrics_block(m, title):
    print(f"\n  {title}")
    print(f"    recall      {_fmt(m.get('recall'))}      precision  {_fmt(m.get('precision'))}")
    print(f"    f1          {_fmt(m.get('f1'))}      roc_auc    {_fmt(m.get('roc_auc'))}")
    print(f"    pr_auc      {_fmt(m.get('pr_auc'))}      fpr        {_fmt(m.get('fpr'),'.5f')}")
    print(f"    detected    {m.get('tp')}/{m.get('n_positive')}   missed {m.get('fn')}   "
          f"false alarms {m.get('fp')}")
    if m.get("alerts_per_1k_legit") is not None:
        print(f"    alerts per 1,000 legitimate transactions: "
              f"{_fmt(m.get('alerts_per_1k_legit'), '.2f')}")


# ==========================================================================
def cmd_build(a):
    from sovereignguard.pipeline import build_world, save_world
    w = build_world(a.scale, a.seed, target_prevalence=a.prevalence,
                    attack_types=a.types or None)
    s = w.summary()
    print("\nWORLD SUMMARY")
    print(json.dumps({k: v for k, v in s.items() if k != "diversity"}, indent=2, default=str))
    print("\nATTACK DIVERSITY")
    d = s["diversity"]
    print(json.dumps({k: v for k, v in d.items()
                      if not k.endswith("_counts")}, indent=2, default=str))
    if a.save:
        paths = save_world(w)
        print(f"\nwrote {len(paths)} artefacts under {C.DATA_DIR}")
    return w


def cmd_train(a):
    from sovereignguard.pipeline import build_world, train_baseline
    w = build_world(a.scale, a.seed, target_prevalence=a.prevalence)
    det, sp = train_baseline(w, a.model, target_fpr=a.fpr)
    m = det.metrics["test"]["overall"]
    _metrics_block(m, f"BLUE TEAM ({a.model}) on held-out test window")
    print(f"\n  operating threshold {det.threshold:.6f} "
          f"(chosen on validation at FPR budget {det.target_fpr:.3%})")
    print("\n  RECALL BY DIFFICULTY")
    print(_table([[r["group"], r["n"], r["detected"], r["missed"], round(r["recall"], 4)]
                  for r in det.metrics["test"]["by_difficulty"]],
                 ["difficulty", "n", "detected", "missed", "recall"]))
    print("\n  RECALL BY ATTACK TYPE")
    print(_table([[r["group"], r["n"], r["detected"], r["missed"], round(r["recall"], 4)]
                  for r in det.metrics["test"]["by_attack_type"]],
                 ["attack type", "n", "detected", "missed", "recall"]))
    print("\n  TOP FEATURES")
    print(_table([[f["label"], round(f["importance"], 4)]
                  for f in det.metrics["top_features"][:12]], ["feature", "importance"]))
    if a.save_model:
        p = det.save(C.MODELS_DIR / f"{a.model}_baseline")
        print(f"\n  model saved to {p}")
    return w, det, sp


def cmd_redteam(a):
    from sovereignguard.pipeline import build_world
    w = build_world(a.scale, a.seed, target_prevalence=a.prevalence, quiet=False)
    mix = {a.difficulty: 1.0} if a.difficulty else None
    b = w.red_team.generate(a.n, attack_types=a.types or None, difficulty_mix=mix,
                            stream="cli")
    print(f"\nGENERATED {b.n_scenarios} scenarios / {b.n_events} events")
    print("\nDIVERSITY")
    print(json.dumps(b.diversity_report(), indent=2, default=str))
    if not b.scenarios.empty:
        print("\nSAMPLE SCENARIOS")
        cols = ["attack_id", "attack_type", "difficulty", "persona", "n_events",
                "total_value", "span_seconds"]
        print(_table(b.scenarios[cols].head(12).values.tolist(), cols))


def cmd_gap(a):
    from sovereignguard.pipeline import build_world, train_baseline, diagnose
    w = build_world(a.scale, a.seed, target_prevalence=a.prevalence)
    det, sp = train_baseline(w, a.model, target_fpr=a.fpr)
    gap, _ = diagnose(w, det, sp)
    print("\n" + "=" * 78)
    print("GAP ANALYSIS — why did the defence fail?")
    print("=" * 78)
    print(f"\n{gap.headline()}\n")
    print(_table([[c["label"], f"{c['share_of_missed']:.0%}", f"{c['share_of_detected']:.0%}",
                   f"{c['lift']:.2f}x", f"{c['attribution']:.0%}"]
                  for c in gap.causes],
                 ["evasion trait", "% of misses", "% of catches", "lift", "attribution"]))
    print("\nWEAKEST SEGMENTS")
    print(_table([[s["attack_type"], s["difficulty"], s["n"], s["missed"],
                   round(s["recall"], 3)] for s in gap.weakest_segments],
                 ["attack type", "difficulty", "n", "missed", "recall"]))
    print("\nREMEDIATION FOR THE TOP THREE CAUSES")
    for c in gap.causes[:3]:
        print(f"\n  {c['label']}  (lift {c['lift']:.2f}x)")
        print(f"    diagnosis:   {c['description']}")
        print(f"    remediation: {c['remediation']}")


def cmd_loop(a):
    from sovereignguard.pipeline import (build_world, train_baseline,
                                         adversarial_loop)
    t0 = time.time()
    w = build_world(a.scale, a.seed, target_prevalence=a.prevalence)
    det, sp = train_baseline(w, a.model, target_fpr=a.fpr)
    res, det2, _ = adversarial_loop(w, det, sp, n_adversarial=a.n,
                                    model_kind=a.model, use_search=not a.no_search,
                                    search_rounds=a.rounds, intensity=a.intensity)
    print("\n" + "=" * 78)
    print("ADAPTIVE ATTACK / DEFENCE LOOP")
    print("=" * 78)
    print("\nADAPTATION PLAN")
    for m in res.adaptation_plan.get("moves", []):
        print(f"\n  weakness: {m['cause_label']}  (lift {m['lift']:.2f}x, "
              f"{m['share_of_missed']:.0%} of misses)")
        print(f"  response: {m['rationale']}")
    _metrics_block(res.before, "BEFORE — baseline model on HELD-OUT adversarial batch")
    _metrics_block(res.after, "AFTER  — hardened model on the SAME held-out batch")
    d = res.delta
    print(f"\n  DELTA   recall {d['recall_delta']:+.4f}   f1 {d['f1_delta']:+.4f}   "
          f"pr_auc {d['pr_auc_delta']:+.4f}")
    print(f"          missed {d['missed_before']} -> {d['missed_after']}   "
          f"fpr held at {d['fpr_after']:.5f}")
    print(f"\n  REGRESSION CHECK on the original attack distribution:")
    print(f"          recall {res.baseline_on_baseline['recall']:.4f} -> "
          f"{res.hardened_on_baseline['recall']:.4f} "
          f"({d['baseline_recall_delta']:+.4f})")
    print(f"\n  {res.meta['methodology']}")
    print(f"\n  total elapsed {time.time()-t0:.1f}s")
    out = C.EXPERIMENTS_DIR / "adaptive_loop.json"
    out.write_text(json.dumps(res.to_dict(), indent=2, default=str))
    print(f"  written to {out}")


def cmd_demo(a):
    a.scale = a.scale or "tiny"
    print("=" * 78)
    print("SOVEREIGNGUARD — END-TO-END DEMONSTRATION")
    print("  IDENTIFY -> GENERATE -> ATTACK -> DETECT -> EXPLAIN -> ADAPT -> RETEST")
    print("=" * 78)
    cmd_loop(a)


def cmd_experiments(a):
    from experiments.run_all import run_all
    run_all(scale=a.scale, seed=a.seed, quick=a.quick, only=getattr(a,"only",None))


def cmd_snapshot(a):
    from sovereignguard.snapshot import save_snapshot
    from sovereignguard.pipeline import build_world, train_baseline
    from sovereignguard.config import DATA_DIR
    w = build_world(a.scale, a.seed, target_prevalence=a.prevalence,
                    attack_types=a.types or None, quiet=False)
    det, _sp = train_baseline(w, a.model, target_fpr=a.fpr, quiet=True)
    m = det.metrics["test"]["overall"]
    _metrics_block(m, f"BLUE TEAM ({a.model}) held-out test window")
    rid = f"seed_{a.scale}"
    p = save_snapshot(w, det, rid, meta={
        "scale": a.scale, "seed": a.seed,
        "target_prevalence": a.prevalence,
        "attack_types": list(a.types) if a.types else None,
        "model_kind": a.model,
    })
    print(f"\nsnapshot written to {p}")
    print(f"  start fully populated:  python sg.py serve")
    return w, det


def cmd_serve(a):
    from sovereignguard.api.server import serve
    seed = not a.no_seed
    env = os.environ.get("SG_SEED", "").lower()
    if env:
        seed = env not in ("0", "false", "no")
    httpd = serve(a.host, a.port, seed=seed)
    print(f"SovereignGuard on http://{a.host}:{a.port}")
    print(f"  dashboard : http://{a.host}:{a.port}/")
    print(f"  API health: http://{a.host}:{a.port}/api/health")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


def cmd_taxonomy(a):
    taxonomy.validate()
    if a.type:
        print(json.dumps(taxonomy.get(a.type), indent=2))
        return
    print("\nGENAI PAYMENT FRAUD ATTACK KNOWLEDGE BASE\n")
    print(_table([[e["attack_type"], e["severity"], e["family"], e["n_stages"],
                   f"{e['base_rate_prior']:.2f}"] for e in taxonomy.summary_table()],
                 ["attack type", "severity", "family", "stages", "prior"]))
    print("\nDIFFICULTY LEVELS")
    for k, v in taxonomy.difficulty_levels().items():
        print(f"\n  {k}\n    {v}")


# ==========================================================================
def main(argv=None):
    p = argparse.ArgumentParser(
        prog="sg", description="SovereignGuard — AI Red Team / Blue Team payment defence lab",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, scale_default="tiny"):
        sp.add_argument("--scale", default=scale_default, choices=sorted(C.SCALES))
        sp.add_argument("--seed", type=int, default=C.SEED)
        sp.add_argument("--prevalence", type=float, default=0.010,
                        help="target fraud share of the event stream")
        return sp

    s = common(sub.add_parser("build", help="build a synthetic world"))
    s.add_argument("--types", nargs="*", choices=C.ATTACK_TYPES)
    s.add_argument("--save", action="store_true", help="write CSVs to data/")
    s.set_defaults(func=cmd_build)

    s = common(sub.add_parser("train", help="train and evaluate the Blue Team"))
    s.add_argument("--model", default="gbdt", choices=["gbdt", "forest"])
    s.add_argument("--fpr", type=float, default=C.TARGET_FPR_BUDGET)
    s.add_argument("--save-model", action="store_true")
    s.set_defaults(func=cmd_train)

    s = common(sub.add_parser("redteam", help="generate synthetic attacks"))
    s.add_argument("-n", type=int, default=200, help="number of scenarios")
    s.add_argument("--types", nargs="*", choices=C.ATTACK_TYPES)
    s.add_argument("--difficulty", choices=C.DIFFICULTIES)
    s.set_defaults(func=cmd_redteam)

    s = common(sub.add_parser("gap", help="explain why the defence failed"))
    s.add_argument("--model", default="gbdt", choices=["gbdt", "forest"])
    s.add_argument("--fpr", type=float, default=C.TARGET_FPR_BUDGET)
    s.set_defaults(func=cmd_gap)

    s = common(sub.add_parser("loop", help="adaptive attack/defence loop"))
    s.add_argument("-n", type=int, default=300, help="adversarial scenarios")
    s.add_argument("--model", default="gbdt", choices=["gbdt", "forest"])
    s.add_argument("--fpr", type=float, default=C.TARGET_FPR_BUDGET)
    s.add_argument("--rounds", type=int, default=2)
    s.add_argument("--intensity", type=float, default=0.85)
    s.add_argument("--no-search", action="store_true",
                   help="use interpretable knob adaptation only")
    s.set_defaults(func=cmd_loop)

    s = common(sub.add_parser("demo", help="the whole story in one command"))
    s.add_argument("-n", type=int, default=200)
    s.add_argument("--model", default="gbdt", choices=["gbdt", "forest"])
    s.add_argument("--fpr", type=float, default=C.TARGET_FPR_BUDGET)
    s.add_argument("--rounds", type=int, default=2)
    s.add_argument("--intensity", type=float, default=0.85)
    s.add_argument("--no-search", action="store_true")
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("experiments", help="run the six measured experiments")
    s.add_argument("--scale", default="tiny", choices=sorted(C.SCALES))
    s.add_argument("--seed", type=int, default=C.SEED)
    s.add_argument("--quick", action="store_true", help="fewer repeats")
    s.add_argument("--only", nargs="*", help="run only these, e.g. --only 3 4")
    s.set_defaults(func=cmd_experiments)

    s = common(sub.add_parser("snapshot", help="build + train + persist a boot seed"))
    s.add_argument("--model", default="gbdt", choices=["gbdt", "forest"])
    s.add_argument("--fpr", type=float, default=C.TARGET_FPR_BUDGET)
    s.add_argument("--types", nargs="*", choices=C.ATTACK_TYPES)
    s.set_defaults(func=cmd_snapshot)

    s = sub.add_parser("serve", help="run the API and dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--no-seed", action="store_true",
                   help="do not load data/snapshot on boot (start empty)")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("taxonomy", help="print the attack knowledge base")
    s.add_argument("--type", choices=C.ATTACK_TYPES)
    s.set_defaults(func=cmd_taxonomy)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    main()
