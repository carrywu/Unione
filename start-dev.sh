#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/carry/project2"
LOG_DIR="$PROJECT_ROOT/logs/dev"
PID_DIR="$LOG_DIR/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/start-$TS.log"
PNPM_BIN="$HOME/.local/bin/pnpm"

ensure_pnpm() {
  if [[ -x "$PNPM_BIN" ]]; then
    return 0
  fi
  mkdir -p "$HOME/.local/bin"
  corepack enable --install-directory "$HOME/.local/bin" >/dev/null 2>&1 || true
  corepack prepare pnpm@10.33.2 --activate >/dev/null 2>&1 || true
  if [[ ! -x "$PNPM_BIN" ]]; then
    echo "[ERROR] pnpm bootstrap failed at $PNPM_BIN" | tee -a "$RUN_LOG"
    return 1
  fi
}

log() {
  echo "[$(date '+%F %T')] $*" | tee -a "$RUN_LOG"
}

is_listening() {
  local port="$1"
  lsof -ti TCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

pid_for_port() {
  local port="$1"
  lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

cmd_for_pid() {
  local pid="$1"
  ps -p "$pid" -o cmd= 2>/dev/null || true
}

ensure_container() {
  local name="$1"
  local image="$2"
  local run_args="$3"

  if docker ps -aq -f name="^${name}$" | grep -q .; then
    docker start "$name" >/dev/null || true
    log "docker container ready: $name"
  else
    log "docker container missing, creating: $name"
    # shellcheck disable=SC2086
    docker run -d --name "$name" $run_args "$image" >/dev/null
    log "docker container created: $name"
  fi
}

start_service() {
  local name="$1"
  local port="$2"
  local expected_substr="$3"
  local workdir="$4"
  local cmd="$5"
  local logfile="$LOG_DIR/${name}.log"
  local pidfile="$PID_DIR/${name}.pid"

  if is_listening "$port"; then
    local pid
    pid="$(pid_for_port "$port")"
    local running_cmd
    running_cmd="$(cmd_for_pid "$pid")"
    if [[ "$running_cmd" == *"$expected_substr"* ]]; then
      log "$name already running on :$port (pid=$pid), skip"
      return 0
    fi
    log "WARN: port :$port already used by non-project process (pid=$pid): $running_cmd"
    log "WARN: skip starting $name to avoid killing unrelated process"
    return 1
  fi

  log "starting $name on :$port"
  {
    echo ""
    echo "==== start $name at $(date '+%F %T') ===="
    echo "workdir=$workdir"
    echo "cmd=$cmd"
  } >> "$logfile"

  nohup bash -lc "cd '$workdir' && $cmd" >> "$logfile" 2>&1 &
  local pid=$!
  echo "$pid" > "$pidfile"

  for _ in $(seq 1 40); do
    if is_listening "$port"; then
      log "$name started (pid=$pid), log=$logfile"
      return 0
    fi
    sleep 1
  done

  log "ERROR: $name did not listen on :$port within timeout; check $logfile"
  return 1
}

log "start-dev begin"

ensure_container "project2-postgres" "postgres:16-alpine" "-e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=password -e POSTGRES_DB=quiz_app -p 5432:5432 -v project2-pgdata:/var/lib/postgresql/data"
ensure_container "project2-redis" "redis:7-alpine" "-p 6379:6379 -v project2-redisdata:/data"

if docker exec project2-postgres pg_isready -U postgres >/dev/null 2>&1; then
  log "postgres ready"
else
  log "WARN: postgres not ready yet"
fi

if docker exec project2-redis redis-cli ping >/dev/null 2>&1; then
  log "redis ready"
else
  log "WARN: redis not ready yet"
fi

ensure_pnpm || true

start_service "pdf-service" 8001 "project2/pdf-service/.venv/bin/uvicorn main:app" "$PROJECT_ROOT/pdf-service" "source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8001" || true
start_service "backend" 3010 "project2/backend" "$PROJECT_ROOT/backend" "${PNPM_BIN} run start:dev" || true
start_service "admin-web" 5173 "project2/admin-web" "$PROJECT_ROOT/admin-web" "${PNPM_BIN} run dev" || true
start_service "h5-web" 5174 "project2/h5-web" "$PROJECT_ROOT/h5-web" "${PNPM_BIN} run dev" || true

log "access URLs:"
log "  admin-web:    http://localhost:5173"
log "  h5-web:       http://localhost:5174"
log "  backend docs: http://localhost:3010/api-docs"
log "  pdf health:   http://localhost:8001/health"
log "start-dev done; run-log=$RUN_LOG"
