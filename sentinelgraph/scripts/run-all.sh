#!/usr/bin/env bash
# One-shot: start backend + frontend + load the demo world.
#
#   ./scripts/run-all.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Starting backend + FalkorDB..."
./scripts/run-backend.sh

echo "==> Waiting for backend to be healthy..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "Backend is up."
    break
  fi
  sleep 2
done

echo "==> Loading synthetic demo world into FalkorDB..."
curl -sf -X POST http://localhost:8000/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{"scale":"tiny","seed":20261015,"principal":{"id":"setup","name":"setup","tenant_id":"tenant_acme","roles":["investigator"],"cross_tenant":false}}' >/dev/null
echo "Demo world loaded."

echo "==> Starting dashboard..."
./scripts/run-frontend.sh

echo
echo "============================================"
echo " SentinelGraph is running"
echo "============================================"
echo " Dashboard : http://localhost:3000"
echo " Backend   : http://localhost:8000"
echo " FalkorDB  : localhost:6380"
echo
echo " Open http://localhost:3000 and run an investigation."
echo " Stop everything with:  docker rm -f sg-api sg-falkordb sg-dashboard"
