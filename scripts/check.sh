#!/usr/bin/env bash
# Every project's checks, in parallel, with one summary.
#
# Usage:
#   scripts/check.sh          # all three
#   scripts/check.sh ba       # backend and agent only
#   scripts/check.sh -e w     # everything except web
#   scripts/check.sh --fix    # let the formatters and linters write
#
# Projects:
#   b = backend: ruff, mypy, django check, schema
#   a = agent:   ruff, mypy
#   w = web:     eslint, prettier, tsc
#
# Sequential `just check` stops at the first failure, so a change that breaks
# two projects takes two runs to find out. This runs them together and prints
# the output of the ones that failed, which is the only output worth reading.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ALL="b a w"

# Case lookups rather than associative arrays: those need bash 4, and macOS
# still ships 3.2, so a reader cloning this repo would get "unbound variable"
# instead of a check run.
name_of() {
  case $1 in
    b:ruff) echo "backend: ruff" ;;
    b:mypy) echo "backend: mypy" ;;
    b:django) echo "backend: django check" ;;
    b:schema) echo "backend: openapi schema" ;;
    a:ruff) echo "agent: ruff" ;;
    a:mypy) echo "agent: mypy" ;;
    w:eslint) echo "web: eslint" ;;
    w:prettier) echo "web: prettier" ;;
    w:tsc) echo "web: tsc" ;;
  esac
}

project_of() {
  case $1 in
    b) echo backend ;;
    a) echo agent ;;
    w) echo web ;;
  esac
}

tasks_of() {
  case $1 in
    b) echo "b:ruff b:mypy b:django b:schema" ;;
    a) echo "a:ruff a:mypy" ;;
    w) echo "w:eslint w:prettier w:tsc" ;;
  esac
}

usage() {
  awk 'NR>1 && /^#/{s=$0; sub(/^# ?/,"",s); print s; next} NR>1{exit}' "${BASH_SOURCE[0]}"
  exit 0
}

EXCLUDE=false
FIX=false
LETTERS=""
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage ;;
    -e|--exclude) EXCLUDE=true ;;
    --fix) FIX=true ;;
    -*) echo "unknown flag: $arg" >&2; exit 2 ;;
    *) LETTERS+="$arg" ;;
  esac
done

SELECTED=""
i=0
while [ "$i" -lt "${#LETTERS}" ]; do
  letter=$(printf '%s' "$LETTERS" | cut -c $((i + 1)))
  if [ -z "$(project_of "$letter")" ]; then
    echo "unknown project: $letter (valid: b a w)" >&2
    exit 2
  fi
  SELECTED="$SELECTED $letter"
  i=$((i + 1))
done

if [ -z "$SELECTED" ]; then
  TARGETS="$ALL"
elif [ "$EXCLUDE" = true ]; then
  TARGETS=""
  for candidate in $ALL; do
    keep=true
    for chosen in $SELECTED; do
      [ "$candidate" = "$chosen" ] && keep=false && break
    done
    [ "$keep" = true ] && TARGETS="$TARGETS $candidate"
  done
else
  TARGETS="$SELECTED"
fi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

run_task() {
  local key=$1 log="$OUT/$1.log"
  case $key in
    b:ruff)
      if [[ "$FIX" == true ]]; then
        ( cd backend && uv run ruff check --fix . && uv run ruff format . ) >"$log" 2>&1
      else
        ( cd backend && uv run ruff check . && uv run ruff format --check . ) >"$log" 2>&1
      fi
      ;;
    b:mypy)   ( cd backend && uv run mypy . ) >"$log" 2>&1 ;;
    b:django) ( cd backend && uv run python manage.py check ) >"$log" 2>&1 ;;
    b:schema)
      ( cd backend && uv run python manage.py spectacular --validate --fail-on-warn \
          >/dev/null ) >"$log" 2>&1
      ;;
    a:ruff)
      if [[ "$FIX" == true ]]; then
        ( cd agent && uv run ruff check --fix . && uv run ruff format . ) >"$log" 2>&1
      else
        ( cd agent && uv run ruff check . && uv run ruff format --check . ) >"$log" 2>&1
      fi
      ;;
    a:mypy)   ( cd agent && uv run mypy assistant ) >"$log" 2>&1 ;;
    w:eslint)
      if [[ "$FIX" == true ]]; then
        ( cd web && pnpm lint:fix ) >"$log" 2>&1
      else
        ( cd web && pnpm lint ) >"$log" 2>&1
      fi
      ;;
    w:prettier)
      if [[ "$FIX" == true ]]; then
        ( cd web && pnpm format:fix ) >"$log" 2>&1
      else
        ( cd web && pnpm format ) >"$log" 2>&1
      fi
      ;;
    w:tsc)    ( cd web && pnpm typecheck ) >"$log" 2>&1 ;;
  esac
  echo $? >"$OUT/$key.exit"
}

TASKS=""
for target in $TARGETS; do
  TASKS="$TASKS $(tasks_of "$target")"
done
COUNT=$(echo "$TASKS" | wc -w | tr -d ' ')

if [ "$FIX" = true ]; then
  echo -e "${CYAN}Running $COUNT checks (writing fixes)${NC}\n"
else
  echo -e "${CYAN}Running $COUNT checks${NC}\n"
fi

for task in $TASKS; do run_task "$task" & done
wait

echo -e "${CYAN}── results ──${NC}"
FAILED=""
for task in $TASKS; do
  code=$(cat "$OUT/$task.exit" 2>/dev/null || echo 1)
  if [ "$code" = "0" ]; then
    echo -e "  ${GREEN}✓${NC} $(name_of "$task")"
  else
    echo -e "  ${RED}✗${NC} $(name_of "$task")"
    FAILED="$FAILED $task"
  fi
done
echo

if [ -n "$FAILED" ]; then
  for task in $FAILED; do
    echo -e "${YELLOW}─── $(name_of "$task") ───${NC}"
    cat "$OUT/$task.log"
    echo
  done
  echo -e "${RED}Failed: $(echo "$FAILED" | wc -w | tr -d ' ')/$COUNT${NC}"
  exit 1
fi

echo -e "${GREEN}All $COUNT checks passed${NC}"
