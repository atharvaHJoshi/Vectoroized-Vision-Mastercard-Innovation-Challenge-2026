#!/usr/bin/env bash
# Run the SentinelGraph backend inside Docker.
#
#   ./scripts/run-backend.sh          # start backend on :8000 (uses pre-built image)
#   ./scripts/run-backend.sh --build  # rebuild image from Dockerfile
set -euo pipefail

cd "$(dirname "$0")/.."

BUILD=0
if [[ "${1:-}" == "--build" ]]; then
  BUILD=1
fi

NETWORK="sg-net"

if [[ "$BUILD" == "1" ]]; then
  echo "==> Building backend image..."
  docker build -t sentinelgraph:latest .
fi

# Ensure network exists
docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK"

# Ensure FalkorDB is running
if ! docker ps --format '{{.Names}}' | grep -q sg-falkordb; then
  echo "==> Starting FalkorDB..."
  docker run -d --name sg-falkordb --network "$NETWORK" -p 6380:6379 falkordb/falkordb:latest
fi

# Wait for FalkorDB
echo "==> Waiting for FalkorDB..."
for i in $(seq 1 30); do
  if docker exec sg-falkordb redis-cli -p 6379 ping >/dev/null 2>&1; then
    echo "FalkorDB is ready."
    break
  fi
  sleep 1
done

# Remove old backend if exists
docker rm -f sg-api 2>/dev/null || true

echo "==> Starting backend API..."
docker run -d --name sg-api --network "$NETWORK" -p 8000:8000 \
  -e FALKORDB_HOST=sg-falkordb \
  -e FALKORDB_PORT=6380 \
  -e SG_DEFAULT_TENANT=tenant_acme \
  -e SG_GRAPH_FALLBACK=1 \
  sentinelgraph:latest

echo
echo "Backend API:  http://localhost:8000"
echo "FalkorDB:     localhost:6380"
echo
echo "Health check: curl http://localhost:8000/api/health"
echo "Stop:         docker rm -f sg-api sg-falkordb"
