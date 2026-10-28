#!/usr/bin/env bash
# Start the whole trainer from scratch, check it, and leave it running for a
# walk in the browser. Run `deploy/demo.sh --help` for the options.
set -euo pipefail

# A stale GROQ_API_KEY in the shell beats the repo .env for compose, and the
# proxy then authenticates nobody.
unset GROQ_API_KEY

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
PROXY_URL="${PROXY_URL:-http://localhost:4000}"
SUBJECT=demo
COMPOSE=(docker compose -f "$ROOT/deploy/docker-compose.yml" --env-file "$ENV_FILE" --profile dev)

usage() {
  cat <<'TXT'
deploy/demo.sh [--browser] [--walk] [--keep] [--down] [--logs]

  (no option)  build the image, start postgres, litellm and trainer, wait for
               readiness, reset the demo student, check the API and the served
               UI, then print what to click
  --browser    after the checks, drive the real UI in a browser against a
               scripted stack of its own on port 4173 (about a minute)
  --walk       after the checks, walk the full course over the API with the
               real models as a throwaway student (a few minutes)
  --keep       skip the reset, resume the demo student where they stopped
  --down       stop the stack, keep the database
  --logs       follow the trainer log

The database survives every option: it holds real completion records.
TXT
}

walk=0 keep=0 browser=0 action=up
while [ $# -gt 0 ]; do
  case "$1" in
    --browser) browser=1 ;;
    --walk) walk=1 ;;
    --keep) keep=1 ;;
    --down) action=down ;;
    --logs) action=logs ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

# Never -v here: the volume holds the completion records of every student who
# ever passed on this machine.
case "$action" in
  down)
    "${COMPOSE[@]}" down --remove-orphans
    echo "stack down, database kept"
    exit 0
    ;;
  logs) exec "${COMPOSE[@]}" logs -f trainer ;;
esac

# Every bind mount in the compose file must exist as a file before compose runs.
# Docker creates a missing bind source as a root-owned directory, and on a path
# under a deleted worktree that leaves a tree nobody can remove without root.
for bound in deploy/litellm/config.yaml; do
  [ -f "$ROOT/$bound" ] || {
    echo "missing $ROOT/$bound: compose would create it as a root-owned directory" >&2
    exit 1
  }
done

[ -f "$ENV_FILE" ] || {
  echo "no $ENV_FILE: copy .env.example and fill it in" >&2
  exit 1
}
if [ "$(grep -c '^GROQ_API_KEY=.' "$ENV_FILE")" -eq 0 ]; then
  echo "warning: $ENV_FILE carries no GROQ_API_KEY, the tutor will not answer" >&2
fi

wait_for() { # url label tries
  for _ in $(seq 1 "${3:-90}"); do
    if curl -sf -o /dev/null "$1"; then
      echo "ok    $2"
      return 0
    fi
    sleep 2
  done
  echo "FAILED: $2 not reachable at $1" >&2
  "${COMPOSE[@]}" logs --tail 50 trainer litellm >&2
  exit 1
}

check() { # command... label
  local label="${*: -1}"
  if "${@:1:$#-1}" > /dev/null 2>&1; then
    echo "ok    $label"
  else
    echo "FAILED: $label" >&2
    exit 1
  fi
}

echo "==> building and starting postgres, litellm, trainer"
"${COMPOSE[@]}" up -d --build postgres
for _ in $(seq 1 30); do
  "${COMPOSE[@]}" exec -T postgres psql -q -U trainer -d trainer -c "SELECT 1" >/dev/null 2>&1 && break
  sleep 2
done
# LiteLLM tracks its budgets in its own database; Prisma makes it on first boot,
# but the database itself must exist, also on a volume created before it did.
"${COMPOSE[@]}" exec -T postgres psql -q -U trainer -d trainer -tc \
  "SELECT 1 FROM pg_database WHERE datname = 'litellm'" | grep -q 1 ||
  "${COMPOSE[@]}" exec -T postgres psql -q -U trainer -d trainer -c "CREATE DATABASE litellm"
"${COMPOSE[@]}" up -d --build litellm trainer

echo "==> waiting"
wait_for "$PROXY_URL/health/liveliness" "model proxy at $PROXY_URL" 30
wait_for "$BASE_URL/api/health/ready" "trainer at $BASE_URL"

if [ "$keep" -eq 0 ]; then
  echo "==> resetting the $SUBJECT student"
  "${COMPOSE[@]}" exec -T postgres psql -q -v ON_ERROR_STOP=1 -U trainer -d trainer <<SQL
DELETE FROM turn_log WHERE user_id IN (SELECT id FROM users WHERE subject = '$SUBJECT');
DELETE FROM completions WHERE user_id IN (SELECT id FROM users WHERE subject = '$SUBJECT');
DELETE FROM training_sessions WHERE user_id IN (SELECT id FROM users WHERE subject = '$SUBJECT');
DELETE FROM users WHERE subject = '$SUBJECT';
SQL
fi

echo "==> checking"
jar="$(mktemp)"
trap 'rm -f "$jar" "$jar.html"' EXIT
check curl -sf -c "$jar" -X POST "$BASE_URL/api/auth/dev/login" \
  -H 'content-type: application/json' -d "{\"subject\":\"$SUBJECT\"}" "sign in as $SUBJECT"
echo "ok    version   $(curl -sf "$BASE_URL/api/version" | grep -o '"app":"[^"]*"' | cut -d'"' -f4)"
echo "ok    look      $(curl -sf "$BASE_URL/api/theme" | grep -o '"look":"[^"]*"' | cut -d'"' -f4)"
echo "ok    personas  $(curl -sf -b "$jar" "$BASE_URL/api/personas" | grep -o '"id"' | wc -l)"
check curl -sf -o /dev/null -b "$jar" "$BASE_URL/api/personas/clerk/images/happy" "portraits served"
check curl -sf "$BASE_URL/" -o "$jar.html" "built UI served"
check grep -q 'id="root"' "$jar.html" "the UI is the built app, not the API"
check curl -sf -o /dev/null "$BASE_URL/gallery" "primitives gallery"

if [ "$browser" -eq 1 ]; then
  # Its own stack on 4173 with scripted models: the click path has to be the same
  # every run, and the compose stack answers from the real ones.
  echo "==> driving the UI in a browser"
  (cd "$ROOT/frontend" && pnpm build && pnpm test:browser)
fi

if [ "$walk" -eq 1 ]; then
  command -v uv > /dev/null || {
    echo "FAILED: --walk needs uv on the host" >&2
    exit 1
  }
  subject="walk-$(date +%Y%m%d-%H%M%S)"
  echo "==> walking the whole course as $subject, real models, a few minutes"
  (cd "$ROOT" && uv run --project backend python tools/demo_walk.py \
    --base-url "$BASE_URL" --subject "$subject" --questions content/de/questions)
fi

cat <<TXT

The stack is up. Open $BASE_URL and sign in as Demo.

  start     pick a persona on the first screen; the course opens on its own
  chat      say "weiter", answer the questions, watch the line above the box:
            persona mood, chapter count, streak, attempt dots
  look      the buttons at the top switch pixel and clean, dark and light, and
            the pixel look switches the body font
  files     a finished chapter attaches its cheat sheet, the finale attaches
            the full sheet and the certificate, both open as PDFs
  gallery   $BASE_URL/gallery shows every primitive in both looks and modes
  browser   deploy/demo.sh --browser  drives the click path in a real browser
  again     deploy/demo.sh          resets the demo student and checks again
  stop      deploy/demo.sh --down   keeps the database
TXT
