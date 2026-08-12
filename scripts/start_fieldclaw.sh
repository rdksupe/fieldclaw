#!/usr/bin/env bash
# Start FieldClaw UI (API on :8000) + Supervisor Hermes gateway.
# Usage:
#   ./scripts/start_fieldclaw.sh
#   ./scripts/start_fieldclaw.sh --no-gateway   # API/UI only
#   ./scripts/start_fieldclaw.sh --no-api       # gateway only
# Ctrl+C stops whatever this script started.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$REPO/apps/api"
HOST="${FIELDCLAW_HOST:-127.0.0.1}"
PORT="${FIELDCLAW_PORT:-8000}"
LOG_DIR="${FIELDCLAW_LOG_DIR:-/tmp/fieldclaw}"
API_LOG="$LOG_DIR/api.log"
GW_LOG="$LOG_DIR/gateway.log"
HERMES_BIN="${HERMES_FIELDCLAW_BIN:-$(command -v hermes-fieldclaw || true)}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes-fieldclaw}"

START_API=1
START_GW=1
REPLACE_GW=1

for arg in "$@"; do
  case "$arg" in
    --no-api) START_API=0 ;;
    --no-gateway|--no-gw) START_GW=0 ;;
    --no-replace) REPLACE_GW=0 ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      echo "unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$LOG_DIR"
API_PID=""
GW_PID=""

cleanup() {
  trap - EXIT INT TERM
  echo ""
  echo "stopping…"
  if [[ -n "${GW_PID}" ]] && kill -0 "$GW_PID" 2>/dev/null; then
    kill "$GW_PID" 2>/dev/null || true
    wait "$GW_PID" 2>/dev/null || true
  fi
  if [[ -n "${API_PID}" ]] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
  echo "stopped (logs: $API_LOG  $GW_LOG)"
}
trap cleanup EXIT INT TERM

if [[ "$START_API" -eq 1 ]]; then
  if ss -tln 2>/dev/null | grep -q ":${PORT} "; then
    echo "port $PORT already in use — freeing it"
    fuser -k "${PORT}/tcp" 2>/dev/null || true
    sleep 0.4
  fi
  echo "starting API/UI on http://${HOST}:${PORT}"
  (
    cd "$API_DIR"
    # Prefer uv if present
    if command -v uv >/dev/null 2>&1; then
      exec uv run uvicorn fieldclaw_api.main:app --host "$HOST" --port "$PORT"
    fi
    if [[ -x "$API_DIR/.venv/bin/uvicorn" ]]; then
      exec "$API_DIR/.venv/bin/uvicorn" fieldclaw_api.main:app --host "$HOST" --port "$PORT"
    fi
    exec python -m uvicorn fieldclaw_api.main:app --host "$HOST" --port "$PORT"
  ) >"$API_LOG" 2>&1 &
  API_PID=$!
  for _ in $(seq 1 40); do
    if curl -sf "http://${HOST}:${PORT}/api/projects" -H "X-API-Key: ${FIELDCLAW_API_KEY:-dev-key-change-me}" >/dev/null 2>&1 \
      || curl -sf "http://${HOST}:${PORT}/" >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$API_PID" 2>/dev/null; then
      echo "API failed to start — see $API_LOG" >&2
      tail -n 40 "$API_LOG" >&2 || true
      exit 1
    fi
    sleep 0.25
  done
  echo "  UI  → http://${HOST}:${PORT}/"
  echo "  log → $API_LOG  (pid $API_PID)"
  PW_FILE="$REPO/data/ui_password.txt"
  if [[ -f "$PW_FILE" ]]; then
    echo "  password → $(cat "$PW_FILE")   (delete $PW_FILE to rotate)"
  fi
fi

if [[ "$START_GW" -eq 1 ]]; then
  if [[ -z "$HERMES_BIN" || ! -x "$HERMES_BIN" ]]; then
    echo "hermes-fieldclaw not found on PATH" >&2
    echo "set HERMES_FIELDCLAW_BIN or install the wrapper" >&2
    exit 1
  fi
  export HERMES_HOME
  echo "starting Hermes gateway (HERMES_HOME=$HERMES_HOME)"
  GW_ARGS=(gateway run)
  if [[ "$REPLACE_GW" -eq 1 ]]; then
    GW_ARGS+=( --replace )
  fi
  (
    export PATH="$(dirname "$HERMES_BIN"):${PATH:-}"
    exec "$HERMES_BIN" "${GW_ARGS[@]}"
  ) >"$GW_LOG" 2>&1 &
  GW_PID=$!
  sleep 1
  if ! kill -0 "$GW_PID" 2>/dev/null; then
    echo "gateway failed to start — see $GW_LOG" >&2
    tail -n 60 "$GW_LOG" >&2 || true
    exit 1
  fi
  echo "  gateway running (pid $GW_PID)"
  echo "  log → $GW_LOG"
  echo "  pair: DM Supervisor bot → paste code in UI Crew tab"
fi

echo ""
echo "FieldClaw up. Ctrl+C to stop."
# Wait on children
while true; do
  if [[ -n "$API_PID" ]] && ! kill -0 "$API_PID" 2>/dev/null; then
    echo "API exited unexpectedly — see $API_LOG" >&2
    exit 1
  fi
  if [[ -n "$GW_PID" ]] && ! kill -0 "$GW_PID" 2>/dev/null; then
    echo "gateway exited unexpectedly — see $GW_LOG" >&2
    exit 1
  fi
  sleep 2
done
