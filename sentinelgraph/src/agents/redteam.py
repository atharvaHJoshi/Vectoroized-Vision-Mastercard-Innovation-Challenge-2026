"""Red-team agent.

Challenges the investigator's claims: finds alternative explanations, missing
evidence, possible false positives (e.g. shared legitimate device). Outputs
counterargument claims.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from ..config import DEFAULT_TENANT
from ..graph import get_graph
from ..security import authorizer
from .base import Agent, AgentResult


class RedTeamAgent(Agent):
    def __init__(self, tenant_id: str = DEFAULT_TENANT):
        super().__init__("red_team", "red_team", tenant_id)

    def challenge(self, claims: List[Dict[str, Any]],
                  evidence: List[Dict[str, Any]],
                  transaction_id: str) -> AgentResult:
        t0 = time.time()
        p = self._principal()
        authorizer.enforce_tenant(p, self.tenant_id)
        g = get_graph()

        counterarguments: List[Dict[str, Any]] = []
        notes: List[str] = []

        # Build an index of evidence by claim evidence ids.
        ev_ids = set()
        for c in claims:
            for eid in c.get("evidence_ids", []):
                ev_ids.add(eid)

        for c in claims:
            stmt = c.get("statement", "")
            conf = float(c.get("confidence", 0))
            # Challenge low-confidence unsupported claims.
            if not c.get("evidence_ids") and conf < 0.7:
                counter = {
                    "id": f"counter_{int(time.time()*1000)}",
                    "statement": f"Claim lacks supporting evidence: {stmt[:80]}",
                    "target_claim": c.get("claim_id"),
                    "strength": 0.8,
                    "reason": "unsupported_claim",
                    "created_by": self.name,
                }
                counterarguments.append(counter)
                notes.append(f"Challenged unsupported claim: {stmt[:60]}")

            # Shared-device false association challenge.
            if "shared device" in stmt.lower() or "multiple connected" in stmt.lower():
                counter = {
                    "id": f"counter_{int(time.time()*1000)}",
                    "statement": ("Device sharing alone does not establish fraud; "
                                  "the device may be used by multiple legitimate "
                                  "customers."),
                    "target_claim": c.get("claim_id"),
                    "strength": 0.85,
                    "reason": "false_association",
                    "created_by": self.name,
                }
                counterarguments.append(counter)
                notes.append("Raised false-association challenge on shared device")

        # Missing evidence: if a transaction has no linked alert/case, flag it.
        has_alert = any(e.get("label") == "Alert" for e in evidence)
        if not has_alert:
            notes.append("No linked alert found — missing evidence; consider abstention")

        # Persist counterarguments as claims.
        for ca in counterarguments:
            self.propose_claim(ca["statement"], confidence=ca["strength"],
                               evidence_ids=[], actor=self.name)

        return AgentResult(True, self.name, self.tenant_id,
                           counterarguments=counterarguments, notes=notes,
                           at=time.time() - t0)
