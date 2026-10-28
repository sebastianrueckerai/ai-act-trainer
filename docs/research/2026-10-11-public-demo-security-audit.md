# Security audit of the public demo, 2026-10-11

Scope: aifuehrerschein.world on the Oracle free VM as deployed by the internal
(archived) Terraform and Ansible at master d2a8cb4. Ordered by what the
owner fears most: a bill, then someone in the VM, then user data. Every "checked" line was verified on the live host or
the live site that day; "open" lines are findings not yet acted on.

## 1. Billing

What can cost money: model calls through the proxy (Groq), and Oracle resources. Nothing
else in the stack bills.

| Gate | State | Evidence |
|---|---|---|
| Per caller, day: LiteLLM key, 2 USD (pool and account) | checked | Production proxy refused a 0.001 USD key on its first call by pre-call estimate; the app reads a key with less than 0.01 USD left as spent, so the notice shows the reset time |
| Per caller, month: LiteLLM user, 6 USD pool, 8 USD account | checked by test | Same read path as the day, covered by `test_llm_budget.py`; not exhausted live |
| Proxy-wide: 5 USD a day | checked locally | A 0.0001 USD proxy-wide budget refused every call on the local stack; the same setting is live in `config.public.yaml`, proxy healthy |
| Per model deployment: 12 + 3 USD a month | config live | Setting names confirmed against the LiteLLM docs; not driven to its limit |
| Fail closed when spend cannot be read | config live | `fail_closed_budget_enforcement: true`; the proxy's database is the shared Postgres, unpublished |
| Groq organisation limit: 15 USD a month | **open, owner** | Console only (Settings, Billing, Limits), Developer tier |
| Turn counts: 150 guest, 300 account, 2000 all, per day | checked by test | `_refusal` in `chat.py`, tests in `test_turns.py` and `test_callers.py` |
| Seats: 10 guests per ten minutes | checked live | Two seats and three guests refused the third on the local stack. This also caps the spend rate: at most ten guest openings per ten minutes |
| Rate at the proxy: 30 and 60 rpm | config live | Worst case about 0.1 USD a minute at full rate, so the proxy-wide day cap closes within an hour of a flood |
| Oracle: only always-free resources | checked | Terraform state holds VCN, subnet, security list, gateway, route table, one A1 instance (2 OCPU, 12 GB), one reserved IP. The playbook creates nothing in the tenancy. OCI budget alert at 1 EUR a month set earlier (M5.21) |

Endpoints without a session, and what they cost: `POST /api/auth/guest` (a cookie, no
row until the first request), `GET /api/auth/options`, `/api/version`, `/api/theme`,
`/api/personas` and the portraits (static files), `/api/health/live`, `/ready`, `/llm`
(lists the proxy's models, no completion). None reaches a paid model.

Overshoot per key is at most one request past the budget, since the proxy estimates
before the call and books after it. Budgets count USD; the owner's numbers were EUR, so
every cap is a little stricter than asked.

Open, billing:

- The Groq organisation limit is the backstop if the proxy's database is lost together
  with its fail-closed setting. The owner sets it.
- Oracle's free tier includes 10 TB of egress a month. A flood that downloads the page's
  scene images for a month could cross it; the 1 EUR OCI alert would say so. Not mitigated.
- `ghcr.io/berriai/litellm:main-stable` is a moving tag. A future image could change what
  a budget means. Pin a version once one has been proven, and bump on purpose.

## 2. The VM

| Control | State | Evidence |
|---|---|---|
| Ports reachable from the internet | checked | 80 and 443 open, 22 open to the admin address only (OCI security list), 8000, 4000, 5432, 2019 closed from outside |
| SSH | checked | `passwordauthentication no`, `permitrootlogin no`, `kbdinteractiveauthentication no` from `sshd -T`; fail2ban's sshd jail running |
| Host firewall | checked | `/etc/iptables/rules.v4` accepts 22, 80, 443 and rejects the rest; the live INPUT chain matches; Docker's own FORWARD chains intact |
| Services listening | checked | sshd, Caddy's two published ports, resolved on localhost. rpcbind masked |
| Updates | checked | `unattended-upgrades` installed and enabled; containers rebuilt from HEAD on every deploy |
| TLS | checked | Let's Encrypt via Caddy, HTTP 308 to HTTPS, HSTS and nosniff headers (third playbook run) |
| Containers | checked | The trainer runs as uid 10001; no Docker socket mounted; no privileged container; Postgres and the proxy have no published ports |
| Secrets | checked | `/opt/ai-act-trainer/.env` root-only 0600; the generated secrets on the host 0600 in a 0700 directory; the Terraform state holds no secret (the SSH public key only); nothing in git or the image |
| Logs | checked | Docker json-file logs capped at 5 by 20 MB per container (third run) |

Open, VM:

- If the maintainer's home address changes, SSH is locked out at the Oracle level:
  re-applying the archived Terraform with the new admin CIDR opens it again.
- No rate limit at the edge. A request flood can take the free VM down; it cannot bill.
  Caddy's standard image has no rate limiter; a custom build with `caddy-ratelimit` or
  fail2ban on Caddy's access log would add one.
- `postgres:16` and `caddy:2` are moving minor tags, rebuilt on every deploy.

## 3. User data

| Control | State | Evidence |
|---|---|---|
| Guests | checked by test | Own thread per guest; idle six hours means thread, sessions, completions, turn log and user row are deleted hourly (`clean_guests`) |
| Named accounts | by design | `DATA_LEVEL=0`: a completion stores the pass only. The thread stays until `RETENTION_DAYS` is enforced (M6, open) |
| Session cookie | checked in code | Signed with the generated `SECRET_KEY`, `HttpOnly`, `Secure` in production, `SameSite=Lax`, 30 days |
| Cross-site requests | checked in code | No CORS middleware, so a browser blocks cross-origin calls to the JSON API |
| Invite tokens | checked in code | 24 random bytes, only the SHA-256 stored, stripped from the address bar after login; Caddy writes no access log |
| Database at rest | by provider | Oracle boot volumes are encrypted at rest by default |

Open, data:

- No backup. The database holds the accounts table (re-creatable with new links) and
  guest threads that die in six hours. A nightly `pg_dump` to the boot volume is a
  one-task addition to the playbook if accounts become worth keeping.
- `turn_failed` events carry `str(error)` to the client. It names internal hosts at worst,
  never a secret.
