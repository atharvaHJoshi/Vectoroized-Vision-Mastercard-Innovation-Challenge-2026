# SentinelGraph

Trust-Aware Investigation and Memory Engine — an adversarially verified context
graph for secure AI investigations.

An agent's output is treated as a *claim*, not a fact: claims move through
`PROPOSED → SUPPORTED → VERIFIED → CONTRADICTED → SUPERSEDED`, and only supported
or verified claims may influence a conclusion.

## Contents

| Path | Description |
|---|---|
| [`sentinelgraph/`](sentinelgraph/README.md) | The application — Python backend, agents, and Next.js dashboard |
| [`sentinelgraph/SETUP.md`](sentinelgraph/SETUP.md) | Local setup and run instructions |
| [`sentinelgraph/GRAPH_MODEL.md`](sentinelgraph/GRAPH_MODEL.md) | Graph schema, trust states, and access model |

Quick start:

```bash
cd sentinelgraph
pip install -r requirements.txt
python cli.py ingest
./scripts/run-backend.sh
./scripts/run-frontend.sh
```

> This repository previously hosted the MasterCard 2026 Vectoroized Vision
> project. Those files were superseded and remain available in the git history.
