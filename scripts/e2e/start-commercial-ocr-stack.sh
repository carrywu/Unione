#!/bin/bash
# Start the full commercial OCR E2E stack
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Starting Commercial OCR E2E Stack ==="

# 1. Start PostgreSQL + Redis
echo "[1/5] Starting PostgreSQL + Redis..."
cd "$PROJECT_ROOT"
docker compose -f docker-compose.e2e.yml up -d
sleep 5

# 2. Seed database
echo "[2/5] Seeding database..."
cd "$PROJECT_ROOT/backend"
pnpm seed

# 3. Start pdf-service
echo "[3/5] Starting pdf-service on :8001..."
cd "$PROJECT_ROOT/pdf-service"
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  . "$PROJECT_ROOT/.env"
  set +a
fi
if [ -f "$PROJECT_ROOT/backend/.env" ]; then
  set -a
  . "$PROJECT_ROOT/backend/.env"
  set +a
fi
if [ -f "$PROJECT_ROOT/pdf-service/.env" ]; then
  set -a
  . "$PROJECT_ROOT/pdf-service/.env"
  set +a
fi
COMMERCIAL_OCR_ENABLED="${COMMERCIAL_OCR_ENABLED:-true}" \
COMMERCIAL_OCR_REAL_SMOKE="${COMMERCIAL_OCR_REAL_SMOKE:-false}" \
PDF_PARSE_PRIMARY_PROVIDER="${PDF_PARSE_PRIMARY_PROVIDER:-mock_commercial_ocr}" \
PDF_PARSE_FALLBACK_PROVIDERS="${PDF_PARSE_FALLBACK_PROVIDERS:-local_parser,mock_commercial_ocr}" \
MIMO_ENABLED=false \
MIMO_REAL_SMOKE=false \
TENCENT_OCR_REAL_SMOKE="${TENCENT_OCR_REAL_SMOKE:-false}" \
./.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001 &
PDF_PID=$!
sleep 3

# 4. Start backend
echo "[4/5] Starting backend on :3010..."
cd "$PROJECT_ROOT/backend"
pnpm start:prod &
BACKEND_PID=$!
sleep 5

# 5. Start frontends
echo "[5/5] Starting admin-web on :5174, h5-web on :5173..."
cd "$PROJECT_ROOT/admin-web"
VITE_API_BASE_URL=http://localhost:3010 pnpm exec vite --host 127.0.0.1 --port 5174 &
ADMIN_PID=$!

cd "$PROJECT_ROOT/h5-web"
VITE_API_BASE_URL=http://127.0.0.1:3010 pnpm exec vite --host 127.0.0.1 --port 5173 &
H5_PID=$!

sleep 3

# Health check
echo ""
echo "=== Health Checks ==="
curl -s http://127.0.0.1:8001/health && echo " [pdf-service]"
curl -s http://127.0.0.1:3010/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'status={d[\"data\"][\"status\"]} db={d[\"data\"][\"db_status\"]} redis={d[\"data\"][\"redis_status\"]} pdf={d[\"data\"][\"pdf_service_status\"]}')" 2>/dev/null && echo " [backend]"
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5174/ && echo " [admin-web]"
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5173/ && echo " [h5-web]"

echo ""
echo "=== Stack Ready ==="
echo "PIDs: pdf=$PDF_PID backend=$BACKEND_PID admin=$ADMIN_PID h5=$H5_PID"
echo "Run: pnpm exec playwright test e2e/commercial-ocr-admin.spec.ts e2e/commercial-ocr-h5.spec.ts --trace=on"
echo "Stop: bash scripts/e2e/stop-commercial-ocr-stack.sh"
