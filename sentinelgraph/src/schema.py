"""SentinelGraph graph schema.

Defines node labels, edge types, property contracts and the trust-state
machine. These are the application-level constructs FalkorDB stores; they are
NOT built-in FalkorDB features.
"""
from __future__ import annotations

from typing import Dict, List

from .config import TRUST_STATES, CONCLUSIVE_STATES

# ---------------------------------------------------------------------------
# Node labels (entity types)
# ---------------------------------------------------------------------------
NODE_LABELS = [
    # Domain entities
    "Customer", "Account", "Transaction", "Merchant", "Device",
    "Alert", "Incident", "Person", "Team", "Document", "Policy",
    # Evidence
    "Evidence", "SourceRecord", "EvidenceSpan", "ModelOutput",
    # Claims & verification
    "Claim", "VerificationRun", "Counterargument", "Decision",
    # Memory & coordination
    "Case", "AgentTask", "Handoff", "MemoryVersion", "Correction",
    # Governance
    "Tenant", "Principal", "Role", "PolicyDecision", "AuditEvent",
    # Organizational knowledge
    "Employee", "Team", "Project", "Runbook", "Ticket", "Service",
    "DecisionRecord",
]

# ---------------------------------------------------------------------------
# Edge types (relationships)
# ---------------------------------------------------------------------------
EDGE_TYPES = [
    "INVOLVES", "USES_DEVICE", "TRIGGERED", "LINKED_TO",
    "SUPPORTED_BY", "CONTRADICTED_BY", "SUPERSEDES",
    "INVESTIGATED_IN", "REFERENCES", "OWNED_BY", "PRODUCED",
    "PART_OF", "ISSUED_BY", "REVIEWED_BY", "BELONGS_TO",
    "HAS_CLAIM", "HAS_EVIDENCE", "NEXT_VERSION_OF", "CORRECTS",
    "GOVERNED_BY", "ASSIGNED_TO", "CITES",
]

# ---------------------------------------------------------------------------
# Trust-state transition rules.
# key = current state -> set of allowed next states
# ---------------------------------------------------------------------------
TRUST_TRANSITIONS: Dict[str, set] = {
    "PROPOSED": {"SUPPORTED", "CONTRADICTED", "SUPERSEDED"},
    "SUPPORTED": {"VERIFIED", "CONTRADICTED", "SUPERSEDED"},
    "VERIFIED": {"CONTRADICTED", "SUPERSEDED"},
    "CONTRADICTED": {"SUPERSEDED"},
    "SUPERSEDED": set(),  # terminal for active use; historical only
}

# States that may influence a final conclusion.
def is_conclusive(state: str) -> bool:
    return state in CONCLUSIVE_STATES


# ---------------------------------------------------------------------------
# Time-aware property names (valid-time / observation-time versioning)
# ---------------------------------------------------------------------------
TEMPORAL_PROPS = ("valid_from", "valid_to", "observed_at", "version_id")

# ---------------------------------------------------------------------------
# Sensitivity classification levels (for data minimization / redaction)
# ---------------------------------------------------------------------------
SENSITIVITY_LEVELS = ("public", "internal", "confidential", "restricted")

# ---------------------------------------------------------------------------
# Minimal property contract per node label (name -> (type, sensitive))
# Only the minimum data required for reasoning is stored in graph properties.
# Protected source content is retrieved through the authorized backend.
# ---------------------------------------------------------------------------
NODE_PROPS: Dict[str, Dict[str, tuple]] = {
    "Customer": {
        "id": (str, False), "name": (str, True), "tenant_id": (str, False),
        "created_at": (str, False), "risk_band": (str, False),
    },
    "Account": {
        "id": (str, False), "account_number": (str, True),
        "tenant_id": (str, False), "opened_at": (str, False),
        "currency": (str, False),
    },
    "Transaction": {
        "id": (str, False), "amount": (float, False), "currency": (str, False),
        "timestamp": (str, False), "type": (str, False),
        "tenant_id": (str, False), "status": (str, False),
    },
    "Merchant": {
        "id": (str, False), "name": (str, False), "category": (str, False),
        "tenant_id": (str, False),
    },
    "Device": {
        "id": (str, False), "fingerprint": (str, True), "tenant_id": (str, False),
        "first_seen": (str, False),
    },
    "Alert": {
        "id": (str, False), "severity": (str, False), "rule_id": (str, False),
        "triggered_at": (str, False), "tenant_id": (str, False),
    },
    "Incident": {
        "id": (str, False), "title": (str, False), "severity": (str, False),
        "opened_at": (str, False), "status": (str, False), "tenant_id": (str, False),
    },
    "Case": {
        "id": (str, False), "title": (str, False), "status": (str, False),
        "opened_at": (str, False), "tenant_id": (str, False),
        "version": (int, False),
    },
    "Claim": {
        "id": (str, False), "statement": (str, False), "state": (str, False),
        "confidence": (float, False), "created_at": (str, False),
        "created_by": (str, False), "tenant_id": (str, False),
    },
    "Evidence": {
        "id": (str, False), "description": (str, False),
        "observed_at": (str, False), "source_id": (str, False),
        "tenant_id": (str, False),
    },
    "SourceRecord": {
        "id": (str, False), "title": (str, False), "sensitivity": (str, False),
        "created_at": (str, False), "tenant_id": (str, False),
    },
    "Policy": {
        "id": (str, False), "title": (str, False), "version": (int, False),
        "effective_from": (str, False), "tenant_id": (str, False),
    },
    "VerificationRun": {
        "id": (str, False), "result": (str, False), "checked_at": (str, False),
        "checked_by": (str, False),
    },
    "Counterargument": {
        "id": (str, False), "statement": (str, False), "strength": (float, False),
        "created_at": (str, False),
    },
    "Decision": {
        "id": (str, False), "action": (str, False), "approved": (bool, False),
        "decided_at": (str, False), "decided_by": (str, False),
    },
    "Tenant": {"id": (str, False), "name": (str, False)},
    "Principal": {"id": (str, False), "name": (str, False), "tenant_id": (str, False)},
    "Role": {"id": (str, False), "name": (str, False)},
    "PolicyDecision": {"id": (str, False), "decision": (str, False)},
    "AuditEvent": {"id": (str, False), "action": (str, False), "at": (str, False)},
    "Employee": {"id": (str, False), "name": (str, True), "role": (str, False)},
    "Team": {"id": (str, False), "name": (str, False)},
    "Runbook": {"id": (str, False), "title": (str, False), "version": (int, False)},
    "Ticket": {"id": (str, False), "title": (str, False), "status": (str, False)},
    "Service": {"id": (str, False), "name": (str, False)},
    "DecisionRecord": {"id": (str, False), "title": (str, False)},
    "Correction": {"id": (str, False), "reason": (str, False), "at": (str, False)},
    "MemoryVersion": {"id": (str, False), "version": (int, False), "at": (str, False)},
    "AgentTask": {"id": (str, False), "task_type": (str, False), "status": (str, False)},
    "Handoff": {"id": (str, False), "summary": (str, False), "at": (str, False)},
    "Document": {"id": (str, False), "title": (str, False), "sensitivity": (str, False)},
    "Project": {"id": (str, False), "name": (str, False)},
}

# ---------------------------------------------------------------------------
# Sensitivity of properties by level -> which properties are redacted for
# non-authorized principals. None means always visible.
# ---------------------------------------------------------------------------
REDACTION_RULES: Dict[str, list] = {
    "restricted": ["name", "account_number", "fingerprint"],
    "confidential": ["name", "account_number"],
    "internal": ["name"],
}
