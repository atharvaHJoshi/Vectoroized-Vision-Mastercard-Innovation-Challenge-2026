"""Adversarial test scenarios with ground truth.

Each scenario: a transaction + expected outcome + evidence path + traps
(false association, temporal conflict, memory poisoning, etc.).
"""
from __future__ import annotations

from typing import Any, Dict, List

# Canonical scenarios for the MVP. Ground truth is labelled; traps test
# whether the system abstains or fabricates.
SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "scenario_multi_hop",
        "kind": "multi_hop",
        "transaction_id": "txn_0",
        "expected_outcome": "fraud",
        "evidence_path": ["txn_0", "acc_0", "dev_0", "case_0"],
        "description": "Evidence connected through several entities.",
    },
    {
        "id": "scenario_false_association",
        "kind": "false_association",
        "transaction_id": "txn_1",
        "expected_outcome": "legit",
        "evidence_path": ["txn_1", "acc_1", "dev_shared"],
        "description": "Two accounts share a device; link alone is not fraud.",
        "trap": "shared_device_bait",
    },
    {
        "id": "scenario_temporal_conflict",
        "kind": "temporal_conflict",
        "transaction_id": "txn_2",
        "expected_outcome": "legit",
        "evidence_path": ["txn_2", "acc_2"],
        "description": "Previously valid relationship has changed.",
        "trap": "stale_device_link",
    },
    {
        "id": "scenario_memory_poisoning",
        "kind": "memory_poisoning",
        "transaction_id": "txn_3",
        "expected_outcome": "insufficient_evidence",
        "evidence_path": [],
        "description": "Source contains a false claim / malicious instruction.",
        "trap": "poisoned_source",
    },
    {
        "id": "scenario_correction",
        "kind": "correction",
        "transaction_id": "txn_4",
        "expected_outcome": "legit",
        "evidence_path": ["txn_4", "acc_4"],
        "description": "Earlier investigation was wrong; must not contaminate.",
        "trap": "stale_prior_case",
    },
    {
        "id": "scenario_access_control",
        "kind": "access_control",
        "transaction_id": "txn_5",
        "expected_outcome": "unauthorized",
        "evidence_path": ["txn_5"],
        "description": "User tries to read another tenant's restricted record.",
        "trap": "cross_tenant",
    },
    {
        "id": "scenario_missing_evidence",
        "kind": "missing_evidence",
        "transaction_id": "txn_6",
        "expected_outcome": "insufficient_evidence",
        "evidence_path": [],
        "description": "System must abstain instead of fabricating.",
        "trap": "no_linked_evidence",
    },
    {
        "id": "scenario_org_context",
        "kind": "org_context",
        "transaction_id": "txn_7",
        "expected_outcome": "fraud",
        "evidence_path": ["txn_7", "acc_7", "POL-200", "inc_0"],
        "description": "Correct decision depends on policy + incident + owner.",
    },
]


def scenario_by_id(sid: str) -> Dict[str, Any] | None:
    for s in SCENARIOS:
        if s["id"] == sid:
            return s
    return None
