# SentinelGraph

Trust-Aware Investigation and Memory Engine — an adversarially verified context
graph for secure AI investigations.

SentinelGraph connects transactions, accounts, devices, alerts, incidents,
documents, employees, policies, and previous investigations. AI agents
investigate these relationships, challenge the evidence, preserve verified
corrections, and return source-backed findings subject to access control.

This is a new product built from the strongest ideas in **Adversia**
(adversarial red/blue feedback), **SovereignGuard** (privacy, tenant isolation,
provenance, governance) and **Graph Hacks + FalkorDB** (connected, queryable
context + evolving memory). It is not a port of either existing project.

> Working name. Availability and trademark status not checked.

## The core idea

An agent's output is a **claim, not a fact**. Claims move through explicit
trust states — `PROPOSED → SUPPORTED → VERIFIED → CONTRADICTED → SUPERSEDED` —
and may only influence a final conclusion when `SUPPORTED` or `VERIFIED`. A
red-team agent challenges every claim; a verifier checks both sides against
source records and permitted evidence; a memory manager promotes supported
findings, retains uncertainty, and supersedes stale facts.

## Three tracks, one engine

| Track | Capability |
|-------|------------|
| **1 — Investigate** | Multi-hop FalkorDB traversal, evidence-backed paths, red-team challenge, verification gate before action. |
| **2 — Remember** | Versioned facts, corrections, structured agent handoffs; corrected facts persist without erasing history. |
| **3 — Company Brain** | Incident → policy → owner/runbook, with backend-enforced tenant scoping and redaction. |

## Quick start

### Option A — Docker Compose (recommended; FalkorDB is the primary graph)

```bash
cd sentinelgraph
docker compose up -d falkordb backend
python sg.py ingest --scale tiny        # load synthetic world into FalkorDB
python sg.py serve --host 0.0.0.0 --port 8000
# dashboard:
cd frontend && npm install && npm run dev   # :3001
```

### Option B — Standalone (no FalkorDB; in-memory graph fallback)

The backend degrades to a deterministic in-memory graph when FalkorDB is
unavailable (`SG_GRAPH_FALLBACK=1`). FalkorDB remains the primary database in
compose/production; the fallback is demo/dev-only.

```bash
cd sentinelgraph
pip install -r requirements.txt
python sg.py ingest --scale tiny
python sg.py serve
open http://127.0.0.1:8000/api/health
```

### CLI

```bash
python sg.py ingest --scale tiny
python sg.py investigate txn_0 --tenant tenant_acme
python sg.py eval --scale tiny --n-cases 8
```

## Graph model & Cypher queries

See [`GRAPH_MODEL.md`](GRAPH_MODEL.md) for the node labels, edge types,
property contracts, trust-state transitions, temporal semantics, tenant
boundaries and the bounded Cypher queries the backend uses.

## Security (enforced backend-side)

1. **Tenant isolation** — every graph operation, memory retrieval and source
   lookup is scoped to the authenticated tenant; the backend never lets an LLM
   pick its own tenant boundary.
2. **Data minimization / redaction** — sensitive properties are pseudonymized
   before model context; a stable pseudonymous id preserves link reasoning.
3. **Provenance & audit** — every material conclusion records the source, graph
   query, agent task, verification result and memory version (`/api/audit`).
4. **Prompt-injection / memory-poisoning resistance** — retrieved documents and
   messages are treated as untrusted data; they supply evidence but cannot
   override policy, permissions or verification.
5. **Action authorization** — recommendations are separated from execution; the
   backend validates permitted actions (`approve_refund`, `freeze_account`, …).

## Evaluation

Run the three-baseline comparison on shared synthetic cases:

```bash
python sg.py eval --scale tiny --n-cases 8
```

Baseline A = conventional retrieval → LLM.  
Baseline B = FalkorDB graph traversal → LLM (no adversarial verification).  
SentinelGraph = graph → claim verification → adversarial challenge → governed
memory.

Metrics: investigation accuracy, evidence coverage, claim-support rate,
counterevidence recall, unauthorized-disclosure rate, latency. Results are
written to `data/eval_results/`.

## Acceptance criteria (MVP)

0/8 at start → target 8/8 by end of build:

1. Graph-native reasoning — at least one answer depends on a multi-hop
   FalkorDB query.
2. Evidence traceability — every material finding links to source evidence +
   verification status.
3. Adversarial challenge — a red-team test identifies/flags an unsupported
   claim.
4. Persistent correction — a corrected fact changes a later answer without
   erasing history.
5. Company Brain — incident + policy + owner/runbook connected in one answer.
6. Permission enforcement — automated cross-tenant access test is denied.
7. Benchmark comparison — Baseline A / B / SentinelGraph on the same cases.
8. Submission readiness — repo, setup guide, graph model, Cypher queries,
   demo, track declarations complete.

## Notes

- The LLM is optional: extraction/reasoning fall back to deterministic,
  rule-based logic when no model API key is configured, so the demo runs
  offline. Plug an LLM into the agent `propose_claim`/`verify` methods to
  upgrade.
- Fine-tuning is not a required component; build time is better spent on the
  graph, verification loop and evaluation.
