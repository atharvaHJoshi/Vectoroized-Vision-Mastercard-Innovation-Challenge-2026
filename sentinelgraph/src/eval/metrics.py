"""Metrics for the three-baseline comparison."""
from __future__ import annotations

from typing import Any, Dict, List


def accuracy(pred: str, truth: str) -> int:
    return 1 if pred == truth else 0


def evidence_coverage(retrieved: List[str], ground_truth: List[str]) -> float:
    if not ground_truth:
        return 1.0
    got = set(retrieved)
    need = set(ground_truth)
    return len(got & need) / len(need)


def claim_support_rate(claims: List[Dict[str, Any]]) -> float:
    if not claims:
        return 1.0
    supported = [c for c in claims if c.get("evidence_ids")]
    return len(supported) / len(claims)


def counterevidence_recall(counterarguments: List[Dict[str, Any]],
                           expected_traps: List[str]) -> float:
    if not expected_traps:
        return 1.0
    found = {ca.get("reason") for ca in counterarguments}
    return len(found & set(expected_traps)) / len(expected_traps)


def unauthorized_disclosure(result: Dict[str, Any],
                            authorized_tenant: str) -> int:
    """1 if restricted info leaked outside the authorized tenant."""
    tenant = result.get("tenant_id")
    return 0 if tenant == authorized_tenant else 1


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {}
    n = len(results)
    acc = sum(r.get("accuracy", 0) for r in results) / n
    cov = sum(r.get("evidence_coverage", 0) for r in results) / n
    csr = sum(r.get("claim_support_rate", 0) for r in results) / n
    cer = sum(r.get("counterevidence_recall", 0) for r in results) / n
    leak = sum(r.get("unauthorized_disclosure", 0) for r in results)
    latency = sum(r.get("latency_ms", 0) for r in results) / n
    return {
        "n": n,
        "accuracy": round(acc, 4),
        "evidence_coverage": round(cov, 4),
        "claim_support_rate": round(csr, 4),
        "counterevidence_recall": round(cer, 4),
        "unauthorized_disclosures": leak,
        "avg_latency_ms": round(latency, 2),
    }
