"""Benchmark comparison: three configurations on the same cases.

Acceptance criterion 7: Baseline A / B / SentinelGraph evaluated on the same
test cases with comparable metrics.
"""
from src.eval.runner import run_benchmark


def test_benchmark_runs_all_three_baselines():
    out = run_benchmark(scale="tiny", seed=20261015, n_cases=6)
    for key in ("baseline_a_retrieval", "baseline_b_graph", "sentinelgraph"):
        assert key in out, f"missing {key}"
        m = out[key]
        assert set(m) >= {"accuracy", "evidence_coverage", "claim_support_rate",
                          "counterevidence_recall", "unauthorized_disclosures",
                          "avg_latency_ms", "n"}
        assert m["n"] == 6

    # SentinelGraph should support its claims (unlike the plain baselines).
    assert out["sentinelgraph"]["claim_support_rate"] > 0
    assert out["baseline_a_retrieval"]["claim_support_rate"] == 0
    assert out["baseline_b_graph"]["claim_support_rate"] == 0

    # No unauthorized disclosures in any config.
    assert out["sentinelgraph"]["unauthorized_disclosures"] == 0
