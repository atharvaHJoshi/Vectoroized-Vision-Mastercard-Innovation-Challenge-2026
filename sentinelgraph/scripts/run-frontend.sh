#!/usr/bin/env bash
# Run the SentinelGraph frontend (Next.js dashboard) inside Docker.
#
#   ./scripts/run-frontend.sh   # start dashboard on :3000
set -euo pipefail

cd "$(dirname "$0")/.."

NETWORK="sg-net"

docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK"

docker rm -f sg-dashboard 2>/dev/null || true

echo "==> Starting dashboard (Next.js)..."
docker run -d --name sg-dashboard --network "$NETWORK" -p 3000:3000 \
  -e SG_API_URL=http://sg-api:8000 \
  -v "$(pwd)/dashboard:/app" \
  -v sg-dashboard-modules:/app/node_modules \
  node:20-alpine \
  sh -c "npm install --no-audit --no-fund && npm run dev"

echo
echo "Dashboard:  http://localhost:3000   (proxies /api to backend :8000)"
echo
echo "Make sure the backend is running first:"
echo "  ./scripts/run-backend.sh"
echo
echo "Stop:       docker rm -f sg-dashboard"
