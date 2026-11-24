#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
port="${ANNOTATION_TEST_PORT:-5195}"
python="${ANNOTATION_PYTHON:-python3}"
testdir="$(mktemp -d /tmp/annotation-check.XXXXXXXX)"
child=
cleanup(){
  if [ -n "$child" ]; then kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi
  # Remove only the directory created for this exact run.
  rm -rf -- "$testdir"
}
trap cleanup EXIT
export ANNOTATION_STATE_DIR="$testdir" ANNOTATION_PORT="$port"
bash scripts/run-local.sh > "$testdir/run.log" 2>&1 &
child=$!
for i in {1..80}; do
  if grep -q "Evidence Desk: http://127.0.0.1:$port" "$testdir/run.log"; then break; fi
  if ! kill -0 "$child" 2>/dev/null; then cat "$testdir/run.log"; exit 1; fi
  sleep .2
done
"$python" tests/triage_check.py
if ! "$python" tests/api_smoke.py "$port"; then cat "$testdir/run.log"; exit 1; fi
if [ "${1:-}" = "--browser" ]; then
  if ! node tests/ui_smoke.mjs "$port"; then cat "$testdir/run.log"; exit 1; fi
fi
