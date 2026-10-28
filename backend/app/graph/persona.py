import re

import structlog
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.config import get_stream_writer

from app.api.chat_events import part_out
from app.content.citations import de_ref, scan_citations, written_act_names
from app.content.gender import degender
from app.content.models import PersonaManifest
from app.graph.brief import Brief, build_brief
from app.graph.critic import critique_voice
from app.graph.deps import GraphDeps
from app.graph.events import settle_events, ui_events
from app.graph.govern import deadline, govern
from app.graph.prompts import GENDER_RULE, PERSONA, PLAIN_TEXT_RULE, mark
from app.graph.stage import build_stage
from app.graph.state import InputHint, Mood, SessionState, TurnScratch
from app.graph.translate import chapter_titles_en
from app.graph.working import announce
from app.i18n import t
from app.llm.retry import with_retry

log = structlog.get_logger(__name__)

OPENING_NOTE = (
    "\n\nThis is the course's very first message and it already opens on the "
    "character's greeting, which the student has read: write no opener of your own."
)

NO_SPICE_LINE = (
    "This character adds nothing of his own: no opener, no closer, no aside, no comparison. "
    "Rewrite the message's sentences in his voice and stop there, no longer than the message."
)

VOICE_RULES = (
    "Rules. Keep every fact, number, citation, option letter and verdict exactly as the "
    "message has them. Where the message ends on the question the tutor asks, or carries "
    "the app's closing line, keep that text word for word. Add no fact, no hint and no "
    "question of your own: the tutor's questions are the only questions. The character's "
    "flavour lives in the framing, an opener, a closer, a short aside, word choice and "
    "rhythm, never inside a fact, a condition or a number. At most one image from the "
    "character's world. Readable first: the student must find the lesson without decoding "
    "the character, so keep the message's paragraphs, in the same order, and about the same "
    "length. Vary the opener: the conversation shows what was said, so do not open the "
    "same way twice. When the student is stuck or wrong, the character is kind and short. "
    f"{PLAIN_TEXT_RULE} {GENDER_RULE}"
)

_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]*", re.M)
_THEMATIC_BREAK = re.compile(r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$", re.M)
_EMPHASIS = re.compile(r"(\*{1,3}|_{2,3})(\S(?:.*?\S)?)\1", re.S)
_BULLET = re.compile(r"^[ \t]*[*+][ \t]+", re.M)
# Runs after degender, which owns the gender star.
_STRAY_EMPHASIS = re.compile(r"(?<=\w)\*+|\*+(?=\w)")
# A prompt's own node marker, echoed back by the model.
_NODE_MARKER = re.compile(r"\[node:[a-z_]+\]")
# The bitmap body font has no glyph for a non-breaking space or hyphen, so the word and the
# number it separates run together on screen, or the hyphen falls out of the face.
_HARD_CHARS = str.maketrans({" ": " ", " ": " ", " ": " ", " ": " ", "‑": "-"})
# A single line break inside a paragraph is the model's, not the draft's ("Tadaa!  \nVerlangt
# ist ..."), and the bubble would show it. A list item keeps its line.
_BLANK_LINE = re.compile(r"\n[ \t]+\n")
_LINE_BREAK = re.compile(r"(?<!\n)[ \t]*\n(?!\n)(?![ \t]*(?:[-*+]|\d+[.)])[ \t])[ \t]*")
# An interjection parked at the very end of a paragraph ("... ein solches System. Arr,") has
# nothing to attach to.
_COMMA_TAIL = re.compile(r"(?<=[.!?])[ \t]+\w{1,12},[ \t]*(?=\n|$)")


def plain_text(text: str) -> str:
    text = written_act_names(_NODE_MARKER.sub("", text.translate(_HARD_CHARS)))
    text = _HEADING.sub("", text)
    text = _THEMATIC_BREAK.sub("", text)
    text = _EMPHASIS.sub(r"\2", text)
    text = _BULLET.sub("- ", text)
    text = _LINE_BREAK.sub(" ", _BLANK_LINE.sub("\n\n", text))
    text = _COMMA_TAIL.sub("", text)
    text = _STRAY_EMPHASIS.sub("", degender(text.strip()))
    # Longest ref first, so Art. 5(1)(f) is rendered before Art. 5(1) eats its opening.
    for citation in sorted(scan_citations(text), key=lambda c: len(c.ref), reverse=True):
        text = text.replace(citation.ref, de_ref(citation.ref))
    return text


def _one_question_bubble(text: str) -> str:
    """The chat marks a turn's last paragraph as the question it asks, so the paragraph
    that asks and whatever the character says after it stay one paragraph (D131)."""
    paragraphs = re.split(r"\n\s*\n", text)
    asking = max((i for i, paragraph in enumerate(paragraphs) if "?" in paragraph), default=None)
    if asking is None:
        return text
    return "\n\n".join([*paragraphs[:asking], "\n".join(p.strip() for p in paragraphs[asking:])])


def _confirm_label(locale: str, hint: InputHint, final_text: str) -> InputHint:
    """ "Ja, weiter" answers "Klar soweit?", also when the character signs off after it
    (D141). A message that does not ask it, like the reply to a no, offers Weiter."""
    if (
        hint.kind != "confirm"
        or hint.label != t(locale, "clear_yes")
        or t(locale, "clear_so_far") in final_text
    ):
        return hint
    return hint.model_copy(update={"label": t(locale, "continue_label")})


def _message_text(turn: TurnScratch) -> str:
    if turn.closing_line and turn.closing_line not in turn.draft:
        return f"{turn.draft}\n\n{turn.closing_line}"
    return turn.draft


def _rewrite_prompt(
    persona: PersonaManifest,
    locale: str,
    mood: Mood,
    brief_text: str,
    text: str,
    previous: str | None,
    notes: str | None,
) -> str:
    blocks = [
        "Rewrite the German tutor message below in the character's voice. Return only the "
        "rewritten German text.",
        f"Persona voice: {persona.voice}",
        "Persona style rules:\n" + "\n".join(f"- {rule}" for rule in persona.style_rules),
    ]
    guide = persona.prompts.get(locale)
    if guide:
        blocks.append(f"Persona guide:\n{guide}")
    blocks.append(f"The situation:\n{brief_text}")
    if mood is Mood.happy:
        blocks.append(
            "Tutor mood: happy. The student just answered correctly. Open on short, genuine "
            "praise of the answer in the character's voice, a different line every time. "
            "Praise the answer, never the student as a person."
        )
    elif mood is Mood.disappointed:
        blocks.append(
            "Tutor mood: disappointed. The student just answered wrongly. Open kindly, in "
            "the character's voice, and spur them on without belittling."
        )
    else:
        blocks.append(
            f"Tutor mood: {mood.value}. The opener passes no verdict on an answer: the "
            "message's own words are the verdict."
        )
    blocks.append(VOICE_RULES if persona.spice else NO_SPICE_LINE)
    if previous is not None:
        blocks.append(
            f"Your previous rewrite:\n{previous}\n\nThe critic's notes:\n{notes}\n\n"
            "Rewrite it again. Keep the character, fix what the notes name."
        )
    blocks.append(f"The tutor's message:\n{text}")
    return mark("\n\n".join(blocks), PERSONA)


def _ask(model, prompt: str) -> str:
    return str(with_retry(lambda: model.invoke([SystemMessage(prompt)])).content).strip()


def voice_rewrite(
    model,
    persona: PersonaManifest,
    locale: str,
    mood: Mood,
    brief_text: str,
    text: str,
    previous: str | None = None,
    notes: str | None = None,
    opening: bool = False,
) -> str:
    """One rewrite of the text in the persona's voice. `opening` says the course's first
    message already opened on the character's set greeting. One function for the graph node
    and for `tools/persona_probe.py`."""
    prompt = _rewrite_prompt(persona, locale, mood, brief_text, text, previous, notes)
    if opening:
        prompt += OPENING_NOTE
    return _ask(model, prompt)


def persona_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        locale = state.get("locale", "de")
        turn = state["turn"]
        text = _message_text(turn)
        persona = deps.persona(state.get("persona_id"))
        # The course's first message opens on the persona's set greeting, which the
        # student has already seen stream in before this node ran.
        opening = state.get("opening_line", "") if not state.get("messages") else ""
        question = deps.question(turn.context_question) if turn.context_question else None
        # The verdict leads the reply: the stage and the turn's ui events stream before
        # the first word, so flash and confetti fire as the tutor starts, not after he
        # has spoken.
        # Direct node invocation runs outside a runnable context; emission is best-effort.
        try:
            writer = get_stream_writer()
        except RuntimeError:
            writer = None
        if writer is not None:
            english = state.get("display_locale", "de") == "en"
            writer(
                {
                    "type": "ui",
                    "name": "stage",
                    "payload": build_stage(
                        deps.content,
                        deps.settings.personas_dir,
                        state,
                        titles_en=chapter_titles_en(deps) if english else None,
                    ),
                }
            )
            for event in ui_events(turn):
                writer(event)
        # A curated reaction is the character's own words already (turn.voiced), and a case
        # turn is the pool question and nothing else (D96): neither is rewritten.
        rewrite = (
            persona is not None
            and bool(turn.draft)
            and not turn.voiced
            and not (question is not None and turn.draft.strip() == question.question)
        )
        if rewrite:
            brief = Brief.from_text(turn.brief or build_brief(deps, state, "curated").text())
            mood = Mood(state.get("mood", Mood.neutral))
            model = deps.models[deps.settings.persona_model_role]
            governed = govern(
                "voice",
                lambda previous, notes: voice_rewrite(
                    model,
                    persona,
                    locale,
                    mood,
                    brief.text(),
                    text,
                    previous,
                    notes,
                    bool(opening),
                ),
                lambda candidate: critique_voice(deps, brief, text, candidate),
                deadline(state, deps.settings),
                lambda step: announce(deps, state, "voicing" if step == "writing" else step),
            )
            if governed.shipped:
                text = governed.text
        final_text = f"{opening}\n\n{plain_text(text)}" if opening else plain_text(text)
        if turn.input_hint.asks:
            final_text = _one_question_bubble(final_text)
        turn = turn.model_copy(
            update={"input_hint": _confirm_label(locale, turn.input_hint, final_text)}
        )
        # The student reads only what survives: the final text streams as one piece,
        # after the verdict and before the parts, so no discarded attempt and no later
        # swap reaches the page. In an English session the translate node streams the
        # final text and the translated parts and hint instead.
        if writer is not None and state.get("display_locale", "de") != "en":
            writer({"type": "token", "text": final_text})
            for event in settle_events(turn):
                writer(event)
        message = AIMessage(
            final_text,
            additional_kwargs={
                "parts": [part_out(part).model_dump(mode="json") for part in turn.parts],
                "hint": turn.input_hint.model_dump(mode="json"),
            },
        )
        return {"messages": [message], "last_hint": turn.input_hint, "turn": turn}

    return node
