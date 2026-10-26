"""Investigation (blue-team) agent.

Builds the supported case: queries FalkorDB for connected evidence, constructs
candidate explanations, and proposes claims. Every material claim must link to
source evidence.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..config import DEFAULT_TENANT, MAX_TRAVERSAL_DEPTH
from ..graph import get_graph
from ..security import Principal, authorizer
from .base import Agent, AgentResult


class InvestigationAgent(Agent):
    def __init__(self, tenant_id: str = DEFAULT_TENANT):
        super().__init__("investigator", "investigator", tenant_id)

    def investigate(self, transaction_id: str,
                    depth: int = MAX_TRAVERSAL_DEPTH) -> AgentResult:
        t0 = time.time()
        p = self._principal()
        authorizer.enforce_tenant(p, self.tenant_id)
        g = get_graph()

        notes: List[str] = []
        claims: List[Dict[str, Any]] = []
        evidence: List[Dict[str, Any]] = []

        # 1. Load the transaction + direct neighbours (bounded traversal).
        tx = g.find_node("Transaction", transaction_id)
        if tx is None:
            return AgentResult(False, self.name, self.tenant_id,
                               error=f"transaction {transaction_id} not found",
                               at=time.time() - t0)
        evidence.append({"label": "Transaction", "props": tx})

        notes.append(f"Loaded transaction {transaction_id} "
                     f"(${tx.get('amount')} {tx.get('currency')})")

        # 2. Multi-hop: account -> device -> earlier cases/alerts/merchants.
        rels = ["INVOLVES", "USES_DEVICE", "TRIGGERED", "LINKED_TO"]
        paths = g.traverse("Transaction", transaction_id, rels,
                           depth=depth, tenant_id=self.tenant_id)
        notes.append(f"Traversed {len(paths)} connected paths (depth {depth})")

        # Collect related entities and evidence.
        related: List[Dict[str, Any]] = []
        for path in paths:
            for node in path.nodes:
                if node.get("id") == transaction_id:
                    continue
                related.append(node)
                evidence.append({"label": node.get("label", "Entity"),
                                 "props": node})

        # 3. Build candidate explanation (deterministic rule-based when no LLM).
        explanation = self._build_explanation(tx, related, notes)

        # 4. Propose claims (each linked to evidence).
        for stmt, conf, ev_ids in explanation["claims"]:
            claim = self.propose_claim(stmt, confidence=conf,
                                       evidence_ids=ev_ids,
                                       actor=self.name)
            claims.append(claim.to_dict())
            g.upsert_edge("Claim", claim.claim_id, "HAS_EVIDENCE",
                          "Evidence", ev_ids[0] if ev_ids else "ev_unknown", {})

        return AgentResult(True, self.name, self.tenant_id, claims=claims,
                           evidence=evidence, notes=notes, at=time.time() - t0)

    def _build_explanation(self, tx: Dict[str, Any],
                           related: List[Dict[str, Any]],
                           notes: List[str]) -> Dict[str, Any]:
        """Deterministic candidate explanation. Replace with LLM extraction."""
        claims: List[tuple] = []
        # Claim A: transaction involves its account.
        acc = next((r for r in related if r.get("label") == "Account"), None)
        if acc:
            claims.append((
                f"Transaction {tx['id']} involves account {acc['id']}.",
                0.9, [f"ev_{tx['id'].split('_')[1]}"],
            ))
        # Claim B: device used.
        dev = next((r for r in related if r.get("label") == "Device"), None)
        if dev:
            claims.append((
                f"Transaction {tx['id']} uses device {dev['id']}.",
                0.85, [f"ev_{tx['id'].split('_')[1]}"],
            ))
            # Device reuse claim (weaker — red team should challenge).
            other = [r for r in related if r.get("label") == "Device"
                     and r.get("id") != dev.get("id")]
            if other:
                claims.append((
                    f"Device {dev['id']} appears in multiple connected "
                    f"transactions (possible shared device).",
                    0.6, [],
                ))
                notes.append("Flagged shared-device association for red-team review")
        # Claim C: amount/velocity
        amt = float(tx.get("amount", 0) or 0)
        if amt > 2000:
            claims.append((
                f"High-value transaction ${amt} exceeds secondary-approval threshold.",
                0.8, [],
            ))
        return {"claims": claims}


# Simple alias expected by tests/CLI.
InvestigatorAgent = InvestigationAgent
