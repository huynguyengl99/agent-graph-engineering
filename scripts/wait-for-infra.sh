#!/usr/bin/env bash
# Wait until Postgres and Redis actually accept connections.
#
# `docker compose up -d` returns as soon as the containers exist, which is well
# before Postgres is listening. `just setup` ran `migrate` straight afterwards
# and failed on a cold machine - the one path where a reader of the series has
# no idea whether they did something wrong.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

wait_for() {
  name=$1
  shift
  for _ in $(seq 1 60); do
    if "$@" >/dev/null 2>&1; then
      echo "   $name ready"
      return 0
    fi
    sleep 1
  done
  echo "   $name never became ready; try: docker compose logs $name" >&2
  return 1
}

failed=0
wait_for postgres docker compose exec -T postgres pg_isready -U postgres || failed=1
wait_for redis docker compose exec -T redis redis-cli ping || failed=1
exit $failed
