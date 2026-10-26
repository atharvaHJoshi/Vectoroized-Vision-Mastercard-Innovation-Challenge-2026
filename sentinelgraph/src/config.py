"""SentinelGraph configuration.

All constants for the Trust-Aware Investigation and Memory Engine.
Keep values here so the graph schema, tenant boundaries, agent roles and
trust-state lifecycle can be reviewed and changed in one place.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# FalkorDB (primary graph database)
# ---------------------------------------------------------------------------
FALKORDB_HOST = os.getenv("FALKORDB_HOST", "127.0.0.1")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6379"))
FALKORDB_DB = int(os.getenv("FALKORDB_DB", "0"))
# When FalkorDB is unavailable, fall back to an in-memory graph so the demo
# still runs and is demonstrable. FalkorDB remains the primary database in
# production/compose mode; the fallback is explicitly dev-only.
GRAPH_FALLBACK = os.getenv("SG_GRAPH_FALLBACK", "1") == "1"

# ---------------------------------------------------------------------------
# Tenant / access control
# ---------------------------------------------------------------------------
DEFAULT_TENANT = os.getenv("SG_DEFAULT_TENANT", "tenant_acme")
SUPER_TENANT = "tenant_system"  # can read across tenants (audit only)

# ---------------------------------------------------------------------------
# Trust-state lifecycle for claims
# ---------------------------------------------------------------------------
# An agent's output is a claim, not a fact. Claims move through these states.
TRUST_STATES = (
    "PROPOSED",      # an agent generated the claim
    "SUPPORTED",     # one or more sources support it
    "VERIFIED",      # defined checks passed against permitted evidence
    "CONTRADICTED",  # evidence conflicts with the claim
    "SUPERSEDED",    # a newer verified fact replaces it
)

# States that may influence a final conclusion (per the design doc table).
CONCLUSIVE_STATES = {"SUPPORTED", "VERIFIED"}

# ---------------------------------------------------------------------------
# Agent roles
# ---------------------------------------------------------------------------
ROLE_BLUE = "investigator"     # builds the supported case
ROLE_RED = "red_team"          # challenges claims
ROLE_VERIFIER = "verifier"     # checks both sides against evidence + policy
ROLE_MEMORY = "memory_manager" # promotes / supersedes / logs changes

# ---------------------------------------------------------------------------
# Graph traversal bounds (prevents LLM-run amok queries)
# ---------------------------------------------------------------------------
MAX_TRAVERSAL_DEPTH = 3
MAX_RESULTS = 50
ALLOWED_RELATIONSHIPS = {
    "INVOLVES", "USES_DEVICE", "TRIGGERED", "LINKED_TO",
    "SUPPORTED_BY", "CONTRADICTED_BY", "SUPERSEDES",
    "INVESTIGATED_IN", "REFERENCES", "OWNED_BY", "PRODUCED",
    "PART_OF", "ISSUED_BY", "REVIEWED_BY", "BELONGS_TO",
    "HAS_CLAIM", "HAS_EVIDENCE", "NEXT_VERSION_OF", "CORRECTS",
    "GOVERNED_BY", "ASSIGNED_TO", "CITES",
}

# ---------------------------------------------------------------------------
# Synthetic data scales
# ---------------------------------------------------------------------------
SCALES = {
    "nano":   {"customers": 60,   "accounts": 90,  "transactions": 600,
               "devices": 40,   "merchants": 30,  "cases": 8,
               "policies": 12,  "incidents": 6},
    "tiny":   {"customers": 200,  "accounts": 300, "transactions": 2500,
               "devices": 120,  "merchants": 90,  "cases": 25,
               "policies": 30,  "incidents": 15},
    "demo":   {"customers": 2000, "accounts": 3000,"transactions": 25000,
               "devices": 800,  "merchants": 500, "cases": 120,
               "policies": 80,  "incidents": 60},
}

DEFAULT_SCALE = "tiny"
SEED = 20261015

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = ROOT / "data" / "synthetic"
RESULTS_DIR = ROOT / "eval_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

GRAPH_MODEL_PATH = ROOT / "GRAPH_MODEL.md"
