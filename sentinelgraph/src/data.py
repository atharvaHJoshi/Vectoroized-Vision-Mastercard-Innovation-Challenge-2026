"""Synthetic data generator for SentinelGraph.

Produces a small, controlled payment-fraud world with tenants, accounts,
devices, transactions, alerts, incidents, cases, policies and ground-truth
evidence paths. Used to seed FalkorDB (or the in-memory fallback) and to drive
the evaluation scenarios.
"""
from __future__ import annotations

import csv
import json
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .config import DATA_DIR, DEFAULT_SCALE, SCALES, SEED
from .schema import SENSITIVITY_LEVELS

# ---------------------------------------------------------------------------
# World model
# ---------------------------------------------------------------------------
@dataclass
class World:
    scale: str
    seed: int
    tenants: List[Dict[str, Any]] = field(default_factory=list)
    customers: List[Dict[str, Any]] = field(default_factory=list)
    accounts: List[Dict[str, Any]] = field(default_factory=list)
    devices: List[Dict[str, Any]] = field(default_factory=list)
    merchants: List[Dict[str, Any]] = field(default_factory=list)
    transactions: List[Dict[str, Any]] = field(default_factory=list)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    incidents: List[Dict[str, Any]] = field(default_factory=list)
    cases: List[Dict[str, Any]] = field(default_factory=list)
    policies: List[Dict[str, Any]] = field(default_factory=list)
    employees: List[Dict[str, Any]] = field(default_factory=list)
    teams: List[Dict[str, Any]] = field(default_factory=list)
    runbooks: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    ground_truth: List[Dict[str, Any]] = field(default_factory=list)


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def generate_world(scale: str = DEFAULT_SCALE, seed: int = SEED) -> World:
    rng = _rng(seed)
    spec = SCALES[scale]
    w = World(scale=scale, seed=seed)

    # tenants
    for t in ("tenant_acme", "tenant_globex", "tenant_umbrella"):
        w.tenants.append({
            "id": t, "name": t.title().replace("_", " "),
            "sensitivity": "internal",
        })

    # employees / teams / runbooks (Company Brain)
    teams = ["Fraud Ops", "Compliance", "Payment Integrity", "SOC"]
    for i, tname in enumerate(teams):
        w.teams.append({
            "id": f"team_{i}", "name": tname, "tenant_id": "tenant_acme",
        })
    roles = ["Analyst", "Senior Analyst", "Investigator", "Compliance Officer"]
    for i in range(12):
        w.employees.append({
            "id": f"emp_{i}", "name": f"Employee {i}",
            "role": roles[i % len(roles)],
            "tenant_id": "tenant_acme",
            "team_id": f"team_{i % len(teams)}",
        })
    for i in range(6):
        w.runbooks.append({
            "id": f"runbook_{i}", "title": f"Runbook {i}: Payment Review",
            "version": i + 1,
            "effective_from": "2026-01-01",
            "tenant_id": "tenant_acme",
        })

    # policies
    policies = [
        ("POL-100", "High-value payment requires secondary approval"),
        ("POL-200", "Device shared across customers triggers review"),
        ("POL-300", "Cross-border payments above threshold need KYC re-check"),
        ("POL-400", "Prior fraud case on linked device must be disclosed"),
        ("POL-500", "Restricted records may not leave tenant boundary"),
    ]
    for i, (pid, title) in enumerate(policies):
        w.policies.append({
            "id": pid, "title": title, "version": 1,
            "effective_from": "2026-01-01",
            "tenant_id": "tenant_acme",
            "sensitivity": "internal",
        })

    # customers, accounts, devices, merchants
    for i in range(spec["customers"]):
        tid = rng.choice(["tenant_acme", "tenant_globex", "tenant_umbrella"])
        w.customers.append({
            "id": f"cust_{i}", "name": f"Customer {i}",
            "tenant_id": tid, "created_at": "2026-01-01",
            "risk_band": rng.choice(["low", "medium", "high"]),
        })
    for i in range(spec["accounts"]):
        tid = rng.choice(["tenant_acme", "tenant_globex", "tenant_umbrella"])
        cust = rng.choice(w.customers)
        w.accounts.append({
            "id": f"acc_{i}", "account_number": f"ACCT-{i:06d}",
            "tenant_id": tid, "opened_at": "2026-01-01",
            "currency": "USD", "customer_id": cust["id"],
        })
    for i in range(spec["devices"]):
        tid = rng.choice(["tenant_acme", "tenant_globex", "tenant_umbrella"])
        w.devices.append({
            "id": f"dev_{i}", "fingerprint": f"FP-{i:06d}",
            "tenant_id": tid, "first_seen": "2026-01-01",
        })
    for i in range(spec["merchants"]):
        tid = rng.choice(["tenant_acme", "tenant_globex", "tenant_umbrella"])
        w.merchants.append({
            "id": f"merch_{i}", "name": f"Merchant {i}",
            "category": rng.choice(["retail", "travel", "electronics", "gambling"]),
            "tenant_id": tid,
        })

    # transactions (with some fraud injected)
    base = datetime(2026, 9, 1)
    n_tx = spec["transactions"]
    for i in range(n_tx):
        t = base + timedelta(seconds=rng.randint(0, 40 * 86400))
        acc = rng.choice(w.accounts)
        is_fraud = rng.random() < 0.02
        w.transactions.append({
            "id": f"txn_{i}", "amount": round(rng.uniform(10, 5000), 2),
            "currency": "USD", "timestamp": t.isoformat(),
            "type": "payment", "tenant_id": acc["tenant_id"],
            "status": "fraud" if is_fraud else "completed",
            "account_id": acc["id"],
            "device_id": rng.choice(w.devices)["id"],
            "merchant_id": rng.choice(w.merchants)["id"],
            "is_fraud": is_fraud,
        })

    # Build links: transaction -> account -> customer, device, merchant
    # Devices shared across multiple accounts/customers (false association bait)
    shared_devices = rng.sample(w.devices, min(5, len(w.devices)))
    for dev in shared_devices:
        # attach device to several accounts across customers
        for _ in range(rng.randint(2, 4)):
            acc = rng.choice(w.accounts)
            # (link recorded at ingestion time)

    # alerts
    for i in range(max(5, n_tx // 500)):
        tx = rng.choice(w.transactions)
        w.alerts.append({
            "id": f"alt_{i}", "severity": rng.choice(["low", "medium", "high"]),
            "rule_id": f"RULE-{i % 5}", "triggered_at": tx["timestamp"],
            "tenant_id": tx["tenant_id"], "transaction_id": tx["id"],
        })

    # incidents & cases
    for i in range(spec["incidents"]):
        w.incidents.append({
            "id": f"inc_{i}", "title": f"Incident {i}",
            "severity": rng.choice(["medium", "high"]),
            "opened_at": "2026-09-01", "status": "open",
            "tenant_id": "tenant_acme",
            "owned_by": rng.choice(w.teams)["id"],
        })
    for i in range(spec["cases"]):
        tx = rng.choice(w.transactions)
        w.cases.append({
            "id": f"case_{i}", "title": f"Case {i}: {tx['status']} payment",
            "status": "open", "opened_at": tx["timestamp"],
            "tenant_id": tx["tenant_id"], "version": 1,
            "trigger_transaction_id": tx["id"],
        })

    # evidence + ground truth evidence paths
    for i, tx in enumerate(w.transactions[: spec["cases"]]):
        w.evidence.append({
            "id": f"ev_{i}", "description": f"Evidence for {tx['id']}",
            "observed_at": tx["timestamp"], "source_id": f"src_{i}",
            "tenant_id": tx["tenant_id"],
        })
        w.ground_truth.append({
            "case_id": f"case_{i}", "transaction_id": tx["id"],
            "outcome": tx["status"],
            "evidence_path": [
                f"txn_{i}", f"acc_{rng.randrange(spec['accounts'])}",
                f"dev_{rng.randrange(spec['devices'])}",
            ],
            "is_fraud": tx["is_fraud"],
        })

    return w


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def save_world(world: World, directory: Path | None = None) -> List[Path]:
    directory = directory or DATA_DIR
    directory.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for name in [
        "tenants", "customers", "accounts", "devices", "merchants",
        "transactions", "alerts", "incidents", "cases", "policies",
        "employees", "teams", "runbooks", "evidence", "ground_truth",
    ]:
        data = getattr(world, name)
        p = directory / f"{name}.json"
        p.write_text(json.dumps(data, indent=2))
        written.append(p)
    return written


def load_world(directory: Path | None = None) -> Dict[str, List[Dict[str, Any]]]:
    directory = directory or DATA_DIR
    out: Dict[str, List[Dict[str, Any]]] = {}
    for p in directory.glob("*.json"):
        out[p.stem] = json.loads(p.read_text())
    return out
