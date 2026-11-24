#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
python="${ANNOTATION_PYTHON:-python3}"
port="${ANNOTATION_PORT:-5194}"
data="${ANNOTATION_STATE_DIR:-$root/.local}"
umask 077
mkdir -p "$data"
data="$(cd "$data" && pwd)"
db="$data/pg"
if [ ! -f "$root/dist/index.html" ]; then
  echo "Build the frontend first: npm ci && npm run build" >&2
  exit 1
fi
"$python" -c 'import psycopg2' || { echo 'Install requirements in a Python venv, or set ANNOTATION_PYTHON.' >&2; exit 1; }
for binary in initdb pg_ctl; do command -v "$binary" >/dev/null || { echo "PostgreSQL executable $binary is required." >&2; exit 1; }; done
if [ ! -f "$db/PG_VERSION" ]; then
  initdb -D "$db" -U annotation --auth-local=trust --auth-host=reject --encoding=UTF8 --locale=C >"$data/init.log"
fi
socket="$(mktemp -d /tmp/annpg.XXXXXXXX)"
started=
child=
cleanup() {
  if [ -n "$child" ]; then kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi
  if [ -n "$started" ]; then pg_ctl -D "$db" -m fast -w stop >/dev/null; fi
  rmdir "$socket" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if ! pg_ctl -D "$db" -l "$data/postgres.log" -w start -o "-h '' -k $socket -p 55494 -c unix_socket_permissions=0700" >/dev/null; then
  echo "Could not start the project database. See $data/postgres.log" >&2
  exit 1
fi
started=1
export ANNOTATION_DSN="host=$socket port=55494 user=annotation dbname=postgres connect_timeout=4"
"$python" server/seed.py
"$python" server/app.py --port "$port" &
child=$!
wait "$child"
