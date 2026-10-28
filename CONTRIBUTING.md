# Contributing

Issues and pull requests are welcome. The project is pre-alpha, so the code
moves fast.

## Rules that guard the product

- The law is the source of truth. Every legal claim in content, prompts or UI
  cites an article, annex, recital or section of a bundled act under
  `corpus/raw/` (manifest in `corpus/manifest.yaml`). The tutor answers only
  from bundled acts and says so when a question leaves them.
- The tutor never gives a test answer away. A change to the coaching branch
  ships with a leak test that pastes the tutor's reply back as the answer and
  expects it to fail.
- Personas are data directories under `personas/`. They never touch teaching,
  coaching or grading logic. A new persona is a directory, not a code change.
- Code, prompts, identifiers and docs are English. Student-facing strings live
  in locale and content files. German is the reference locale and the only one
  shipped today. Do not write English course content, and do not translate
  content that exists in German only.

## Development setup

You need [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/) and
Docker for the full stack.

1. Clone the repo.
2. `cd backend && uv sync`
3. `cd frontend && pnpm install`
4. Copy `.env.example` to `.env` and add a `GROQ_API_KEY` for the bundled model
   proxy.

## Tests

Run these before you open a pull request:

```bash
cd backend && uv run pytest
cd backend && uv run ruff check . && uv run ruff format --check .
cd frontend && pnpm test && pnpm lint && pnpm build
```

`bash deploy/smoke.sh` builds the compose stack and checks readiness.
`bash deploy/demo.sh` starts the stack and walks the product.
