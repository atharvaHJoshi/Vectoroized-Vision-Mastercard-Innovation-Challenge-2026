# Setup — SentinelGraph

## Prerequisites

- Python 3.10+ (3.12 recommended for Docker)
- Node.js 18+ (for the dashboard)
- Docker + Docker Compose (for FalkorDB + full stack)

## 1. Clone / locate the project

The project lives under `sentinelgraph/` in the hackathon repo.

## 2. Backend (Python)

```bash
cd sentinelgraph
pip install -r requirements.txt
```

Optional: install FalkorDB Python client for the production path:

```bash
pip install falkordb   # already in requirements.txt
```

FalkorDB itself runs via Docker Compose (`falkordb/falkordb:latest`). When it
is unavailable the backend uses an in-memory graph fallback (`SG_GRAPH_FALLBACK=1`).

## 3. Run with Docker (recommended — FalkorDB is the primary graph)

The quickest way to run everything:

```bash
cd sentinelgraph

# Start backend + FalkorDB
./scripts/run-backend.sh

# Load the synthetic demo world
docker compose run --rm ingest

# Start the dashboard
./scripts/run-frontend.sh

# Or everything at once:
./scripts/run-all.sh
```

This starts:
- FalkorDB on `localhost:6380`
- Backend API on `http://localhost:8000`
- Next.js dashboard on `http://localhost:3000`

### Backend only
```bash
./scripts/run-backend.sh          # with FalkorDB
./scripts/run-backend.sh --no-falkordb   # in-memory graph fallback
```

### Frontend only
```bash
./scripts/run-frontend.sh
```

## 4. Run standalone (no Docker)

```bash
cd sentinelgraph
pip install -r requirements.txt
python sg.py ingest --scale tiny
python sg.py serve                    # API on :8000
open http://127.0.0.1:8000/api/health
```

### CLI examples

```bash
# One adversarial investigation (blue → red → verifier → memory)
python sg.py investigate txn_0 --tenant tenant_acme

# Three-baseline benchmark (A retrieval / B graph / SentinelGraph)
python sg.py eval --scale tiny --n-cases 8

# Ingest a larger world
python sg.py ingest --scale demo --seed 20261015
```

## 5. Dashboard

```bash
cd frontend
npm install
npm run dev   # :3001 standalone / :3000 under docker compose
```

## 6. Environment variables

```bash
cd frontend
npm install
npm run dev   # :3001 (proxies /api to backend :8000)
```

## 7. Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FALKORDB_HOST` | `127.0.0.1` | FalkorDB host |
| `FALKORDB_PORT` | `6379` | FalkorDB port |
| `SG_DEFAULT_TENANT` | `tenant_acme` | default tenant |
| `SG_GRAPH_FALLBACK` | `1` | allow in-memory graph when FalkorDB absent |

## 8. Test data

`python sg.py ingest` writes JSON to `data/synthetic/` and loads it into the
graph. Evaluation results go to `data/eval_results/`.

## 9. Acceptance criteria (MVP)

See `README.md` — the 8 done criteria map to the hackathon tracks:
investigate / remember / company brain + benchmark + submission readiness.
