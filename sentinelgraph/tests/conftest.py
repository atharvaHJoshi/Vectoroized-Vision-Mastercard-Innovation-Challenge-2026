"""Shared fixtures for SentinelGraph tests.

Builds a tiny synthetic world and loads it into the in-memory graph, mirroring
what `python sg.py ingest` does. Tests run against the real graph client
(memory fallback) so they exercise the same code path as the demo.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data import generate_world, save_world  # noqa: E402
from src.graph import get_graph  # noqa: E402
from src.security import Principal  # noqa: E402


def build_world(scale="tiny", seed=20261015):
    world = generate_world(scale=scale, seed=seed)
    save_world(world)
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
    return world, g


def principal(tenant_id="tenant_acme", cross_tenant=False, roles=None):
    return Principal(id="test", name="test", tenant_id=tenant_id,
                     roles=set(roles or ["investigator"]),
                     cross_tenant=cross_tenant)
