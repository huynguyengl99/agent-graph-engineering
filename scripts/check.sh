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

ALL=(b a w)
declare -A NAMES=(
  [b:ruff]="backend: ruff"
  [b:mypy]="backend: mypy"
  [b:django]="backend: django check"
  [b:schema]="backend: openapi schema"
  [a:ruff]="agent: ruff"
  [a:mypy]="agent: mypy"
  [w:eslint]="web: eslint"
  [w:prettier]="web: prettier"
  [w:tsc]="web: tsc"
)
declare -A PROJECTS=([b]="backend" [a]="agent" [w]="web")

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

SELECTED=()
for (( i=0; i<${#LETTERS}; i++ )); do
  letter="${LETTERS:$i:1}"
  [[ -z "${PROJECTS[$letter]+x}" ]] && {
    echo "unknown project: $letter (valid: b a w)" >&2
    exit 2
  }
  SELECTED+=("$letter")
done

if [[ ${#SELECTED[@]} -eq 0 ]]; then
  TARGETS=("${ALL[@]}")
elif [[ "$EXCLUDE" == true ]]; then
  TARGETS=()
  for candidate in "${ALL[@]}"; do
    keep=true
    for chosen in "${SELECTED[@]}"; do
      [[ "$candidate" == "$chosen" ]] && keep=false && break
    done
    [[ "$keep" == true ]] && TARGETS+=("$candidate")
  done
else
  TARGETS=("${SELECTED[@]}")
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

TASKS=()
for target in "${TARGETS[@]}"; do
  case $target in
    b) TASKS+=(b:ruff b:mypy b:django b:schema) ;;
    a) TASKS+=(a:ruff a:mypy) ;;
    w) TASKS+=(w:eslint w:prettier w:tsc) ;;
  esac
done

# The two linters in a project would race to rewrite the same files.
if [[ "$FIX" == true ]]; then
  echo -e "${CYAN}Running ${#TASKS[@]} checks (writing fixes)${NC}\n"
else
  echo -e "${CYAN}Running ${#TASKS[@]} checks${NC}\n"
fi

for task in "${TASKS[@]}"; do run_task "$task" & done
wait

echo -e "${CYAN}── results ──${NC}"
FAILED=()
for task in "${TASKS[@]}"; do
  code=$(cat "$OUT/$task.exit" 2>/dev/null || echo 1)
  if [[ "$code" == "0" ]]; then
    echo -e "  ${GREEN}✓${NC} ${NAMES[$task]}"
  else
    echo -e "  ${RED}✗${NC} ${NAMES[$task]}"
    FAILED+=("$task")
  fi
done
echo

if (( ${#FAILED[@]} )); then
  for task in "${FAILED[@]}"; do
    echo -e "${YELLOW}─── ${NAMES[$task]} ───${NC}"
    cat "$OUT/$task.log"
    echo
  done
  echo -e "${RED}Failed: ${#FAILED[@]}/${#TASKS[@]}${NC}"
  exit 1
fi

echo -e "${GREEN}All ${#TASKS[@]} checks passed${NC}"
