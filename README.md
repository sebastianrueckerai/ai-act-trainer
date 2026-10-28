# AI Act Trainer

An employee training tool for the EU AI Act (Regulation (EU) 2024/1689). A chat
with a Socratic tutor teaches an application-focused course in about 35
minutes, coaches without giving answers away, runs a 10-question test drawn
from a curated pool, and records completions for compliance.

The course content is curated in the repo, not invented by the model: chapters,
the question bank, model answers and cheat sheets are authored files per
language. The model delivers, coaches and grades. Personas (a sad robot, a
drill sergeant, a jester, a bureaucrat) add flavour as the last step of the
pipeline and never touch the teaching logic.

German course content ships first. English is planned. The code base, prompts
and docs are English.

Self-hosted: one container plus your model proxy (LiteLLM), your identity
provider and your Postgres. Ships with a docker compose file
for the mittelstand-ai stack.

Status: **pre-alpha**. Identity is invite-based today. OIDC and LDAP are
planned.

## Quickstart

### Public host with the compose overlay

The public overlay runs the trainer behind Caddy on ports 80 and 443, in
production mode, with invite-only sign-up.

1. Copy `.env.example` to `.env`.
2. Generate a `SECRET_KEY`: any random string of 16 characters or more. The
   overlay refuses to start without one.
3. Set `PUBLIC_HOST` to your domain, for example `aifuehrerschein.world`, or
   `localhost` for a self-signed certificate.
4. Set `GROQ_API_KEY` and `LITELLM_MASTER_KEY`. The bundled LiteLLM proxy uses
   both.
5. Start the stack:

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.public.yml \
  --profile dev --profile public --env-file .env up -d --build
```

Invite auth needs a proxy key that may create keys and read spend: set
`LITELLM_ADMIN_KEY`, or leave it unset and the overlay falls back to
`LITELLM_MASTER_KEY`.

To use an existing LiteLLM instead of the bundled one, drop `--profile dev`
and point `LLM_BASE_URL` and `LLM_API_KEY` at it.

### Plain dev path

```bash
cd backend && uv sync && uv run uvicorn app.main:create_app --factory --reload
cd frontend && pnpm install && pnpm dev
```

The API serves on `http://localhost:8000`. The Vite dev server on
`http://localhost:5173` proxies `/api` to it.

## Configuration

Every variable below is read from the environment or `.env`. The compose files
read the ones marked compose. Defaults come from `.env.example`.

### Runtime

| Variable | Default | What it does |
| --- | --- | --- |
| `ENV` | `development` | `development`, `test` or `production`. Production turns off the API docs and dev auth. |
| `LOG_LEVEL` | `INFO` | Python log level. |
| `SECRET_KEY` | dev default | Signs sessions and tokens. Use a random string of 16 characters or more. Production refuses the default. Compose: the public overlay refuses to start without it. |

### Storage

| Variable | Default | What it does |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./trainer.db` | SQLAlchemy URL. Compose overrides it with the bundled Postgres. |
| `RUN_MIGRATIONS` | `true` | Runs schema migrations at start. |
| `POSTGRES_PASSWORD` | `trainer-dev-password` | Password of the bundled Postgres. Compose. Dev default only. |

### Identity

| Variable | Default | What it does |
| --- | --- | --- |
| `AUTH_BACKEND` | `dev` | `dev`, `invite`, `oidc`, `ldap` or `proxy`. `oidc`, `ldap` and `proxy` are planned. The public overlay forces `invite`. |
| `ADMIN_GROUPS` | `compliance` | Comma-separated identity-provider groups that get the admin role. |
| `PROXY_TRUSTED_ADDRESSES` | empty | Trusted proxy addresses, required when `AUTH_BACKEND=proxy`. |
| `SESSION_MAX_AGE_SECONDS` | `43200` | Session lifetime. |
| `GUEST_ACCESS` | `false` | `true` opens guest sign-up (`POST /api/auth/guest`), with any backend. |
| `GUEST_SEATS` | `10` | Guests with a turn in the last ten minutes. The next one waits. |
| `GUEST_RETENTION_HOURS` | `6` | A guest idle this long loses every row, checked hourly. |
| `PUBLIC_URL` | `http://localhost:8000` | Base URL of invite links. |

### Models through LiteLLM

| Variable | Default | What it does |
| --- | --- | --- |
| `LLM_BASE_URL` | `http://litellm:4000/v1` | OpenAI-compatible endpoint of the model proxy. Compose. |
| `LLM_API_KEY` | `sk-dev-master` | Key the app calls the proxy with. |
| `LITELLM_ADMIN_KEY` | empty | Proxy key that may create keys and read spend, used for invite auth and budgets. Empty turns budgets off. The public overlay falls back to `LITELLM_MASTER_KEY`. |
| `LLM_MODEL_STRONG` | `strong` | Model name for teaching, grading and personas. |
| `LLM_MODEL_FAST` | `fast` | Model name for triage and summaries. |
| `LLM_MODEL_EMBED` | empty | Model name for embeddings. Unused today. |
| `LLM_TIMEOUT_SECONDS` | `60` | Timeout of one model call. |
| `EXCERPT_BUDGET_CHARS` | `1200` | Characters of cited law text a prompt carries per citation. |
| `SEARCH_TOP_K` | `5` | Hits the law search returns per query. |
| `TURN_BUDGET_SECONDS` | `20` | Critic retries stop after this. The best draft ships. |
| `LITELLM_MASTER_KEY` | `sk-dev-master` | Master key of the bundled LiteLLM proxy. Read by LiteLLM, not by the app. |
| `GROQ_API_KEY` | empty | Provider key the bundled LiteLLM proxy uses. Read by LiteLLM. |

### Data and compliance

| Variable | Default | What it does |
| --- | --- | --- |
| `DATA_LEVEL` | `0` | `0` pass records only. `1` adds attempts and scores. `2` adds transcripts and raw model output in logs. |
| `RETENTION_DAYS` | `30` | A named student idle this long loses their threads and turns, checked hourly. Pass records stay. |
| `RETRAIN_ON_MAJOR_VERSION` | `true` | A major law version bump invalidates passes. |
| `PASS_THRESHOLD` | `8` | Correct answers out of 10 that pass the test. |
| `TRAINING_INTERVAL_DAYS` | `365` | Days a pass covers, for the yearly training duty. |
| `TURN_LIMIT_USER_DAY` | `300` | Streamed turns per named student per rolling day. |
| `TURN_LIMIT_GUEST_DAY` | `150` | Streamed turns per guest per rolling day. |
| `TURN_LIMIT_GLOBAL_DAY` | `2000` | Streamed turns across all students per rolling day. |
| `FEATURE_ADMIN_VIEW` | `false` | Admin view of completions. |
| `FEATURE_CERTIFICATE` | `false` | PDF certificate for a pass. |
| `FEATURE_REMINDERS` | `false` | Reminder emails. Requires `SMTP_HOST`. |
| `FEATURE_DEPARTMENT_STATS` | `false` | Statistics per department. |
| `FEATURE_AUDIT_LOG` | `false` | Audit log. Requires `DATA_LEVEL=2`. |
| `SMTP_HOST` | empty | SMTP server for reminders. |
| `SMTP_PORT` | `587` | SMTP port. |
| `SMTP_USER` | empty | SMTP user. |
| `SMTP_PASSWORD` | empty | SMTP password. |
| `SMTP_FROM` | empty | Sender address of outgoing mail. |

### Theme

| Variable | Default | What it does |
| --- | --- | --- |
| `THEME_PRIMARY` | `#38bdf8` | Primary colour, hex. |
| `THEME_SECONDARY` | `#16233a` | Secondary colour, hex. |
| `THEME_ACCENT` | `#fbbf24` | Accent colour, hex. |
| `THEME_BACKGROUND` | `#f8fafc` | Light-mode background colour, hex. |
| `THEME_LOOK` | `pixel` | `pixel` or `clean`. |

### Paths

Each of these is set by the container image. Override one for a local run.

| Variable | Default | What it does |
| --- | --- | --- |
| `CONTENT_DIR` | `/app/content` | Curated course content. |
| `CONTENT_OVERLAY_DIR` | empty | Layers local content on top of `CONTENT_DIR`. Unset by default. |
| `PERSONAS_DIR` | `/app/personas` | Persona data. |
| `CORPUS_DIR` | `/app/corpus` | Bundled law text. |
| `FRONTEND_DIST` | `/app/frontend` | Built frontend the backend serves. |
| `FONTS_DIR` | `/app/fonts` | Font files. |

### Compose and build

| Variable | Default | What it does |
| --- | --- | --- |
| `PUBLIC_HOST` | none | Site address Caddy serves. Required by the public overlay. Compose. |
| `CADDY_HTTP_PORT` | `80` | Host port for Caddy HTTP. Compose. |
| `CADDY_HTTPS_PORT` | `443` | Host port for Caddy HTTPS. Compose. |
| `REPLICATE_API_TOKEN` | empty | Only `tools/generate_avatars.py` reads this. The app never does. |
| `VITE_TOLGEE_API_URL` | unset | Translation tooling at build time. Leave unset for public builds. |
| `VITE_TOLGEE_API_KEY` | unset | Translation tooling at build time. The key ships in the JS bundle, so leave it unset for public builds. |

## Privacy and data protection

The trainer stores completion records: who passed which course and law version,
when, in which language, with which persona. These records are the point of the
tool, so they stay until you delete the database.

With `DATA_LEVEL=2` the trainer also stores transcripts: the full chat threads.
An hourly sweep purges them. A named student's threads go after
`RETENTION_DAYS` idle days (30 by default). A guest's threads go after
`GUEST_RETENTION_HOURS` idle hours (6 by default). The account row and the pass
record of a named student survive the sweep.

Logs carry verdicts and lengths, never student text. Raw model output is
logged only at `DATA_LEVEL=2`.

## Law text

The tutor answers only from the acts bundled under `corpus/`. Bundled EUR-Lex
text: © European Union, 2024-2026, eur-lex.europa.eu, reused under Commission
Decision 2011/833/EU. Only the Official Journal is authentic.

## Licence

The code is MIT licensed. See [LICENSE](LICENSE).

The bundled law text under `corpus/` is third-party material. Each act in
`corpus/manifest.yaml` carries its own attribution and reuse terms.

## Known limitations

- File download tokens do not expire.
- In the dev compose file, the bundled LiteLLM shares the app's Postgres
  credentials.
- Guest sign-up is not throttled beyond the seat limit.
