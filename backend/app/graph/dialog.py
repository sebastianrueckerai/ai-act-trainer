from langchain_core.messages import RemoveMessage, SystemMessage

from app.graph.deps import GraphDeps
from app.graph.prompts import COMPACT, HELP, mark
from app.graph.state import Guard, InputHint, Mood, Phase, SessionState
from app.i18n import t
from app.llm.retry import with_retry

KEEP_RECENT = 8


def compact_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        messages = state.get("messages", [])
        estimate = sum(len(str(m.content)) for m in messages) // 4
        older = messages[:-KEEP_RECENT]
        if estimate <= deps.settings.compact_tokens or not older:
            return {}
        for i, message in enumerate(messages):
            if not message.id:
                message.id = f"m{i}"
        transcript = "\n".join(f"{m.type}: {m.content}" for m in older)
        prompt = mark(
            "Summarize the earlier part of a German training conversation for the tutor's "
            "memory. Keep roles, decisions and cited articles. German, plain text, at most "
            f"ten sentences. Return the summary by writing it directly.\n\n{transcript}",
            COMPACT,
        )
        reply = with_retry(lambda: deps.models["fast"].invoke([SystemMessage(prompt)]))
        summary = str(reply.content)
        previous = state.get("summary", "")
        if previous:
            summary = f"{previous}\n\n{summary}"
        return {"summary": summary, "messages": [RemoveMessage(id=m.id) for m in older]}

    return node


def react_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        turn = state["turn"]
        hint = state.get("last_hint", InputHint(kind="text"))
        guard = turn.guard
        if guard is Guard.ok:
            return {
                "turn": turn.model_copy(
                    update={"draft": state.get("pending_prompt", ""), "input_hint": hint}
                )
            }
        persona = deps.persona(state.get("persona_id"))
        locale = state.get("locale", "de")
        reaction = persona.reactions[guard.value] if persona else t(locale, f"react_{guard.value}")
        draft = f"{reaction}\n\n{state.get('pending_prompt', '')}"
        patch: dict = {
            "turn": turn.model_copy(
                update={
                    "draft": draft,
                    "guard_category": guard,
                    "input_hint": hint,
                    "voiced": persona is not None,
                }
            )
        }
        if guard in (Guard.cheat, Guard.insult, Guard.humor):
            patch["mood"] = Mood.surprised
        return patch

    return node


def _help_prompt(locale: str, phase: Phase) -> str:
    prompt = (
        "You are the tutor in a German AI Act training chat and the student asked what "
        "they can do now or how the course works.\n"
        f"Answer with exactly this, and nothing else: {t(locale, f'help_{phase.value}')}\n"
        "Keep every fact and every quoted word the student has to type. Write German, "
        "du-form, at most two sentences. Ask no question back and add no fact of your own."
    )
    return mark(prompt, HELP)


def help_node(deps: GraphDeps):
    """How the course works. With a question open, a plea for help goes to grade and the
    writer like any other message, so this node never sees one."""

    def node(state: SessionState) -> dict:
        locale = state.get("locale", "de")
        hint = state.get("last_hint", InputHint(kind="text"))
        if state.get("pending_case") is not None:
            # A no to "Klar soweit?": ask what did not land, and the check-in stands.
            update = {"draft": t(locale, "clear_not_yet"), "closing_line": "", "input_hint": hint}
            return {"turn": state["turn"].model_copy(update=update)}
        phase = Phase(state.get("phase", Phase.lesson))
        prompt = _help_prompt(locale, phase)
        reply = with_retry(lambda: deps.models["fast"].invoke([SystemMessage(prompt)]))
        return {
            "turn": state["turn"].model_copy(
                update={
                    "draft": str(reply.content),
                    "closing_line": state.get("pending_prompt", ""),
                    "input_hint": hint,
                }
            )
        }

    return node
