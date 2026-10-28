#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(cd "$ROOT/backend" && uv run python -m app.openapi > openapi.json)
(cd "$ROOT/frontend" && pnpm gen:api)
echo "API types written to frontend/src/api/schema.d.ts"
