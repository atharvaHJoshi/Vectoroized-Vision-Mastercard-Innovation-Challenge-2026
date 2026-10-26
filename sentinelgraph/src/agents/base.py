"""Base agent class and result contract."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import DEFAULT_TENANT
from ..security import authorizer, claim_store, ClaimRecord, Principal


@dataclass
class AgentResult:
    ok: bool
    agent: str
    tenant_id: str
    claims: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    counterarguments: List[Dict[str, Any]] = field(default_factory=list)
    decision: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None
    at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok, "agent": self.agent, "tenant_id": self.tenant_id,
            "claims": self.claims, "evidence": self.evidence,
            "counterarguments": self.counterarguments, "decision": self.decision,
            "notes": self.notes, "error": self.error, "at": self.at,
        }


class Agent:
    """Base class. All agent outputs are claims, not facts."""

    def __init__(self, name: str, role: str, tenant_id: str = DEFAULT_TENANT):
        self.name = name
        self.role = role
        self.tenant_id = tenant_id

    def _principal(self) -> Principal:
        from ..security import Principal
        return Principal(id=self.name, name=self.name, tenant_id=self.tenant_id,
                         roles={self.role})

    def _log(self, action: str, detail: Dict[str, Any]) -> None:
        p = self._principal()
        authorizer.enforce_tenant(p, self.tenant_id)
        authorizer._audit(action, p, self.tenant_id, detail=detail)

    def propose_claim(self, statement: str, confidence: float = 0.5,
                      evidence_ids: Optional[List[str]] = None,
                      actor: Optional[str] = None) -> ClaimRecord:
        """Create a PROPOSED claim and persist it to graph + claim store."""
        from ..graph import get_graph
        from ..security import claim_store
        import time
        cid = f"claim_{int(time.time()*1000)}"
        claim = ClaimRecord(
            claim_id=cid, statement=statement, state="PROPOSED",
            confidence=confidence, evidence_ids=evidence_ids or [],
            tenant_id=self.tenant_id, created_by=actor or self.name,
            created_at=time.time(),
        )
        claim_store.create(claim)
        g = get_graph()
        g.upsert_node("Claim", {
            "id": cid, "statement": statement, "state": "PROPOSED",
            "confidence": confidence, "created_at": str(claim.created_at),
            "created_by": actor or self.name, "tenant_id": self.tenant_id,
        })
        if actor:
            g.upsert_edge("AgentTask", f"task_{actor}", "PRODUCED",
                          "Claim", cid, {})
        self._log("propose_claim", {"claim_id": cid, "statement": statement,
                                    "state": "PROPOSED"})
        return claim
