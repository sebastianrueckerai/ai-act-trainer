# LangChain guide for this repo

Written as interview notes: each concept, where it lives, why it is used that way. Kept current
from M2 on. The research behind the choices is in
`docs/research/2026-09-15-stack-and-langchain.md`.

## Chat models through LiteLLM

`backend/app/llm/models.py`. `ChatOpenAI` from `langchain-openai` with `base_url` pointing at the
LiteLLM proxy and `model` set to a role alias (`strong`, `fast`). LiteLLM maps the alias to a real
model per deployment, so the code never names a vendor. `temperature=0` for deterministic tool
runs, `max_retries=2` for transient proxy errors.

`chat_model(settings, role)` is the only place that builds a model. Everything else takes a
`BaseChatModel` as an argument, which is what makes the translation functions testable without a
network.

## Structured output

`backend/app/content/translate.py`. `model.with_structured_output(PydanticModel,
method="function_calling")` turns the Pydantic schema into a tool definition, forces the model to
call it, and validates the result. `function_calling` is pinned because proxy-fronted models do
not reliably support strict JSON schema.

The Pydantic model holds only the translatable fields. Shared fields are merged back in code, so
the model cannot alter ids, option keys, citations or the correct answer. That split is the whole
safety argument of the tool: a wrong translation is a content problem, a wrong id would be a data
problem.

## Messages

`SystemMessage` and `HumanMessage` from `langchain_core.messages`, passed as a list to `invoke`.
The system message carries the task rules, the human message the JSON payload. Both are built by
`system_prompt` and `_messages`, so the prompt is one testable string rather than something
scattered over call sites.

## Three things that make a forced tool call fail

All three cost a day to find. Each one produced a proxy error that named the model, not the cause.

**An empty tool description.** LangChain builds the tool description from the Pydantic model's
docstring. Without a docstring it sends `"description": ""`, and `openai/gpt-oss-120b` behind the
proxy then answers in plain text instead of calling the tool. Groq rejects that with
`tool_use_failed`, and the model's perfect answer is thrown away in the error body. The same
request with a one-line description succeeded five times out of five. **Give every schema used for
structured output a docstring.**

**A prompt that does not ask for the call.** `tool_choice` is set to the tool by name, so in
theory the instruction is redundant. In practice, adding "Return your translation by calling the
function TranslatableChapter." to the system message took a long payload from zero successes in
three to three in three. **Name the function in the prompt as well.**

**An output that is too long.** A whole chapter in one call is about 1500 tokens of arguments, and
the model drifts out of the tool-call format part way through: one success in five. The same model
translating one step at a time succeeded every time, and faster, because a failed attempt costs 22
seconds. `translate_chapter` therefore makes one call for the chapter frame and one call per step.
**Size the structured call to what the model can hold in format, not to what the data model looks
like.**

## Retrying the model, not the network

`with_retry` in `app/llm/retry.py`. `max_retries` on `ChatOpenAI` covers transport errors. It does not
cover an answer that arrived intact but is unusable, which is the common failure with open-weight
models. Two kinds are retried and nothing else:

- `ModelInvalidRequestError` whose text names `tool_use_failed`, which is the proxy saying the
  model skipped the tool call.
- Any `ValueError`, which in practice is one of two things. Our own merge guard, saying the model
  changed an option key or a step id. Or the parser, because a pydantic `ValidationError` is a
  `ValueError`, and that is what LangChain raises when the tool arguments do not fit the schema.

All three are non-deterministic and all three clear on the next attempt. Every other error is
raised at once, so a wrong base URL or an exhausted context still fails fast. An exhausted
context is worth checking if you change this: `langchain-openai` turns it into
`ContextOverflowError`, which is not a `ModelInvalidRequestError`, so it falls through to the
raise. Catching the LangChain exception `langchain_core.exceptions.ModelInvalidRequestError`
rather than the OpenAI one keeps the code free of the vendor SDK.

## Prompts are part of the legal surface

The glossary in `translate.py` maps German source terms to the official English terms of the
Regulation. Without it the model wrote "operator" for Betreiber and "AI Regulation" for
KI-Verordnung across most files, which is everyday English and wrong. With it the first run came
back clean on every term.

Two glossary lessons, both found by reading the output:

- An instruction to normalise article references also rewrote a German national law: `§ 2 Abs. 1
  KI-MIG` became `Art. 2(1) AI Act`, which points at the wrong statute. The prompt now excludes
  national laws by name.
- A glossary entry is applied wherever it roughly fits. "Personen, bei denen die KI-Systeme
  eingesetzt werden" pulled the unrelated "Personen in seinem Auftrag" towards it, until that
  second phrase got its own entry.

Read every generated file before committing it.

## An agent with real tools and a scripted model

`create_agent` from `langchain.agents`, in `backend/app/graph/answer.py`. The two answering
branches of the tutor graph (a free question with no question open, and the writer in
`reply.py` for every message while one is open) need the three law tools: open a library
node, read a citation, search. `create_agent` gives the tool loop: the model calls a tool,
sees the result, writes a final answer. The prompt is one string built by
`free_question_prompt` or `reply_prompt` and passed as `system_prompt`, and `_final_text`
reads the last `AIMessage` in the result as the answer. Every model call, agent or plain,
goes through the same `with_retry` as the translate tool.

In tests the tools are real and only the model is scripted. `ScriptedChatModel.bind_tools`
returns the model itself, and a script entry of the form `{"tool_calls": [...]}` becomes an
`AIMessage` carrying tool calls, so the agent loop runs its real tools over scripted turns.
That is the point: the test exercises the loop, the tool arguments and the final answer, not
a stubbed shortcut around them.

## ScriptedChatModel and the marker protocol

`backend/tests/fakes/scripted.py`. A `BaseChatModel` whose answers come from a script keyed
by a marker. Every model-facing prompt in the graph ends with a marker such as
`[node:triage]`, appended by `mark()` in `backend/app/graph/prompts.py`. The fake reads the
marker off the last system message, pops the script entry for it and records the call.
`_generate` also records the prompt, so a test can assert on what a node sent. A script
entry is one response or a list consumed in order. A list is what serves an agent loop: every
model turn carries the same system prompt, so a two-entry script answers the tool call and
then the final reply.

The marker protocol keeps a script declarative: the test says what each node answers, not in
what order the graph calls them. A marker with no script entry asserts, and an exhausted
list asserts, so a surprise model call fails the test rather than passing silently.

## Structured output inside the graph

Same call as the translate tool, `model.with_structured_output(Schema,
method="function_calling")`, on the triage decision (`Triage`), the leak judge
(`LeakVerdict`), the recovery of a choice from a free-form sentence and the rubric verdict
(`ProseChoice`, `Verdict`). Every schema carries a docstring, which the empty-tool-description
lesson above demands, and every call names its function in the prompt.

`with_structured_output` on `ScriptedChatModel` overrides the base method instead of
wrapping `_generate`. It returns a `RunnableLambda` that pops the scripted response and
asserts it is an instance of the schema. A structured-output call on the fake therefore
never reaches `_generate`, and a script entry for such a node is a Pydantic instance, not a
string.

## The checkpointer, per D23

`backend/app/graph/checkpointer.py`. Session state between turns lives in LangGraph's
checkpointer: `InMemorySaver` when `env` is `test`, `AsyncSqliteSaver` for a sqlite URL,
`AsyncPostgresSaver` otherwise. The sqlite and postgres savers come from LangGraph's `.aio`
modules. Each creates its own tables through `setup()` on open, Alembic does not manage
them, and `test_migrations.py` keeps checking only our own models. The reasoning is D23 in
`docs/design-decisions.md`.

## Custom events out of a node, and multi-mode astream at the edge

`get_stream_writer` from `langgraph.config`, in `backend/app/graph/persona.py`. A node
cannot stream from its return value, because that value is a state patch. While the node
runs inside a runnable context, `get_stream_writer()` hands back a writer callable, and
everything it is called with arrives at the graph edge as a `custom` chunk. The persona
funnel uses it after the rewrite: `turn_events` in `backend/app/graph/events.py` projects
the finished turn's ui events, parts and input hint onto plain dicts, and the node writes
each one through the writer. The call is wrapped for the case a test invokes the node
directly, outside a runnable context, where the writer raises `RuntimeError`.

`backend/app/api/chat.py` consumes the graph through
`astream(stream_mode=["updates", "messages", "custom"])`. Multi-mode astream yields
`(mode, chunk)` tuples, one mode per concern: `updates` carries the finished node names,
`messages` the token stream of the model calls, `custom` the writer's dicts. Each chunk is
consumed for its own source, and a custom dict travels unserialized because the endpoint
and the graph share the process.
