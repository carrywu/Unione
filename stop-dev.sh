#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/carry/project2"
LOG_DIR="$PROJECT_ROOT/logs/dev"
PID_DIR="$LOG_DIR/pids"
mkdir -p "$LOG_DIR" "$PID_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
RUN_LOG="$LOG_DIR/stop-$TS.log"

log() {
  echo "[$(date '+%F %T')] $*" | tee -a "$RUN_LOG"
}

stop_pid_if_running() {
  local pid="$1"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    for _ in $(seq 1 10); do
      if ! kill -0 "$pid" >/dev/null 2>&1; then
        return 0
      fi
      sleep 1
    done
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
}

stop_by_port_project() {
  local name="$1"
  local port="$2"
  local must_contain="$3"
  local touched=0

  mapfile -t pids < <(lsof -ti TCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if (( ${#pids[@]} == 0 )); then
    return 1
  fi

  for pid in "${pids[@]}"; do
    local cmd
    cmd="$(ps -p "$pid" -o cmd= 2>/dev/null || true)"
    if [[ "$cmd" == *"$must_contain"* ]]; then
      log "stop $name by port :$port pid=$pid"
      stop_pid_if_running "$pid"
      touched=1
    else
      log "WARN: :$port pid=$pid not in project path, skip: $cmd"
    fi
  done

  (( touched == 1 ))
}

stop_by_pattern() {
  local name="$1"
  local pattern="$2"
  local pidfile="$PID_DIR/${name}.pid"
  local stopped=0

  if [[ -f "$pidfile" ]]; then
    local pid
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
      log "try stop $name by pidfile pid=$pid"
      stop_pid_if_running "$pid"
      stopped=1
    fi
    rm -f "$pidfile"
  fi

  mapfile -t pids < <(pgrep -f "$pattern" || true)
  if (( ${#pids[@]} > 0 )); then
    log "try stop $name by pattern, pids=${pids[*]}"
    for pid in "${pids[@]}"; do
      stop_pid_if_running "$pid"
      stopped=1
    done
  fi

  if (( stopped == 1 )); then
    log "$name stopped"
  else
    log "$name not running"
  fi
}

log "stop-dev begin"
stop_by_port_project "h5-web" 5174 "/home/carry/project2/h5-web" || true
stop_by_port_project "admin-web" 5173 "/home/carry/project2/admin-web" || true
stop_by_port_project "backend" 3010 "/home/carry/project2/backend" || true
stop_by_port_project "pdf-service" 8001 "/home/carry/project2/pdf-service" || true

stop_by_pattern "h5-web" "/home/carry/project2/h5-web/.*vite"
stop_by_pattern "admin-web" "/home/carry/project2/admin-web/.*vite"
stop_by_pattern "backend" "/home/carry/project2/backend/.*(nest|dist/main)"
stop_by_pattern "pdf-service" "/home/carry/project2/pdf-service/.*uvicorn main:app --host 0.0.0.0 --port 8001"

log "docker volumes untouched (no remove)"
log "uploads untouched; migration package untouched"
log "stop-dev done; run-log=$RUN_LOG"
