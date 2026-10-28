# Research notes: target stack and LangChain landscape (2026-09-15)

Gathered by background research agents during the design phase. Facts, not decisions.

## 1. Target stack (from ../mittelstand-ai/leistungsbeschreibung-intern.md)

`mittelstand-ai` is a document workspace, not code. Its internal service description is the platform contract:

- Services: LiteLLM (gateway), Open WebUI (chat), Keycloak (SSO), shared Postgres (LiteLLM, Open WebUI, Keycloak), SearXNG, plus the AI Act trainer as an in-house component (Apache 2.0).
- Orchestration: Kubernetes via one Helm chart, versions pinned, Terraform IaC, GitOps. Managed k8s (EKS/AKS) or self-run on Hetzner. Not docker compose in production.
- Auth: Keycloak, federated to customer Entra ID / LDAP. Trainer is specified as "Login über Keycloak". Directory groups drive model visibility.
- LiteLLM: keys per team and user, budgets, model swap without client change. Apps use the OpenAI-compatible endpoint with URL + key.
- Ownership: trainer content by the maintainer, build by Origami, deliverable #5. Helm chart, IaC, Keycloak config are Origami deliverables in a not-yet-existing neutral GitHub org.

Nearest runnable reference: `../llm-integration/litellm-n8n/` (postgres:16 + `ghcr.io/berriai/litellm:main-stable` + n8n on a named bridge network, healthchecks `/health/liveliness` and `pg_isready`, `config/litellm.yaml` with `model_list`, `os.environ/...` keys, `cors_origins` allow-list, plain `.env` secrets). No pgvector, no Redis, no reverse proxy, no "add a service" doc.

Consequence: OIDC against Keycloak, LLM calls through LiteLLM with a service key, Postgres for state. Ship a Helm chart plus a compose file for local dev.

## 2. LangChain landscape (verified against PyPI/npm and langchain-ai/docs via context7)

Versions (2026-09-15): Python `langchain` 1.4.0, `langchain-core` 1.6.3, `langgraph` 1.2.11, `langchain-openai` 1.6.2, `langchain-classic` 1.0.8, `langchain-postgres` 0.0.17, `langgraph-checkpoint-postgres` 3.1.2, `langchain-text-splitters` 1.1.2, `langchain-litellm` 0.7.1, `langfuse` 4.15.2. JS `langchain` 1.5.11, `@langchain/core` 1.2.11, `@langchain/langgraph` 1.4.15, `@langchain/react` 1.1.0.

- 1.0 (Oct 2025) replaced chains/agents with `create_agent` + middleware on LangGraph. `create_react_agent`, `AgentExecutor`, `initialize_agent` are gone; legacy chains live in `langchain-classic`. `langchain-community` and `-experimental` are being sunset. No breaking changes promised before 2.0.
- Python vs JS: Python is first-class. Job ads: Python required in 93% of LangChain ads, TypeScript 17%. JS gaps: `createAgent` cannot be a `StateGraph` node (langgraphjs #1767 open). JS-only asset: `@langchain/react` `useStream` hook, usable from a React frontend regardless of backend language.
- Pipelines with branches: `StateGraph` + `add_conditional_edges`; `create_agent` as a node where a tool loop is needed. Middleware hooks (`before_agent`, `before_model`, `wrap_model_call`, `wrap_tool_call`, `after_model`, `after_agent`, `jump_to="end"`) implement guards inside an agent; prebuilt `PIIMiddleware`, `HumanInTheLoopMiddleware`, `ModelFallbackMiddleware`, `ToolCallLimitMiddleware`, `SummarizationMiddleware`.
- `agent.invoke(..., version="v2")` returns `.value` / `.interrupts`; `stream_events(version="v3")` gives typed `.messages`, `.values`, `.output`.
- Structured output: `with_structured_output(Schema, method="json_schema"|"function_calling"|"json_mode")`, or `response_format=Schema` in `create_agent` (auto ProviderStrategy/ToolStrategy from model profile). Through a LiteLLM proxy: pin `method="function_calling"`, validate with Pydantic, do not trust auto-selection (profile inferred from model name). Known issues: strict json_schema rejected by some backends; ToolStrategy via proxy to Bedrock fails silently (langchain #34891); forced tool_choice needs `drop_params` on Bedrock (litellm #11154).
- LiteLLM connection: `ChatOpenAI(base_url="http://litellm:4000/v1", api_key=..., model=...)` is the industry-common path. `langchain-litellm` wraps the SDK, not the proxy.
- RAG: `PGVectorStore` from `langchain-postgres` is the recommended store; shares the Postgres already needed for checkpoints. `langchain-chroma` as file-based alternative; `InMemoryVectorStore` for tests. `HTMLHeaderTextSplitter` attaches h1/h2/h3 metadata (article/paragraph numbers). Citations: `@tool(response_format="content_and_artifact")` returns text to the model and raw `Document`s as artifact for the UI.
- Memory: `PostgresSaver.from_conn_string(uri)` + `setup()`, keyed by `configurable.thread_id` (<255 chars); cron to delete old checkpoints. Compaction: `SummarizationMiddleware(model, trigger=("tokens", N), keep=("messages", M))` or `trim_messages` in a graph node.
- Streaming to React: `stream_mode=["messages","updates","custom"]` or `stream_events(v3)`. `useStream` from `@langchain/react` speaks the LangGraph Server protocol and supports custom transports (`FetchStreamTransport`). Reference UI: `langchain-ai/agent-chat-ui`. Alternative: FastAPI + AG-UI bridge (`ag_ui_langgraph`) for CopilotKit. No Vercel AI SDK adapter in current docs.
- Observability: LangSmith cloud free tier; self-host needs Enterprise. Langfuse (MIT) via `from langfuse.langchain import CallbackHandler` in `config={"callbacks":[handler]}`.
- Honest assessment: much less boilerplate than 0.1. Remaining complaints: `create_agent` state must be a TypedDict extending `AgentState`; middleware + custom `state_schema` interact awkwardly (#33217); large dependency tree; tracing near-mandatory to debug; PydanticAI has nicer DX but a smaller ecosystem.

Not verified: no code was run; JS parity from issue trackers.

## 3. LangGraph Server self-hosting (verified 2026-09-15)

- All self-hosted topologies (control plane, hybrid, standalone agent server) "require an Enterprise plan and the LangSmith license key" (docs.langchain.com/langsmith/deploy-to-self-hosted-overview). Standalone needs `LANGGRAPH_CLOUD_LICENSE_KEY` and egress to beacon.langchain.com. No free self-hosted production tier exists any more; "Lite" and node quotas are gone from docs and pricing.
- `langgraph dev` is documented as development-only.
- The server package `langgraph-api` is Elastic License 2.0 (source-available, not OSI), no public repo. ELv2 forbids hosted/managed-service provision and license-key circumvention; the LangSmith ToS limits self-hosted use to internal business use and bars distribution. Shipping it inside a customer's Helm chart is not permitted.
- `langgraph`, checkpointers, CLI and SDKs stay MIT.
- Consequence: the graph runs in our own FastAPI process. `useStream` from `@langchain/langgraph-sdk/react` (also re-exported by `@langchain/react`) works against a custom endpoint via `FetchStreamTransport`, provided the backend emits LangGraph-shaped SSE events (agent-protocol streaming spec). Alternative: a plain SSE client of our own.
