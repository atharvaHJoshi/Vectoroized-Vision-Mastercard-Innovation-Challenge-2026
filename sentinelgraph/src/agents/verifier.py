"""Verifier agent.

Compares investigator claims and red-team counterarguments against source
records and permitted evidence. Promotes supported claims to SUPPORTED/VERIFIED,
marks contradictions CONTRADICTED.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from ..config import DEFAULT_TENANT
from ..graph import get_graph
from ..security import authorizer, claim_store, Principal
from .base import Agent, AgentResult


class VerifierAgent(Agent):
    def __init__(self, tenant_id: str = DEFAULT_TENANT):
        super().__init__("verifier", "verifier", tenant_id)

    def verify(self, claims: List[Dict[str, Any]],
               counterarguments: List[Dict[str, Any]],
               evidence: List[Dict[str, Any]],
               transaction_id: str) -> AgentResult:
        t0 = time.time()
        p = self._principal()
        authorizer.enforce_tenant(p, self.tenant_id)
        g = get_graph()

        notes: List[str] = []
        verified: List[Dict[str, Any]] = []
        contradicted: List[Dict[str, Any]] = []

        # Index evidence by id for quick lookup.
        ev_by_id: Dict[str, Dict[str, Any]] = {}
        for e in evidence:
            ev_by_id[e.get("props", {}).get("id", e.get("id"))] = e

        for c in claims:
            cid = c.get("claim_id")
            stmt = c.get("statement", "")
            ev_ids = c.get("evidence_ids", [])
            conf = float(c.get("confidence", 0))

            # A claim is supported only if it cites evidence we can retrieve.
            supported = all(eid in ev_by_id for eid in ev_ids) if ev_ids else False

            # Check counterarguments against this claim.
            relevant_counters = [ca for ca in counterarguments
                                 if ca.get("target_claim") == cid]
            has_strong_counter = any(
                float(ca.get("strength", 0)) >= conf for ca in relevant_counters)

            from ..security import claim_store as cs
            existing = cs.get(cid) if cid else None
            current_state = existing.state if existing else "PROPOSED"

            new_state = current_state
            if supported and not has_strong_counter:
                new_state = "SUPPORTED" if conf >= 0.7 else "PROPOSED"
            elif has_strong_counter:
                new_state = "CONTRADICTED"
            else:
                new_state = "PROPOSED"

            # Only allow valid transitions.
            if new_state != current_state:
                try:
                    updated = claim_store.transition(cid, new_state,
                                                     self.name, self.tenant_id)
                    if updated:
                        g.upsert_node("Claim", {
                            "id": cid, "statement": stmt, "state": new_state,
                            "confidence": conf, "tenant_id": self.tenant_id,
                        })
                        notes.append(f"Claim {cid}: {current_state} -> {new_state}")
                except ValueError:
                    notes.append(f"Claim {cid}: blocked transition {current_state} -> {new_state}")

            if new_state == "CONTRADICTED":
                contradicted.append(c)
            elif new_state in ("SUPPORTED", "VERIFIED"):
                verified.append(c)

        result = AgentResult(True, self.name, self.tenant_id, claims=verified,
                             counterarguments=counterarguments, notes=notes,
                             at=time.time() - t0)
        result.decision = {
            "verdict": "SUPPORTED" if verified and not contradicted else
                       "CONTRADICTED" if contradicted else "INSUFFICIENT_EVIDENCE",
            "supported_count": len(verified),
            "contradicted_count": len(contradicted),
        }
        return result
