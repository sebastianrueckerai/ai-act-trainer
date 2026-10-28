# Research notes: multilingual content tooling (2026-09-15)

Verified by a background research agent against vendor docs, GitHub and npm. Two kinds of content: (a) UI strings, a few hundred keys; (b) structured course content in git (chapters, question bank, cheat sheets, persona fragments), per locale, edited by a non-developer with review and LLM translation suggestions.

## UI strings
| Tool | License | State | Footprint | Git | React / in-context | MT | Review |
|---|---|---|---|---|---|---|---|
| Tolgee | Apache-2.0 core, EE dirs source-available, free binary 10 seats | 3.221.x, releases weekly | Java + Postgres | CLI push/pull/sync, no git backend | `@tolgee/react`, in-context DevTools | DeepL/Google/AWS/Azure + configurable LLM | States + comments free; tasks, SSO, glossary, branching UI are EE |
| Weblate | GPL-3.0 | 2026.9.x | Weblate + Postgres + Redis, 4 GB RAM | Native: commits, pushes, PRs, GitHub App | None (file based: i18next JSON, PO) | DeepL/Google/MS/LibreTranslate/OpenAI-compatible | Reviewer role, approved state; auth GitHub/Entra/SAML/LDAP |
| Traduora | AGPL-3.0 | last release 2025-06, stagnant | Angular + Node + DB | none | none | none | none |
| lingo.dev | Apache-2.0 CLI | active | none | GitHub Action | n/a | bring-your-own LLM, JSON/YAML/Markdown, lockfile | none (MT in CI, not an editor) |

## Structured content in git
| Tool | License / state | Storage | i18n | Auth | Lists of objects | Review |
|---|---|---|---|---|---|---|
| Decap CMS | MIT, 3.16.x, slow | files in git | folder/file/single-file; list widget only whole-list i18n | git-host OAuth via proxy, no OIDC | yes | editorial workflow: branch + PR |
| Sveltia CMS | MIT, 0.212.x, near-daily releases | files in git, Decap-compatible config | field-level i18n honored inside lists and objects, per-locale required | GitHub/GitLab OAuth (Cloudflare Worker), Gitea; no OIDC | yes | Draft / In Review / Ready via PR labels (GitHub/GitLab) |
| Keystatic | MIT, 0.6.x, experimental | files in git via GitHub App | none | GitHub App | yes | branch switch only |
| TinaCMS | Apache-2.0 | git, but self-host needs GraphQL backend + DB | none native | Auth.js | yes | editorial workflow cloud-only |
| Payload / Strapi / Directus | MIT / MIT+EE / MSCL | own DB, export job needed | field-level | custom / EE / licensed | yes | drafts; approval EE or unverified |
| Static CMS | archived 2024 | | | | | |

## Findings
- No single tool covers both. Weblate can translate content files but is not an authoring tool for a question bank.
- Lightest pair: **Sveltia CMS** for course content (per-locale YAML/Markdown the backend loads unchanged, field-level i18n in lists so `type` and `citations` duplicate while `question`, `options`, `rubric`, `model_answer` translate, PR-based review, built-in AI translation with an Anthropic/OpenAI/Mistral key) plus **Tolgee** self-hosted for UI strings (React SDK, in-context editing, `tolgee pull` in CI). Runner-up: Weblate for all translation plus a small form editor for German authoring.
- Build-your-own baseline: `@rjsf/core` 6.x (Apache-2.0) or JSON Forms driven by JSON Schema emitted from the backend's Pydantic models, `monaco-yaml`, Octokit for branch + PR, GitHub OAuth. Estimate 2-4 developer weeks vs 1-2 days of Sveltia configuration. Sveltia supports custom field widgets, so a citation picker or rubric preview can be added later.
- Risks: Sveltia is 0.x (pin the version); the curator needs a GitHub or GitLab account with write access; Tolgee free tier lacks tasks and SSO (10 seats is enough).
- The curation stack serves the content team, not customers. Customers receive built content in the image.

## Not verified
Tolgee first-party GitHub Action; which AI features are EE; Weblate generic OIDC; Payload OIDC plugin; Octokit method names; the week estimate is judgement.
