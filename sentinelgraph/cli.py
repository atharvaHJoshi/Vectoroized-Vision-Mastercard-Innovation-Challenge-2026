#!/usr/bin/env python3
"""
SentinelGraph command line.

    python cli.py ingest              # load synthetic world into the graph
    python cli.py investigate <tx>    # run one adversarial investigation
    python cli.py eval                # run the 3-baseline benchmark
    python cli.py serve               # FastAPI backend on :8000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config import DEFAULT_TENANT, SCALES
from src.data import generate_world, save_world
from src.graph import get_graph
from src.security import Principal
from src.agents import InvestigatorAgent, RedTeamAgent, VerifierAgent, MemoryManager


def cmd_ingest(args):
    world = generate_world(scale=args.scale, seed=args.seed)
    paths = save_world(world)
    g = get_graph()
    count = 0
    for label, rows in [
        ("Transaction", world.transactions), ("Account", world.accounts),
        ("Device", world.devices), ("Merchant", world.merchants),
        ("Customer", world.customers), ("Alert", world.alerts),
        ("Policy", world.policies), ("Incident", world.incidents),
        ("Case", world.cases), ("Evidence", world.evidence),
    ]:
        for row in rows:
            g.upsert_node(label, row)
            count += 1
    for tx in world.transactions:
        g.upsert_edge("Transaction", tx["id"], "INVOLVES", "Account", tx["account_id"])
        g.upsert_edge("Transaction", tx["id"], "USES_DEVICE", "Device", tx["device_id"])
        g.upsert_edge("Transaction", tx["id"], "LINKED_TO", "Merchant", tx["merchant_id"])
    print(f"Ingested {count} nodes ({args.scale}, seed {args.seed})")
    print(f"Graph backend: {'falkordb' if g.using_falkordb else 'memory fallback'}")


def cmd_investigate(args):
    principal = Principal(id="cli", name="cli", tenant_id=args.tenant,
                          roles={"investigator", "verifier", "red_team"})
    blue = InvestigatorAgent(args.tenant)
    red = RedTeamAgent(args.tenant)
    verifier = VerifierAgent(args.tenant)
    memory = MemoryManager(args.tenant)

    blue_res = blue.investigate(args.transaction_id, depth=args.depth)
    red_res = red.challenge(blue_res.claims, blue_res.evidence, args.transaction_id)
    ver_res = verifier.verify(blue_res.claims, red_res.counterarguments,
                              blue_res.evidence, args.transaction_id)
    mem_res = memory.commit(ver_res.claims, red_res.counterarguments,
                            args.transaction_id)

    print("\n=== SENTINELGRAPH INVESTIGATION ===")
    print(f"Transaction: {args.transaction_id}  Tenant: {args.tenant}")
    print(f"Graph: {'falkordb' if get_graph().using_falkordb else 'memory fallback'}")
    print(f"\n[BLUE] {len(blue_res.claims)} claims proposed")
    for c in blue_res.claims:
        print(f"   - {c['statement']}  (conf {c['confidence']}, state PROPOSED)")
    print(f"\n[RED] {len(red_res.counterarguments)} counterarguments")
    for ca in red_res.counterarguments:
        print(f"   - {ca['statement']}  (strength {ca['strength']})")
    print(f"\n[VERIFIER] verdict: {ver_res.decision['verdict']}")
    for n in ver_res.notes:
        print(f"   - {n}")
    print(f"\n[MEMORY] v{mem_res.decision['version']}: "
          f"{mem_res.decision['promoted']} promoted, "
          f"{mem_res.decision['superseded']} superseded, "
          f"{mem_res.decision['hypotheses_retained']} hypotheses retained")
    print(f"\nFinal decision: {ver_res.decision['verdict']}")


def cmd_eval(args):
    from src.eval.runner import run_benchmark
    out = run_benchmark(scale=args.scale, seed=args.seed, n_cases=args.n_cases)
    print(json.dumps({
        "baseline_a_retrieval": out["baseline_a_retrieval"],
        "baseline_b_graph": out["baseline_b_graph"],
        "sentinelgraph": out["sentinelgraph"],
    }, indent=2))


def cmd_serve(args):
    import uvicorn  # type: ignore
    uvicorn.run("src.server:app", host=args.host, port=args.port, reload=args.reload)


def main(argv=None):
    p = argparse.ArgumentParser(prog="sg", description="SentinelGraph CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--scale", default="tiny", choices=sorted(SCALES))
        sp.add_argument("--seed", type=int, default=20261015)
        return sp

    s = common(sub.add_parser("ingest", help="load synthetic world into graph"))
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("investigate", help="run one adversarial investigation")
    s.add_argument("transaction_id")
    s.add_argument("--tenant", default=DEFAULT_TENANT)
    s.add_argument("--depth", type=int, default=3)
    s.set_defaults(func=cmd_investigate)

    s = common(sub.add_parser("eval", help="run 3-baseline benchmark"))
    s.add_argument("--n-cases", type=int, default=10)
    s.set_defaults(func=cmd_eval)

    s = sub.add_parser("serve", help="run FastAPI backend")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(func=cmd_serve)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    main()
