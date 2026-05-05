#!/bin/bash
# Stop the commercial OCR E2E stack
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Stopping Commercial OCR E2E Stack ==="

# Kill node/python processes on known ports
for PORT in 8001 3010 5174 5173; do
  PID=$(lsof -ti:$PORT 2>/dev/null || true)
  if [ -n "$PID" ]; then
    echo "Killing process on :$PORT (PID $PID)"
    kill $PID 2>/dev/null || true
  fi
done

# Stop Docker containers
echo "Stopping PostgreSQL + Redis..."
cd "$PROJECT_ROOT"
docker compose -f docker-compose.e2e.yml down

echo "=== Stack Stopped ==="
