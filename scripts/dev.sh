#!/usr/bin/env bash
# Start, stop and inspect the three dev services.
#
#   scripts/dev.sh up        # start whatever is not already running, wait for health
#   scripts/dev.sh up a w    # only the agent and the web app
#   scripts/dev.sh down      # stop the ones this script started
#   scripts/dev.sh status    # who is up
#   scripts/dev.sh logs b    # tail one service's log
#
# Services:
#   b = backend  :8000   a = agent  :8001   w = web  :5173
#
# `just backend` and friends each hold a terminal, which is fine when working on
# one service and tedious when a task needs all three - regenerating clients
# needs the backend and the agent, and the browser smoke needs everything. This
# starts what is missing, leaves what is already up alone, and waits until each
# one actually answers rather than guessing with a sleep.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_DIR="${TMPDIR:-/tmp}/agent-graph-dev"
mkdir -p "$RUN_DIR"

ALL="b a w"

# Case lookups rather than associative arrays: those need bash 4, and macOS
# still ships 3.2, so a reader cloning this repo would get "unbound variable"
# instead of a dev server.
name_of() {
  case $1 in
    b) echo backend ;;
    a) echo agent ;;
    w) echo web ;;
  esac
}

port_of() {
  case $1 in
    b) echo 8000 ;;
    a) echo 8001 ;;
    w) echo 5173 ;;
  esac
}

health_of() {
  case $1 in
    b) echo "http://localhost:8000/api/schema/" ;;
    a) echo "http://localhost:8001/health" ;;
    w) echo "http://localhost:5173/" ;;
  esac
}

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

usage() {
  awk 'NR>1 && /^#/{s=$0; sub(/^# ?/,"",s); print s; next} NR>1{exit}' "${BASH_SOURCE[0]}"
  exit 0
}

start_cmd() {
  case $1 in
    b) echo "cd backend && uv run granian --interface asgi --port 8000 --reload helpdesk.config.asgi:application" ;;
    a) echo "cd agent && uv run uvicorn assistant.main:app --port 8001 --reload" ;;
    w) echo "cd web && pnpm dev" ;;
  esac
}

is_up() { curl -fsS -o /dev/null --max-time 3 "$(health_of "$1")" 2>/dev/null; }

log_file() { echo "$RUN_DIR/$(name_of "$1").log"; }
pid_file() { echo "$RUN_DIR/$(name_of "$1").pid"; }

wait_for() {
  local key=$1
  for _ in $(seq 1 90); do
    is_up "$key" && return 0
    # A service that died on startup will never answer; say so straight away
    # rather than after 90 seconds of polling a dead process.
    local pid
    pid=$(cat "$(pid_file "$key")" 2>/dev/null || true)
    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      return 1
    fi
    sleep 1
  done
  return 1
}

# Sets TARGETS, because a function cannot return an array.
parse_targets() {
  TARGETS=""
  for arg in "$@"; do
    if [ -z "$(name_of "$arg")" ]; then
      echo "unknown service: $arg (valid: b a w)" >&2
      exit 2
    fi
    TARGETS="$TARGETS $arg"
  done
  [ -n "$TARGETS" ] || TARGETS="$ALL"
}

cmd_up() {
  failed=""
  parse_targets "$@"

  for key in $TARGETS; do
    if is_up "$key"; then
      echo -e "  ${GREEN}·${NC} $(name_of "$key") already up on :$(port_of "$key")"
      continue
    fi
    echo -e "  ${CYAN}→${NC} starting $(name_of "$key") on :$(port_of "$key")"
    nohup bash -c "$(start_cmd "$key")" >"$(log_file "$key")" 2>&1 &
    echo $! >"$(pid_file "$key")"
  done

  for key in $TARGETS; do
    is_up "$key" && continue
    if wait_for "$key"; then
      echo -e "  ${GREEN}✓${NC} $(name_of "$key") ready"
    else
      echo -e "  ${RED}✗${NC} $(name_of "$key") never answered $(health_of "$key")"
      failed="$failed $key"
    fi
  done

  if [ -n "$failed" ]; then
    for key in $failed; do
      echo -e "\n${YELLOW}─── $(name_of "$key") (last 20 lines) ───${NC}"
      tail -20 "$(log_file "$key")" 2>/dev/null
    done
    echo -e "\n${RED}$(echo $failed | wc -w | tr -d ' ') service(s) failed to start${NC}"
    echo "Infrastructure not running? try: just infra-up && just migrate"
    exit 1
  fi
}

cmd_down() {
  parse_targets "$@"
  for key in $TARGETS; do
    pid=$(cat "$(pid_file "$key")" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      # The recorded pid is the wrapper shell, so take its children with it.
      pkill -P "$pid" 2>/dev/null
      kill "$pid" 2>/dev/null
    fi
    rm -f "$(pid_file "$key")"

    # Then free the port whatever is on it. A server's worker process often
    # carries none of the parent's command line - granian's workers are bare
    # `python3`, so `pkill -f granian` reports success while four of them are
    # still holding :8000 - and a stale worker serving old code is worse than
    # no server at all: it answers health checks and fails on the change you
    # just made.
    port=$(port_of "$key")
    holders=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null)
    if [ -n "$holders" ]; then
      # shellcheck disable=SC2086 - one pid per line, intentionally split
      kill $holders 2>/dev/null
      sleep 1
      holders=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null)
      # shellcheck disable=SC2086
      [ -n "$holders" ] && kill -9 $holders 2>/dev/null
      echo -e "  ${CYAN}→${NC} stopped $(name_of "$key") (:$port)"
    else
      echo -e "  ${YELLOW}·${NC} $(name_of "$key") was not running"
    fi
  done
}

cmd_status() {
  for key in $ALL; do
    if is_up "$key"; then
      echo -e "  ${GREEN}✓${NC} $(name_of "$key") :$(port_of "$key")"
    else
      echo -e "  ${RED}✗${NC} $(name_of "$key") :$(port_of "$key")"
    fi
  done
}

cmd_logs() {
  parse_targets "$@"
  files=""
  for key in $TARGETS; do files="$files $(log_file "$key")"; done
  # shellcheck disable=SC2086 - the paths are ours and contain no spaces
  tail -f $files
}

case "${1:-}" in
  -h|--help|"") usage ;;
  up)     shift; cmd_up "$@" ;;
  down)   shift; cmd_down "$@" ;;
  status) shift; cmd_status ;;
  logs)   shift; cmd_logs "$@" ;;
  *) echo "unknown command: $1 (up, down, status, logs)" >&2; exit 2 ;;
esac
