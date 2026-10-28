#!/usr/bin/env bash
# The occasional real-model battery: every probe that burns tokens, in one run.
# These call the live models many times; run them when a prompt or grading change
# lands, not in CI. Requires the compose dev profile with LiteLLM on :4000.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
echo "==> triage probe (fast model, routing cases)"
uv run --project backend python tools/triage_probe.py "$@" || fail=1

echo "==> persona probe (all personas, real rewrites; catches foreign flavour)"
for persona in clerk jester marvin pirate sergeant; do
  echo "--- persona: $persona"
  uv run --project backend python "tools/persona_probe.py" --persona "$persona" || fail=1
done

echo "==> grading eval (both roles, the whole eval set; slow)"
uv run --project backend python tools/grading_eval.py || fail=1

echo "==> asks eval (every ask pasted back; none may earn its own point)"
uv run --project backend python tools/asks_eval.py || fail=1

if [ "$fail" -ne 0 ]; then
  echo "battery FAILED"
  exit 1
fi
echo "battery passed"
