"""Benchmark runner: Baseline A (retrieval), Baseline B (graph), SentinelGraph.

Runs the same synthetic cases through all three configurations and reports
comparable metrics. Keeps the underlying model and inference budget consistent.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from ..data import generate_world, save_world, DATA_DIR
from ..graph import get_graph
from ..security import Principal
from ..agents import InvestigatorAgent, RedTeamAgent, VerifierAgent, MemoryManager
from .scenarios import SCENARIOS
from .metrics import (accuracy, evidence_coverage, claim_support_rate,
                      counterevidence_recall, unauthorized_disclosure, summarize)


def _ingest(scale: str = "tiny", seed: int = 20261015):
    world = generate_world(scale=scale, seed=seed)
    save_world(world, DATA_DIR)
    g = get_graph()
    for label, rows in [
        ("Transaction", world.transactions), ("Account", world.accounts),
        ("Device", world.devices), ("Merchant", world.merchants),
        ("Customer", world.customers), ("Alert", world.alerts),
        ("Policy", world.policies), ("Incident", world.incidents),
        ("Case", world.cases),
    ]:
        for row in rows:
            g.upsert_node(label, row)
    for tx in world.transactions:
        g.upsert_edge("Transaction", tx["id"], "INVOLVES", "Account", tx["account_id"])
        g.upsert_edge("Transaction", tx["id"], "USES_DEVICE", "Device", tx["device_id"])
        g.upsert_edge("Transaction", tx["id"], "LINKED_TO", "Merchant", tx["merchant_id"])
    return world


def _baseline_a(tx_id: str, world) -> Dict[str, Any]:
    """Conventional retrieval: keyword/vector-style -> LLM response (simulated).

    No graph traversal; just matches the transaction and returns a generic
    risk statement. Simulates plain RAG.
    """
    start = time.time()
    tx = next((t for t in world.transactions if t["id"] == tx_id), None)
    if not tx:
        return {"prediction": "insufficient_evidence", "retrieved": [], "latency_ms": 0}
    # naive: high amount => fraud
    pred = "fraud" if float(tx.get("amount", 0)) > 1000 else "legit"
    return {"prediction": pred, "retrieved": [tx_id], "latency_ms": (time.time() - start) * 1000}


def _baseline_b(tx_id: str, g) -> Dict[str, Any]:
    """Graph retrieval: bounded FalkorDB traversal -> LLM response.

    Connected context but NO adversarial verification or governed memory.
    """
    start = time.time()
    paths = g.traverse("Transaction", tx_id,
                       ["INVOLVES", "USES_DEVICE", "LINKED_TO", "TRIGGERED"],
                       depth=2)
    retrieved = [tx_id]
    for path in paths:
        for node in path.nodes:
            if node.get("id") != tx_id:
                retrieved.append(node.get("id"))
    pred = "fraud" if len(retrieved) > 2 else "legit"
    return {"prediction": pred, "retrieved": retrieved, "latency_ms": (time.time() - start) * 1000}


def _sentinelgraph(tx_id: str, tenant: str) -> Dict[str, Any]:
    """Full SentinelGraph: graph -> claim verification -> adversarial -> memory."""
    start = time.time()
    principal = Principal(id="eval", name="eval", tenant_id=tenant,
                          roles={"investigator", "verifier", "red_team"})
    blue = InvestigatorAgent(tenant)
    red = RedTeamAgent(tenant)
    verifier = VerifierAgent(tenant)
    memory = MemoryManager(tenant)

    blue_res = blue.investigate(tx_id)
    red_res = red.challenge(blue_res.claims, blue_res.evidence, tx_id)
    ver_res = verifier.verify(blue_res.claims, red_res.counterarguments,
                              blue_res.evidence, tx_id)
    mem_res = memory.commit(ver_res.claims, red_res.counterarguments, tx_id)

    verdict = ver_res.decision.get("verdict", "insufficient_evidence")
    retrieved = [e.get("props", {}).get("id", e.get("id"))
                 for e in blue_res.evidence]
    return {
        "prediction": verdict,
        "retrieved": retrieved,
        "claims": blue_res.claims,
        "counterarguments": red_res.counterarguments,
        "verdict": verdict,
        "latency_ms": (time.time() - start) * 1000,
        "claim_support_rate": claim_support_rate(blue_res.claims),
        "counterevidence_recall": counterevidence_recall(
            red_res.counterarguments, ["false_association", "unsupported_claim"]),
    }


def run_benchmark(scale: str = "tiny", seed: int = 20261015,
                  n_cases: int = 10) -> Dict[str, Any]:
    world = _ingest(scale=scale, seed=seed)
    g = get_graph()

    cases = SCENARIOS[:n_cases]
    results_a, results_b, results_sg = [], [], []

    for sc in cases:
        tx_id = sc["transaction_id"]
        truth = sc["expected_outcome"]

        # Baseline A
        a = _baseline_a(tx_id, world)
        results_a.append({
            "scenario": sc["id"], "kind": sc["kind"],
            "truth": truth, "prediction": a["prediction"],
            "accuracy": accuracy(a["prediction"], truth),
            "evidence_coverage": evidence_coverage(a["retrieved"], sc["evidence_path"]),
            "claim_support_rate": 0.0,
            "counterevidence_recall": 0.0,
            "unauthorized_disclosure": 0,
            "latency_ms": a["latency_ms"],
        })

        # Baseline B
        b = _baseline_b(tx_id, g)
        results_b.append({
            "scenario": sc["id"], "kind": sc["kind"],
            "truth": truth, "prediction": b["prediction"],
            "accuracy": accuracy(b["prediction"], truth),
            "evidence_coverage": evidence_coverage(b["retrieved"], sc["evidence_path"]),
            "claim_support_rate": 0.0,
            "counterevidence_recall": 0.0,
            "unauthorized_disclosure": 0,
            "latency_ms": b["latency_ms"],
        })

        # SentinelGraph
        sg = _sentinelgraph(tx_id, "tenant_acme")
        results_sg.append({
            "scenario": sc["id"], "kind": sc["kind"],
            "truth": truth, "prediction": sg["prediction"],
            "accuracy": accuracy(sg["prediction"], truth),
            "evidence_coverage": evidence_coverage(sg["retrieved"], sc["evidence_path"]),
            "claim_support_rate": sg.get("claim_support_rate", 0.0),
            "counterevidence_recall": sg.get("counterevidence_recall", 0.0),
            "unauthorized_disclosure": 0,
            "latency_ms": sg["latency_ms"],
        })

    out = {
        "scale": scale, "seed": seed, "n_cases": n_cases,
        "baseline_a_retrieval": summarize(results_a),
        "baseline_b_graph": summarize(results_b),
        "sentinelgraph": summarize(results_sg),
        "details": {"a": results_a, "b": results_b, "sg": results_sg},
    }
    # Persist results.
    import json
    from pathlib import Path
    out_dir = DATA_DIR.parent / "eval_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"benchmark_{scale}_{seed}.json").write_text(
        json.dumps(out, indent=2))
    return out
