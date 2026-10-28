from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph.state import CompiledStateGraph

from app.content.citations import scan_citations, written_act_names
from app.graph.brief import Brief, build_brief
from app.graph.critic import Critique, critique_reply, retry_block
from app.graph.deps import GraphDeps
from app.graph.govern import deadline, govern
from app.graph.prompts import (
    ANSWER_IN_LOCALE,
    ANSWER_LENGTH_RULE,
    EXPERTISE_RULES,
    FREE_QUESTION,
    GENDER_RULE,
    PLAIN_TEXT_RULE,
    SHORTEN,
    mark,
)
from app.graph.state import InputHint, SessionState
from app.graph.tools import (
    citations_from_text,
    law_tools,
    library_brief,
    without_inline_citations,
)
from app.graph.working import announce
from app.i18n import t
from app.llm.retry import with_retry


def free_question_prompt(
    deps: GraphDeps, brief: Brief, previous: str | None = None, critique: Critique | None = None
) -> str:
    blocks = [
        "You are the tutor of an EU AI Act course answering one free question from the "
        "student. Answer from the bundled acts alone:\n"
        f"{library_brief(deps.library, deps.content)}",
        brief.text(),
        ANSWER_IN_LOCALE,
    ]
    if previous is not None and critique is not None:
        blocks.append(retry_block(previous, critique))
    # The rules close the prompt, after the law the model just read, and the length
    # rule closes the rules: what stands last is what the answer obeys.
    blocks += ["Return your final answer as text.", EXPERTISE_RULES, ANSWER_LENGTH_RULE]
    return mark("\n\n".join(blocks), FREE_QUESTION)


def answer_agent(deps: GraphDeps, prompt: str) -> CompiledStateGraph:
    return create_agent(
        deps.models["strong"],
        tools=law_tools(deps),
        system_prompt=prompt,
    )


def _final_text(result: dict) -> str:
    """The agent's answer, with the corpus act ids it copied written as act names."""
    return written_act_names(
        next(
            str(message.content)
            for message in reversed(result["messages"])
            if isinstance(message, AIMessage)
        )
    )


MAX_PARAGRAPHS = 3


def _shorten_prompt(draft: str) -> str:
    return mark(
        "The tutor's answer below is too long for a chat bubble. Return it as the conclusion "
        "plus at most three short paragraphs, in German. Keep every fact and every citation "
        f"string exactly as written. Add nothing.\n\n{PLAIN_TEXT_RULE} {GENDER_RULE}"
        f"\n\nAnswer:\n{draft}",
        SHORTEN,
    )


def _shortened(deps: GraphDeps, draft: str) -> str:
    """The draft cut to length, or the draft itself when the cut lost a citation."""
    if len(draft.split("\n\n")) <= MAX_PARAGRAPHS:
        return draft
    model = deps.models["strong"]
    short = str(with_retry(lambda: model.invoke([SystemMessage(_shorten_prompt(draft))])).content)
    if not short.strip():
        return draft
    if any(citation.ref not in short for citation in scan_citations(draft)):
        return draft
    return short


def free_question_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        locale = state.get("locale", "de")
        turn = state["turn"]
        # With a question open the message goes to grade and the writer, so nothing here
        # can leak: this node only runs with no question open.
        brief = build_brief(deps, state, "free_question")

        holder: dict[str, Critique] = {}

        def produce(previous: str | None, _notes: str | None) -> str:
            agent = answer_agent(
                deps, free_question_prompt(deps, brief, previous, holder.get("critique"))
            )
            result = with_retry(lambda: agent.invoke({"messages": _input_messages(state)}))
            return _shortened(deps, _final_text(result))

        def judge(draft: str) -> Critique:
            holder["critique"] = critique_reply(deps, brief, draft)
            return holder["critique"]

        governed = govern(
            "reply",
            produce,
            judge,
            deadline(state, deps.settings),
            lambda step: announce(deps, state, step),
        )
        draft = governed.text
        # The parts are built from the prose the model wrote; the prose then loses its
        # references, and the hedge goes on after that, so the sources line stays trailing.
        patch: dict = {
            "parts": turn.parts + citations_from_text(deps, draft),
            "brief": brief.text(),
        }
        draft = without_inline_citations(draft)
        if turn.advice:
            draft = f"{draft}\n\n{t(locale, 'hedge')}"
            patch["hedge_added"] = True
        patch["draft"] = draft
        patch["closing_line"] = state.get("pending_prompt", "")
        patch["input_hint"] = state.get("last_hint", InputHint(kind="text"))
        return {"turn": turn.model_copy(update=patch)}

    return node


def _input_messages(state: SessionState) -> list[AnyMessage]:
    messages: list[AnyMessage] = []
    summary = state.get("summary", "")
    if summary:
        messages.append(
            HumanMessage(f"Here is a summary of the conversation to date:\n\n{summary}")
        )
    return messages + list(state.get("messages", []))
