#!/usr/bin/env bash
# Bring the whole lab up in one command: fresh snapshot if none exists, then
# a snapshot-seeded backend (populated dashboard) + the frontend dashboard.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f data/snapshot/world.pkl ]; then
    echo "no snapshot yet — building one (one-time, ~2 min at demo scale)..."
    python sg.py snapshot --scale demo
fi

if ! curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "starting backend (seeded) on :8000 ..."
    nohup python sg.py serve > /tmp/sg-serve.log 2>&1 &
    # give the seed a few seconds (world + detector reload, no rebuild)
    for _ in $(seq 1 20); do
        curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
        sleep 0.5
    done
fi

if ! curl -sf -o /dev/null http://127.0.0.1:3000/ ; then
    echo "starting frontend on :3000 ..."
    (cd frontend && nohup npm run dev > /tmp/sg-frontend.log 2>&1 &)
fi

echo
echo "backend  : http://127.0.0.1:8000/   health: $(curl -s http://127.0.0.1:8000/api/health | python -c 'import sys,json;print(json.load(sys.stdin)["status"])')"
echo "dashboard: http://127.0.0.1:3000/"
echo "  (dashboard opens fully populated via snapshot seeding)"