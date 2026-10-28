# CLAUDE.md — ai-act-trainer

An employee training tool for the EU AI Act (Regulation (EU) 2024/1689, consolidated text of
27 July 2026). A chat with a Socratic tutor teaches an application-focused course, coaches
without giving answers away, runs a 10-question test drawn from a curated pool, and records
completions for compliance. Multilingual, German first. React frontend, LangChain/LangGraph
backend behind a LiteLLM proxy, pluggable identity (OIDC or LDAP) and storage. Ships as a
container with a docker compose file, as one piece of the mittelstand-ai
self-hosted stack.

Personas are data (one directory each) and are applied as the last step of the pipeline.
Content (chapters, question bank, model answers, cheat sheets) is curated in the repo per
language. The model delivers, coaches and grades. It never invents curriculum.

Pre-alpha. Decisions and why: `docs/design-decisions.md`. Never reverse one silently.
Propose a change as a new dated entry.

## Read before acting in an area

- **The brief:** `GOAL.md`. Its first section is the north star and outranks the rest of it:
  Jo, a desk worker with no interest in law, gives this 35 minutes and remembers it as the
  least shitty compliance training of their life. Bureaucracy on screen is a bug.
- **Decisions and the why:** `docs/design-decisions.md`.
- **Verified facts on the law, the source texts and the target stack:** `docs/research/`.
- **Writing anything a person reads** (docs, commit messages, reports, UI source strings):
  `docs/writing-guide.md`.

## Always-on rules

- The law is the source of truth. Every legal claim in content, prompts or UI cites an article,
  annex, recital or section of a bundled act under `corpus/raw/` (manifest in
  `corpus/manifest.yaml`). The tutor answers only from bundled acts, and says it does not know
  outside them. Bundled EUR-Lex text carries the attribution "© European Union, 2024-2026,
  eur-lex.europa.eu, reused under Commission Decision 2011/833/EU. Only the Official Journal is
  authentic."
- The tutor never gives a test answer away. Any change to the coaching branch ships with a
  leak test.
- Personas never touch teaching, coaching or grading logic. A new persona is a directory, not
  a code change.
- Storage and identity stay behind interfaces. No feature may assume the bundled Postgres or
  any bundled identity provider.
- Code, prompts, identifiers and internal docs are English. Student-facing strings live in
  locale files. German is the reference locale and the only locale v0.1 ships (D22). Do not
  write or translate English content.

## Running things

```bash
cd backend && uv run pytest                    # backend suite (fake models, SQLite)
cd backend && uv run ruff check . && uv run ruff format --check .
cd frontend && pnpm test && pnpm lint && pnpm build
cd frontend && pnpm test:browser               # Playwright: the click path and the gallery
tools/gen-api-types.sh                         # after any API change: regenerate TS types
bash deploy/demo.sh                            # run the product: stack up, checks, browser walk.
                                               # The local stack always runs the latest work; end a
                                               # round with it up
bash deploy/smoke.sh                           # compose stack: build, readiness, teardown
cd backend && uv run uvicorn app.main:create_app --factory --reload   # dev server :8000
cd frontend && pnpm dev                        # Vite dev server :5173, proxies /api
```
