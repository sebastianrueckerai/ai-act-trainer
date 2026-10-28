#!/usr/bin/env bash
# Starts trainer + postgres from the compose file, waits for readiness, tears down.
# --public brings up the public overlay instead (Caddy, self-signed on localhost).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV="${ENV_FILE:-$ROOT/.env}"
COMPOSE=(docker compose -f "$ROOT/deploy/docker-compose.yml" --env-file "$ENV")
SERVICES=(trainer postgres)
URL=http://localhost:8000
CURL=(curl -s)
bound_files=(deploy/litellm/config.yaml)

if [ "${1:-}" = "--public" ]; then
  export PUBLIC_HOST=localhost
  # Production mode refuses the repo default secret; a fresh one per smoke run is fine.
  export SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 24)}"
  COMPOSE=(docker compose -f "$ROOT/deploy/docker-compose.yml" -f "$ROOT/deploy/docker-compose.public.yml"
    --profile dev --profile public --env-file "$ENV")
  SERVICES=(trainer postgres litellm caddy)
  URL="https://localhost:${CADDY_HTTPS_PORT:-443}"
  CURL=(curl -sk)
  bound_files+=(deploy/litellm/config.public.yaml deploy/Caddyfile)
fi

# Every bind mount in the compose file must exist as a file before compose runs.
# Docker creates a missing bind source as a root-owned directory, and on a path
# under a deleted worktree that leaves a tree nobody can remove without root.
for bound in "${bound_files[@]}"; do
  [ -f "$ROOT/$bound" ] || {
    echo "missing $ROOT/$bound: compose would create it as a root-owned directory" >&2
    exit 1
  }
done

# Never -v: the volume holds the completion records of every student who ever
# passed on this machine.
cleanup() { "${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT
"${COMPOSE[@]}" up -d --build "${SERVICES[@]}"
for _ in $(seq 1 60); do
  if "${CURL[@]}" -f "$URL/api/health/ready" >/dev/null; then
    echo "SMOKE OK: $("${CURL[@]}" "$URL/api/version")"
    exit 0
  fi
  sleep 2
done
echo "SMOKE FAILED: readiness not reached" >&2
"${COMPOSE[@]}" logs trainer | tail -50 >&2
exit 1
