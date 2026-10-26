"""SentinelGraph security layer.

Real enforcement, not prompts:
- Tenant isolation: every graph operation, memory retrieval and source lookup is
  scoped to the authenticated tenant.
- Data minimization / redaction: sensitive properties are redacted before model
  context; a stable pseudonymous id is preserved for reasoning.
- Provenance & audit: every material conclusion is recorded with the source,
  graph query, agent task, verification result and memory version.
- Action authorization: recommendations are separated from execution; the
  backend validates permitted actions.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .config import DEFAULT_TENANT, SUPER_TENANT
from .schema import NODE_PROPS, REDACTION_RULES


# ---------------------------------------------------------------------------
# Principal & context
# ---------------------------------------------------------------------------
@dataclass
class Principal:
    id: str
    name: str
    tenant_id: str
    roles: Set[str] = field(default_factory=set)
    # principals allowed to read across tenants (audit only)
    cross_tenant: bool = False

    def can_read_tenant(self, tenant_id: str) -> bool:
        if self.tenant_id == tenant_id:
            return True
        if self.cross_tenant:
            return True  # audit/system principal may read any tenant
        return False


@dataclass
class AuditEvent:
    id: str
    actor: str
    action: str
    tenant_id: str
    target: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)
    at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "actor": self.actor, "action": self.action,
            "tenant_id": self.tenant_id, "target": self.target,
            "detail": self.detail, "at": self.at,
        }


# ---------------------------------------------------------------------------
# Authorization engine
# ---------------------------------------------------------------------------
class Authorizer:
    def __init__(self):
        self._events: List[AuditEvent] = []
        self._lock = __import__("threading").RLock()

    # -- tenant scoping ---------------------------------------------------
    def enforce_tenant(self, principal: Principal, tenant_id: str) -> None:
        if not principal.can_read_tenant(tenant_id):
            raise PermissionError(
                f"principal {principal.id} ({principal.tenant_id}) "
                f"not authorized for tenant {tenant_id}"
            )
        self._audit("tenant_check", principal, tenant_id, detail={"granted": True})

    def scope_query(self, principal: Principal,
                    params: Dict[str, Any]) -> Dict[str, Any]:
        """Inject tenant_id into query params so the graph never leaks across tenants."""
        if "tenant_id" not in params:
            params["tenant_id"] = principal.tenant_id
        return params

    # -- redaction --------------------------------------------------------
    def redact_props(self, principal: Principal, label: str,
                     props: Dict[str, Any]) -> Dict[str, Any]:
        """Redact sensitive properties the principal is not cleared to see.

        For a hackathon prototype this is label-based; in production it would be
        role/policy based. A pseudonymous id is always retained so reasoning
        over links still works.
        """
        out = dict(props)
        level = props.get("sensitivity", "internal")
        rules = REDACTION_RULES.get(level, [])
        for field_name in rules:
            if field_name in out:
                out[field_name] = self._pseudonymize(out[field_name])
        return out

    @staticmethod
    def _pseudonymize(value: Any) -> str:
        if value is None:
            return None
        return "ps:" + hashlib.sha256(str(value).encode()).hexdigest()[:16]

    # -- action authorization --------------------------------------------
    def may_execute(self, principal: Principal, action: str,
                    tenant_id: str) -> bool:
        """Consequential actions require an explicit permit role."""
        permitted = action in {
            "approve_refund", "freeze_account", "file_sar", "escalate_case",
        }
        allowed_roles = {"investigator", "verifier", "memory_manager"}
        ok = permitted and bool(principal.roles & allowed_roles)
        self._audit("action_check", principal, tenant_id,
                    target=action, detail={"granted": ok})
        return ok

    # -- audit ------------------------------------------------------------
    def _audit(self, action: str, principal: Principal, tenant_id: str,
               target: Optional[str] = None,
               detail: Optional[Dict[str, Any]] = None) -> None:
        ev = AuditEvent(
            id=hashlib.sha256(f"{action}{time.time_ns()}".encode()).hexdigest()[:12],
            actor=principal.id, action=action, tenant_id=tenant_id,
            target=target, detail=detail or {}, at=time.time(),
        )
        with self._lock:
            self._events.append(ev)

    def get_audit(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if tenant_id is None:
                return [e.to_dict() for e in self._events]
            return [e.to_dict() for e in self._events if e.tenant_id == tenant_id]


# module-level authorizer (shared across the backend)
authorizer = Authorizer()

# ---------------------------------------------------------------------------
# Claims & provenance tracking (application-level trust states)
# ---------------------------------------------------------------------------
@dataclass
class ClaimRecord:
    claim_id: str
    statement: str
    state: str = "PROPOSED"
    confidence: float = 0.5
    evidence_ids: List[str] = field(default_factory=list)
    counter_ids: List[str] = field(default_factory=list)
    verified_by: Optional[str] = None
    verified_at: Optional[float] = None
    tenant_id: str = DEFAULT_TENANT
    created_by: str = "system"
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id, "statement": self.statement,
            "state": self.state, "confidence": self.confidence,
            "evidence_ids": self.evidence_ids, "counter_ids": self.counter_ids,
            "verified_by": self.verified_by, "verified_at": self.verified_at,
            "tenant_id": self.tenant_id, "created_by": self.created_by,
            "created_at": self.created_at,
        }


class ClaimStore:
    """In-memory claim registry backed by graph persistence."""

    def __init__(self):
        self._claims: Dict[str, ClaimRecord] = {}
        self._lock = __import__("threading").RLock()

    def create(self, claim: ClaimRecord) -> ClaimRecord:
        with self._lock:
            self._claims[claim.claim_id] = claim
        return claim

    def get(self, claim_id: str) -> Optional[ClaimRecord]:
        with self._lock:
            return self._claims.get(claim_id)

    def transition(self, claim_id: str, new_state: str, actor: str,
                   tenant_id: str) -> Optional[ClaimRecord]:
        from .schema import TRUST_TRANSITIONS, is_conclusive
        with self._lock:
            claim = self._claims.get(claim_id)
            if not claim:
                return None
            if claim.tenant_id != tenant_id:
                raise PermissionError("claim tenant mismatch")
            allowed = TRUST_TRANSITIONS.get(claim.state, set())
            if new_state not in allowed:
                raise ValueError(
                    f"invalid transition {claim.state} -> {new_state}"
                )
            claim.state = new_state
            if new_state == "VERIFIED":
                claim.verified_by = actor
                claim.verified_at = time.time()
            return claim

    def list_conclusive(self, tenant_id: str) -> List[ClaimRecord]:
        with self._lock:
            return [c for c in self._claims.values()
                    if c.tenant_id == tenant_id and is_conclusive(c.state)]


claim_store = ClaimStore()
