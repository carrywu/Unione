#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; WARNINGS=$((WARNINGS+1)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; ERRORS=$((ERRORS+1)); }

echo "=== 行测助手 Health Check ==="
echo ""

# --- 1. Environment ---
echo "[1/6] Environment variables"
check_env() {
  local dir=$1 name=$2
  if [ ! -f "$dir/.env" ] && [ ! -f "$dir/.env.example" ]; then
    fail "$name: no .env or .env.example found"
  elif [ ! -f "$dir/.env" ]; then
    warn "$name: only .env.example exists (copy to .env to use)"
  else
    ok "$name: .env exists"
  fi
}
check_env "backend" "Backend"
check_env "pdf-service" "PDF Service"
check_env "admin-web" "Admin Web"

# --- 2. Dependencies ---
echo ""
echo "[2/6] Dependencies"
check_deps() {
  local dir=$1 name=$2
  if [ ! -d "$dir/node_modules" ]; then
    fail "$name: node_modules missing (run: cd $dir && npm install)"
  else
    ok "$name: node_modules present"
  fi
}
check_deps "backend" "Backend"
check_deps "admin-web" "Admin Web"

if [ ! -d "pdf-service/.venv" ] && [ ! -d "pdf-service/.venv-"* ] 2>/dev/null; then
  warn "PDF Service: no Python venv found (run: cd pdf-service && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt)"
else
  ok "PDF Service: Python venv present"
fi

# --- 3. Port checks ---
echo ""
echo "[3/6] Port availability"
check_port() {
  local port=$1 name=$2
  if ss -tlnp 2>/dev/null | grep -q ":$port " || netstat -tlnp 2>/dev/null | grep -q ":$port "; then
    ok "$name (port $port): in use (service likely running)"
  else
    warn "$name (port $port): not in use (service not running)"
  fi
}
check_port 3000 "Backend"
check_port 8001 "PDF Service"
check_port 5173 "Admin Web"
check_port 3306 "MySQL"
check_port 6379 "Redis"

# --- 4. Backend health ---
echo ""
echo "[4/6] Backend health"
if command -v curl &>/dev/null; then
  if curl -sf http://localhost:3000/api-docs &>/dev/null; then
    ok "Backend API responding at /api-docs"
  else
    warn "Backend not responding at localhost:3000 (start: cd backend && npm run start:dev)"
  fi
else
  warn "curl not available, skipping backend health check"
fi

# --- 5. PDF Service health ---
echo ""
echo "[5/6] PDF Service health"
if command -v curl &>/dev/null; then
  if curl -sf http://localhost:8001/health &>/dev/null; then
    ok "PDF Service responding at /health"
  elif curl -sf http://localhost:8001/docs &>/dev/null; then
    ok "PDF Service responding at /docs"
  else
    warn "PDF Service not responding at localhost:8001 (start: cd pdf-service && uvicorn main:app --port 8001)"
  fi
else
  warn "curl not available, skipping PDF service health check"
fi

# Provider order
if [ -f "pdf-service/.env" ]; then
  PROVIDER_ORDER=$(grep -E '^VISION_AI_PROVIDER_ORDER=' pdf-service/.env | head -1 | cut -d= -f2-)
  if [ -n "$PROVIDER_ORDER" ]; then
    ok "Provider order: $PROVIDER_ORDER"
  else
    warn "VISION_AI_PROVIDER_ORDER not set in pdf-service/.env"
  fi
elif [ -f "pdf-service/.env.example" ]; then
  PROVIDER_ORDER=$(grep -E '^VISION_AI_PROVIDER_ORDER=' pdf-service/.env.example | head -1 | cut -d= -f2-)
  warn "Using .env.example provider order: $PROVIDER_ORDER"
fi

# --- 6. Build check ---
echo ""
echo "[6/6] Build verification"
echo "  Run these commands to verify builds:"
echo "    cd backend && npm run build"
echo "    cd admin-web && npm run build"
echo ""

# --- Summary ---
echo "=== Summary ==="
echo -e "  Errors: ${RED}$ERRORS${NC}"
echo -e "  Warnings: ${YELLOW}$WARNINGS${NC}"
if [ $ERRORS -gt 0 ]; then
  echo -e "\n${RED}Health check FAILED. Fix errors above before proceeding.${NC}"
  exit 1
elif [ $WARNINGS -gt 0 ]; then
  echo -e "\n${YELLOW}Health check passed with warnings. Review above.${NC}"
  exit 0
else
  echo -e "\n${GREEN}Health check PASSED. All services ready.${NC}"
  exit 0
fi
