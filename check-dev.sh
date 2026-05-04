#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/carry/project2"
LOG_DIR="$PROJECT_ROOT/logs/dev"
mkdir -p "$LOG_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/check-$TS.log"

log() {
  echo "[$(date '+%F %T')] $*" | tee -a "$RUN_LOG"
}

http_code() {
  local url="$1"
  curl -s -o /dev/null -w "%{http_code}" "$url" || echo "000"
}

log "check-dev begin"

echo "" | tee -a "$RUN_LOG"
echo "=== Docker containers ===" | tee -a "$RUN_LOG"
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | tee -a "$RUN_LOG"

echo "" | tee -a "$RUN_LOG"
echo "=== Ports (3010/8001/5173/5174/5432/6379) ===" | tee -a "$RUN_LOG"
lsof -i :3010 -i :8001 -i :5173 -i :5174 -i :5432 -i :6379 2>/dev/null | tee -a "$RUN_LOG" || true

echo "" | tee -a "$RUN_LOG"
echo "=== HTTP checks ===" | tee -a "$RUN_LOG"
PDF_CODE="$(http_code 'http://localhost:8001/health')"
BACKEND_DOC_CODE="$(http_code 'http://localhost:3010/api-docs')"
ADMIN_CODE="$(http_code 'http://localhost:5173/')"
H5_CODE="$(http_code 'http://localhost:5174/')"

echo "pdf-service /health : $PDF_CODE" | tee -a "$RUN_LOG"
echo "backend /api-docs  : $BACKEND_DOC_CODE" | tee -a "$RUN_LOG"
echo "admin-web /        : $ADMIN_CODE" | tee -a "$RUN_LOG"
echo "h5-web /           : $H5_CODE" | tee -a "$RUN_LOG"

echo "" | tee -a "$RUN_LOG"
echo "=== DB key table counts (quiz_app) ===" | tee -a "$RUN_LOG"
if docker exec project2-postgres pg_isready -U postgres >/dev/null 2>&1; then
  docker exec -i project2-postgres psql -U postgres -d quiz_app -Atc "
    SELECT 'answer_sources', count(*) FROM answer_sources
    UNION ALL SELECT 'materials', count(*) FROM materials
    UNION ALL SELECT 'parse_tasks', count(*) FROM parse_tasks
    UNION ALL SELECT 'question_ai_action_log', count(*) FROM question_ai_action_log
    UNION ALL SELECT 'question_banks', count(*) FROM question_banks
    UNION ALL SELECT 'questions', count(*) FROM questions
    UNION ALL SELECT 'system_configs', count(*) FROM system_configs
    UNION ALL SELECT 'user_question_books', count(*) FROM user_question_books
    UNION ALL SELECT 'user_records', count(*) FROM user_records
    UNION ALL SELECT 'users', count(*) FROM users;
  " 2>/dev/null | tee -a "$RUN_LOG" || true
else
  echo "postgres not ready" | tee -a "$RUN_LOG"
fi

echo "" | tee -a "$RUN_LOG"
echo "=== Service quick status ===" | tee -a "$RUN_LOG"
[[ "$PDF_CODE" == "200" ]] && echo "pdf-service: PASS" | tee -a "$RUN_LOG" || echo "pdf-service: FAIL" | tee -a "$RUN_LOG"
[[ "$BACKEND_DOC_CODE" == "200" ]] && echo "backend: PASS" | tee -a "$RUN_LOG" || echo "backend: FAIL" | tee -a "$RUN_LOG"
[[ "$ADMIN_CODE" == "200" ]] && echo "admin-web: PASS" | tee -a "$RUN_LOG" || echo "admin-web: FAIL" | tee -a "$RUN_LOG"
[[ "$H5_CODE" == "200" ]] && echo "h5-web: PASS" | tee -a "$RUN_LOG" || echo "h5-web: FAIL" | tee -a "$RUN_LOG"

log "check-dev done; run-log=$RUN_LOG"
