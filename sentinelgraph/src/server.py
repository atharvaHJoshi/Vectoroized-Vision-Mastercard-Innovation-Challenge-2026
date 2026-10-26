"""SentinelGraph FastAPI backend.

Investigation API, orchestration, policy checks. FalkorDB (or in-memory
fallback) is the context/reasoning layer; security enforcement is backend-side.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import DEFAULT_TENANT, ALLOWED_RELATIONSHIPS
from .data import generate_world, save_world, load_world, DATA_DIR
from .graph import get_graph
from .security import authorizer, Principal, claim_store
from .agents import (InvestigatorAgent, RedTeamAgent, VerifierAgent,
                     MemoryManager)

app = FastAPI(title="SentinelGraph", version="0.1.0",
              description="Trust-Aware Investigation and Memory Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class PrincipalIn(BaseModel):
    id: str = "analyst_1"
    name: str = "Analyst 1"
    tenant_id: str = DEFAULT_TENANT
    roles: List[str] = ["investigator"]
    cross_tenant: bool = False


class InvestigateRequest(BaseModel):
    transaction_id: str
    tenant_id: str = DEFAULT_TENANT
    depth: int = 3
    principal: PrincipalIn = PrincipalIn()


class VerifyRequest(BaseModel):
    transaction_id: str
    tenant_id: str = DEFAULT_TENANT
    principal: PrincipalIn = PrincipalIn()


class CommitRequest(BaseModel):
    transaction_id: str
    tenant_id: str = DEFAULT_TENANT
    principal: PrincipalIn = PrincipalIn()


class CompanyBrainRequest(BaseModel):
    incident_id: Optional[str] = None
    tenant_id: str = DEFAULT_TENANT
    principal: PrincipalIn = PrincipalIn()


class EvalRequest(BaseModel):
    scale: str = "tiny"
    seed: int = 20261015
    n_cases: int = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _principal_from(body: PrincipalIn) -> Principal:
    return Principal(id=body.id, name=body.name, tenant_id=body.tenant_id,
                     roles=set(body.roles), cross_tenant=body.cross_tenant)


def _run_pipeline(tx_id: str, principal: Principal,
                  request_tenant: str, depth: int = 3) -> Dict[str, Any]:
    """Full adversarial investigation: blue -> red -> verifier -> memory.

    The *requested* tenant is enforced against the authenticated principal —
    the backend, not the client, owns the tenant boundary.
    """
    authorizer.enforce_tenant(principal, request_tenant)
    tenant_id = request_tenant

    blue = InvestigatorAgent(tenant_id)
    red = RedTeamAgent(tenant_id)
    verifier = VerifierAgent(tenant_id)
    memory = MemoryManager(tenant_id)

    # Blue: build the supported case.
    blue_res = blue.investigate(tx_id, depth=depth)

    # Red: challenge the claims.
    red_res = red.challenge(blue_res.claims, blue_res.evidence, tx_id)

    # Verifier: check both sides against evidence + policy.
    ver_res = verifier.verify(blue_res.claims, red_res.counterarguments,
                              blue_res.evidence, tx_id)

    # Memory: controlled update (promote / supersede / retain uncertainty).
    mem_res = memory.commit(ver_res.claims, red_res.counterarguments, tx_id)

    return {
        "transaction_id": tx_id,
        "tenant_id": tenant_id,
        "blue": blue_res.to_dict(),
        "red": red_res.to_dict(),
        "verifier": ver_res.to_dict(),
        "memory": mem_res.to_dict(),
        "verdict": ver_res.decision,
        "depth": depth,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    g = get_graph()
    return {
        "status": "ok",
        "graph_backend": "falkordb" if g.using_falkordb else "memory_fallback",
        "falkordb_available": g.using_falkordb,
    }


@app.post("/api/ingest")
def ingest(scale: str = Query("tiny"), seed: int = 20261015,
           principal: PrincipalIn = PrincipalIn()):
    """Load synthetic world into the graph (backend-enforced tenant scoping)."""
    p = _principal_from(principal)
    authorizer.enforce_tenant(p, p.tenant_id)
    world = generate_world(scale=scale, seed=seed)
    g = get_graph()
    count = 0
    for label, rows in [
        ("Customer", world.customers), ("Account", world.accounts),
        ("Device", world.devices), ("Merchant", world.merchants),
        ("Transaction", world.transactions), ("Alert", world.alerts),
        ("Incident", world.incidents), ("Case", world.cases),
        ("Policy", world.policies), ("Employee", world.employees),
        ("Team", world.teams), ("Runbook", world.runbooks),
        ("Evidence", world.evidence),
    ]:
        for row in rows:
            g.upsert_node(label, row)
            count += 1
    # Edges: transaction -> account/customer/device/merchant; alert -> transaction
    for tx in world.transactions:
        acc = next((a for a in world.accounts if a["id"] == tx["account_id"]), None)
        if acc:
            g.upsert_edge("Transaction", tx["id"], "INVOLVES", "Account", acc["id"])
            cust = next((c for c in world.customers if c["id"] == acc["customer_id"]), None)
            if cust:
                g.upsert_edge("Account", acc["id"], "BELONGS_TO", "Customer", cust["id"])
        dev = next((d for d in world.devices if d["id"] == tx["device_id"]), None)
        if dev:
            g.upsert_edge("Transaction", tx["id"], "USES_DEVICE", "Device", dev["id"])
        mer = next((m for m in world.merchants if m["id"] == tx["merchant_id"]), None)
        if mer:
            g.upsert_edge("Transaction", tx["id"], "LINKED_TO", "Merchant", mer["id"])
    for al in world.alerts:
        g.upsert_edge("Alert", al["id"], "TRIGGERED", "Transaction", al["transaction_id"])
    return {"ingested": count, "scale": scale, "tenant": p.tenant_id}


@app.post("/api/investigate")
def investigate(req: InvestigateRequest,
                x_tenant: Optional[str] = Header(None)):
    # Backend enforces tenant from the authenticated principal; header cannot override.
    principal = _principal_from(req.principal)
    if x_tenant and x_tenant != req.tenant_id:
        raise HTTPException(400, "tenant header mismatch")
    try:
        result = _run_pipeline(req.transaction_id, principal, req.tenant_id,
                           depth=req.depth)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return result


@app.post("/api/verify")
def verify(req: VerifyRequest):
    principal = _principal_from(req.principal)
    try:
        authorizer.enforce_tenant(principal, req.tenant_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    # Re-run pipeline and return just the verifier output.
    result = _run_pipeline(req.transaction_id, principal, req.tenant_id)
    return {"verifier": result["verifier"], "verdict": result["verdict"]}


@app.post("/api/commit")
def commit(req: CommitRequest):
    principal = _principal_from(req.principal)
    try:
        authorizer.enforce_tenant(principal, req.tenant_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    result = _run_pipeline(req.transaction_id, principal, req.tenant_id)
    return {"memory": result["memory"], "version": result["memory"]["decision"]}


@app.post("/api/company-brain")
def company_brain(req: CompanyBrainRequest):
    """Connect incident -> policy -> owner/runbook (Company Brain view)."""
    principal = _principal_from(req.principal)
    try:
        authorizer.enforce_tenant(principal, req.tenant_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    g = get_graph()
    out: Dict[str, Any] = {"incident": None, "policy": None, "owner": None,
                           "runbook": None, "connected": []}
    if req.incident_id:
        inc = g.find_node("Incident", req.incident_id)
        if inc:
            out["incident"] = inc
            owner = g.find_nodes_by_prop("Team", "id", inc.get("owned_by", ""))
            if owner:
                out["owner"] = owner[0]
                g.upsert_edge("Incident", req.incident_id, "OWNED_BY", "Team",
                              inc.get("owned_by", ""), {})
            # policies referenced
            policies = g.find_nodes_by_prop("Policy", "tenant_id", req.tenant_id)
            out["policy"] = policies[:3] if policies else None
            # runbooks
            books = g.find_nodes_by_prop("Runbook", "tenant_id", req.tenant_id)
            out["runbook"] = books[:2] if books else None
    return out


@app.post("/api/eval")
def run_eval(req: EvalRequest):
    """Run the 3-baseline benchmark comparison on synthetic cases."""
    from .eval.runner import run_benchmark
    return run_benchmark(scale=req.scale, seed=req.seed, n_cases=req.n_cases)


@app.get("/api/audit")
def audit(tenant_id: str = DEFAULT_TENANT):
    return {"audit": authorizer.get_audit(tenant_id)}


@app.get("/api/graph/stats")
def graph_stats():
    g = get_graph()
    return {"backend": "falkordb" if g.using_falkordb else "memory",
            "allowed_relationships": sorted(ALLOWED_RELATIONSHIPS),
            "max_traversal_depth": 3}


@app.on_event("startup")
def _startup():
    # Seed a small default world on boot so the dashboard opens populated.
    try:
        existing = load_world(DATA_DIR)
        if not existing:
            world = generate_world(scale="tiny", seed=20261015)
            save_world(world, DATA_DIR)
    except Exception:
        pass
