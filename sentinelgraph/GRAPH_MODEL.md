# SentinelGraph Graph Model & Cypher Queries

FalkorDB is the system's **context and reasoning layer** — not a visualization
database that can be removed without changing the product.

## Node labels

Domain: `Customer`, `Account`, `Transaction`, `Merchant`, `Device`, `Alert`,
`Incident`, `Person`, `Document`, `Policy`

Evidence: `Evidence`, `SourceRecord`, `EvidenceSpan`, `ModelOutput`

Claims & verification: `Claim`, `VerificationRun`, `Counterargument`, `Decision`

Memory & coordination: `Case`, `AgentTask`, `Handoff`, `MemoryVersion`,
`Correction`

Governance: `Tenant`, `Principal`, `Role`, `PolicyDecision`, `AuditEvent`

Org knowledge: `Employee`, `Team`, `Project`, `Runbook`, `Ticket`, `Service`,
`DecisionRecord`

## Edge types (allowlisted)

`INVOLVES`, `USES_DEVICE`, `TRIGGERED`, `LINKED_TO`, `SUPPORTED_BY`,
`CONTRADICTED_BY`, `SUPERSEDES`, `INVESTIGATED_IN`, `REFERENCES`, `OWNED_BY`,
`PRODUCED`, `PART_OF`, `ISSUED_BY`, `REVIEWED_BY`, `BELONGS_TO`,
`HAS_CLAIM`, `HAS_EVIDENCE`, `NEXT_VERSION_OF`, `CORRECTS`, `GOVERNED_BY`,
`ASSIGNED_TO`, `CITES`

Only relationships in this allowlist may be traversed; an LLM is never allowed
to issue unrestricted Cypher.

## Trust-state machine (application-level, not built-in FalkorDB)

`PROPOSED → SUPPORTED → VERIFIED → CONTRADICTED → SUPERSEDED`

Only `SUPPORTED` and `VERIFIED` may influence a final conclusion.

## Temporal / versioning

Time-sensitive facts carry `valid_from`, `valid_to`, `observed_at` and
`version_id`. This distinguishes when something was true from when the system
learned it.

## Minimal property contract

Only the minimum data required for reasoning is stored in graph properties.
Protected source content is retrieved through the authorized backend (see
`security.py` redaction rules).

Example: `Transaction {id, amount, currency, timestamp, type, tenant_id, status}`
— sensitive `account_number` lives on `Account` and is redacted/pseudonymized
for non-authorized principals.

## Bounded Cypher queries (backend contracts)

### Multi-hop investigation (the core query)

```
MATCH p =
  (t:Transaction {id: $transaction_id})
  -[:INVOLVES|USES_DEVICE|LINKED_TO|TRIGGERED*1..3]-
  (related)
WHERE ALL(x IN nodes(p) WHERE x.tenant_id = $tenant_id)
RETURN p
LIMIT 50
```

This is the query that "materially changes the investigation result": it
returns connected accounts, devices, merchants and alerts within 3 hops,
scoped to the tenant.

### Find connected claims + evidence

```
MATCH (c:Claim {id: $claim_id})-[:SUPPORTED_BY|CONTRADICTED_BY]->(e:Evidence)
WHERE c.tenant_id = $tenant_id
RETURN c, e
```

### Versioned memory lookup

```
MATCH (mv:MemoryVersion {entity_id: $tx_id})
RETURN mv ORDER BY mv.version DESC LIMIT 1
```

### Cross-tenant denial (enforced in code)

Every query injects `tenant_id` from the authenticated principal. Queries that
omit it are rejected by the authorizer before reaching FalkorDB.

## Where the graph does real work

`Transaction → Account → Device → Earlier Case → Evidence → Policy`

A keyword search finds each record independently. The graph lets the agent
traverse relationships, constrain depth, inspect associated evidence, and find
a connected explanation — then verify each link before acting.
