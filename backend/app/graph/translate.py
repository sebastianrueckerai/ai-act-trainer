import re
from typing import Any

import structlog
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.config import get_stream_writer

from app.api.chat_events import part_out
from app.content.citations import en_ref, find_german_citations
from app.graph.deps import GraphDeps
from app.graph.events import settle_out
from app.graph.prompts import (
    TRANSLATE,
    TRANSLATE_FIELDS,
    TRANSLATE_FIELDS_RULE,
    TRANSLATE_RULE,
    mark,
)
from app.graph.state import (
    ChapterDonePart,
    ChapterStartPart,
    CitationPart,
    FilePart,
    InputHint,
    ModelAnswerCard,
    Part,
    SessionState,
)
from app.graph.working import announce
from app.i18n import t
from app.llm.retry import with_retry

log = structlog.get_logger(__name__)

_NUMBERED = re.compile(r"^\s*(\d+)\s*:\s*(.*)$")
_TOKEN = re.compile(r"⟦(\d+)⟧")
_INVENTED_CITATION = re.compile(r"\s?\((?:Art\.|Recital|Annex|Section|Q&A)(?:[^()]|\([^()]*\))*\)")


def _mask_citations(text: str) -> tuple[str, list[str]]:
    """The text with every German written citation swapped for a numbered ⟦n⟧ token, and the
    raw ref each token stands for, so a citation never reaches the model at all."""
    found = find_german_citations(text)
    pieces = []
    refs: list[str] = []
    pos = 0
    for span, ref in found:
        pieces.append(text[pos : span[0]])
        refs.append(ref)
        pieces.append(f"⟦{len(refs)}⟧")
        pos = span[1]
    pieces.append(text[pos:])
    return "".join(pieces), refs


def _restore_citations(text: str, refs: list[str]) -> str:
    """Drops anything parenthesised that looks like a citation the model wrote itself, then
    renders every surviving token in English; a token the model dropped simply disappears."""
    text = _INVENTED_CITATION.sub("", text)

    def restore(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        return en_ref(refs[index]) if 0 <= index < len(refs) else ""

    return _TOKEN.sub(restore, text)


def _english_citation(text: str) -> str:
    """A citation already rendered for display, in English: replaces a German written form
    found inside it, or reads the whole string as a raw ref when it carries none."""
    found = find_german_citations(text)
    if not found:
        return en_ref(text)
    pieces = []
    pos = 0
    for (start, end), ref in found:
        pieces.append(text[pos:start])
        pieces.append(en_ref(ref))
        pos = end
    pieces.append(text[pos:])
    return "".join(pieces)


def translate_text(model, text: str) -> str:
    """Tagged "translate_text" so the SSE stream can tell this reply apart from the
    untranslated numbered list translate_fields sends through the same node."""
    if not text:
        return ""
    masked, refs = _mask_citations(text)
    prompt = mark(TRANSLATE_RULE + "\n\n" + masked, TRANSLATE)
    reply = with_retry(
        lambda: model.invoke([SystemMessage(prompt)], config={"tags": ["translate_text"]})
    )
    return _restore_citations(str(reply.content).strip(), refs)


def translate_fields(model, fields: list[str]) -> list[str]:
    if not fields:
        return []
    numbered = "\n".join(f"{i}: {field}" for i, field in enumerate(fields, 1))
    prompt = mark(TRANSLATE_FIELDS_RULE + "\n\n" + numbered, TRANSLATE_FIELDS)
    reply = str(with_retry(lambda: model.invoke([SystemMessage(prompt)])).content)
    found: dict[int, str] = {}
    for line in reply.splitlines():
        match = _NUMBERED.match(line)
        if match:
            found[int(match.group(1))] = match.group(2).strip()
    return [found.get(i, field) for i, field in enumerate(fields, 1)]


def chapter_titles_en(deps: GraphDeps) -> dict[str, str]:
    """The English chapter titles for the stage, rendered once per process. Empty when
    the rendering fails, so the stage shows German and the next read tries again."""
    if not deps.titles_en:
        chapters = deps.chapters("de")
        try:
            english = translate_fields(deps.models["fast"], [chapter.title for chapter in chapters])
        except Exception as error:
            log.warning("chapter titles rendering failed", error=str(error))
            return {}
        deps.titles_en.update(zip((chapter.id for chapter in chapters), english, strict=True))
    return deps.titles_en


def parts_from_dumps(dumps: list[dict[str, Any]]) -> list[Part]:
    """A stored turn's parts back from their PartOut dumps. The models ignore `kind`."""
    parts: list[Part] = []
    for dump in dumps:
        kind = dump.get("kind")
        if kind == "card":
            parts.append(ModelAnswerCard.model_validate(dump))
        elif kind == "file":
            parts.append(FilePart.model_validate(dump))
        elif kind == "chapter_done":
            parts.append(ChapterDonePart.model_validate(dump))
        elif kind == "chapter_start":
            parts.append(ChapterStartPart.model_validate(dump))
        else:
            parts.append(CitationPart.model_validate(dump))
    return parts


def render_en(model, text: str, parts: list[Part], hint: InputHint | None) -> dict[str, Any]:
    """The English rendering of one message: its text, its parts as PartOut dumps in the
    English display form, and its hint with English labels, null when it has none. Two
    model calls whatever the message carries: the text, then every field in one list."""
    en_text = translate_text(model, text)
    cards = [p for p in parts if isinstance(p, ModelAnswerCard)]
    citation_parts = [p for p in parts if isinstance(p, CitationPart)]
    file_parts = [p for p in parts if isinstance(p, FilePart)]
    done_parts = [p for p in parts if isinstance(p, ChapterDonePart)]
    start_parts = [p for p in parts if isinstance(p, ChapterStartPart)]
    choices = hint.choices if hint is not None else []

    fields: list[str] = []
    for card in cards:
        fields.extend([card.question, card.model_answer, card.explanation])
        fields.extend(c.title for c in card.citations)
    fields.extend(part.title for part in citation_parts)
    fields.extend(part.title for part in file_parts)
    fields.extend(part.title for part in done_parts)
    for part in start_parts:
        fields.extend([part.title, part.intro])
    fields.extend(choice.label for choice in choices)
    if hint is not None and hint.label is not None:
        fields.append(hint.label)
    translated = iter(translate_fields(model, fields))

    new_cards = []
    for card in cards:
        question, model_answer, explanation = next(translated), next(translated), next(translated)
        citations = [
            c.model_copy(update={"ref": _english_citation(c.ref), "title": next(translated)})
            for c in card.citations
        ]
        new_cards.append(
            card.model_copy(
                update={
                    "question": question,
                    "model_answer": model_answer,
                    "explanation": explanation,
                    "citations": citations,
                }
            )
        )
    original = t("en", "citation_original_de")
    new_citation_parts = [
        part.model_copy(
            update={
                "ref": _english_citation(part.ref),
                "title": next(translated),
                "quote": f"{original} {part.quote}",
            }
        )
        for part in citation_parts
    ]
    new_file_parts = [part.model_copy(update={"title": next(translated)}) for part in file_parts]
    new_done_parts = [part.model_copy(update={"title": next(translated)}) for part in done_parts]
    new_start_parts = [
        part.model_copy(update={"title": next(translated), "intro": next(translated)})
        for part in start_parts
    ]
    new_choices = [choice.model_copy(update={"label": next(translated)}) for choice in choices]
    new_hint = None
    if hint is not None:
        new_hint = hint.model_copy(update={"choices": new_choices})
        if hint.label is not None:
            new_hint = new_hint.model_copy(update={"label": next(translated)})

    rendered = {
        ModelAnswerCard: iter(new_cards),
        CitationPart: iter(new_citation_parts),
        FilePart: iter(new_file_parts),
        ChapterDonePart: iter(new_done_parts),
        ChapterStartPart: iter(new_start_parts),
    }
    new_parts: list[Part] = [next(rendered[type(part)]) for part in parts]
    return {
        "text": en_text,
        "parts": [part_out(p, localize=False).model_dump(mode="json") for p in new_parts],
        "hint": new_hint.model_dump(mode="json") if new_hint is not None else None,
    }


def translate_node(deps: GraphDeps):
    def node(state: SessionState) -> dict:
        if state.get("display_locale", "de") != "en":
            return {}
        announce(deps, state, "translating")
        model = deps.models["fast"]
        turn = state["turn"]
        last = next(m for m in reversed(state["messages"]) if isinstance(m, AIMessage))
        text = str(last.content)
        # The course's first message opens on the greeting the student already read in
        # English before the graph ran: render the body, store the whole.
        prefix = f"{state.get('opening_line', '')}\n\n"
        opening_en = state.get("opening_line_en", "")
        first = bool(opening_en) and text.startswith(prefix)
        body = text[len(prefix) :] if first else text
        rendering = render_en(model, body, turn.parts, turn.input_hint)
        streamed = rendering["text"]
        if first:
            rendering["text"] = f"{opening_en}\n\n{streamed}"
        # The German stays the stored truth and everything the graph reads; the
        # rendering rides along and the serving side picks by display locale.
        message = AIMessage(
            id=last.id,
            content=text,
            additional_kwargs={**last.additional_kwargs, "en": rendering},
        )
        # The English reply streams as what it settles into, refs and fields included:
        # nothing the student read changes later.
        try:
            writer = get_stream_writer()
        except RuntimeError:
            writer = None
        if writer is not None:
            if streamed:
                writer({"type": "token", "text": streamed})
            for event in settle_out(rendering["parts"], rendering["hint"]):
                writer(event)
        return {"messages": [message]}

    return node
