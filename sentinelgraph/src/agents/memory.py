"""Memory manager.

Controls the memory update lifecycle: promotes supported findings, retains
uncertainty, supersedes stale facts, and logs changes. Corrected facts persist
across sessions via versioned MemoryVersion + Correction nodes.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..config import DEFAULT_TENANT
from ..graph import get_graph
from ..security import authorizer, claim_store, Principal
from .base import Agent, AgentResult


class MemoryManager(Agent):
    def __init__(self, tenant_id: str = DEFAULT_TENANT):
        super().__init__("memory_manager", "memory_manager", tenant_id)

    def commit(self, claims: List[Dict[str, Any]],
               counterarguments: List[Dict[str, Any]],
               transaction_id: str) -> AgentResult:
        t0 = time.time()
        p = self._principal()
        authorizer.enforce_tenant(p, self.tenant_id)
        g = get_graph()

        notes: List[str] = []
        promoted: List[Dict[str, Any]] = []
        superseded: List[Dict[str, Any]] = []

        # Determine current memory version for this case/transaction.
        version_nodes = g.find_nodes_by_prop("MemoryVersion", "entity_id",
                                             transaction_id)
        current_version = max([int(n.get("version", 0)) for n in version_nodes],
                              default=0)
        new_version = current_version + 1

        g.upsert_node("MemoryVersion", {
            "id": f"mv_{transaction_id}_{new_version}",
            "version": new_version, "entity_id": transaction_id,
            "at": str(time.time()), "tenant_id": self.tenant_id,
        })

        for c in claims:
            cid = c.get("claim_id")
            state = c.get("state", "PROPOSED")
            claim_obj = claim_store.get(cid) if cid else None
            final_state = claim_obj.state if claim_obj else state

            # Promote supported/verified findings into trusted memory.
            if final_state in ("SUPPORTED", "VERIFIED"):
                g.upsert_node("Claim", {
                    "id": cid, "statement": c.get("statement", ""),
                    "state": final_state, "confidence": c.get("confidence", 0),
                    "version": new_version, "tenant_id": self.tenant_id,
                })
                promoted.append(c)
                notes.append(f"Promoted claim {cid} to memory v{new_version}")

            # Supersede stale PROPOSED claims that were contradicted.
            if final_state == "CONTRADICTED":
                g.upsert_node("Correction", {
                    "id": f"corr_{cid}", "reason": "contradicted by evidence",
                    "at": str(time.time()), "tenant_id": self.tenant_id,
                })
                g.upsert_edge("Claim", cid, "SUPERSEDES",
                              "Correction", f"corr_{cid}", {})
                superseded.append(c)
                notes.append(f"Superseded contradicted claim {cid}")

        # Retain uncertainty: PROPOSED claims stay as hypotheses, not facts.
        hypotheses = [c for c in claims
                      if (claim_store.get(c.get("claim_id")).state
                          if claim_store.get(c.get("claim_id")) else c.get("state"))
                      == "PROPOSED"]
        for h in hypotheses:
            notes.append(f"Retained hypothesis {h.get('claim_id')} (unverified)")

        return AgentResult(True, self.name, self.tenant_id,
                           claims=promoted, counterarguments=counterarguments,
                           notes=notes, decision={
                               "version": new_version,
                               "promoted": len(promoted),
                               "superseded": len(superseded),
                               "hypotheses_retained": len(hypotheses),
                           }, at=time.time() - t0)
