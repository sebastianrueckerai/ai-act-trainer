from app.api.chat_events import (
    CardOut,
    CitationsOut,
    ErrorEvent,
    FileOut,
    InputHintEvent,
    MessageEvent,
    PartEvent,
    StatusEvent,
    TokenEvent,
    UiPayloadEvent,
    WorkingEvent,
    format_sse,
    part_out,
)
from app.graph.state import CitationPart, FilePart, InputHint, ModelAnswerCard

CITATION = CitationPart(
    ref="KI-VO Art. 14",
    title="Verordnung (EU) 2024/1689",
    quote="…menschengeführt…",
    url="https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
)
CARD = ModelAnswerCard(
    question="Darf ich KI für die Einstellung nutzen?",
    model_answer="Ja, mit menschlicher Letztentscheidung.",
    explanation="Art. 14 AI Act verlangt menschliche Aufsicht.",
    citations=[CITATION],
    correct=True,
)
FILE = FilePart(
    url="/api/files/abc",
    title="Spickzettel: Der ganze Kurs",
    filename="spickzettel-kurs.pdf",
)


def test_part_out_tags_a_card() -> None:
    out = part_out(CARD)
    assert out == CardOut(
        kind="card",
        question=CARD.question,
        model_answer=CARD.model_answer,
        explanation=CARD.explanation,
        citations=[part_out(CITATION)],
        correct=True,
    )


def test_part_out_carries_the_try_count_for_a_settled_card() -> None:
    settled = CARD.model_copy(update={"tries": 2})
    out = part_out(settled)
    assert out.tries == 2


def test_part_out_tags_a_citation() -> None:
    out = part_out(CITATION)
    assert out == CitationsOut(
        kind="citations",
        ref="KI-VO Art. 14",
        title=CITATION.title,
        quote=CITATION.quote,
        url=CITATION.url,
    )


def test_part_out_prints_the_ref_in_german() -> None:
    card = CARD.model_copy(
        update={
            "citations": [
                CITATION.model_copy(update={"ref": ref})
                for ref in ("GDPR Art. 6(1)(f)", "Rec. 44", "Art. 26(7)")
            ]
        }
    )
    assert [out.ref for out in part_out(card).citations] == [
        "Art. 6 Abs. 1 Buchst. f DSGVO",
        "EG 44",
        "Art. 26 Abs. 7",
    ]
    citation = CITATION.model_copy(update={"ref": "Annex III pt. 4(a)"})
    assert part_out(citation).ref == "Anhang III Nr. 4 Buchst. a"


def test_part_out_tags_a_file() -> None:
    out = part_out(FILE)
    assert out == FileOut(
        kind="file",
        url="/api/files/abc",
        title=FILE.title,
        filename=FILE.filename,
    )


def test_event_discriminator_round_trips() -> None:
    hint = InputHint(kind="yes_no")
    events = [
        (StatusEvent(node="triage"), "status"),
        (WorkingEvent(step="grading", text="prüft deine Antwort"), "working"),
        (TokenEvent(text="Gut"), "token"),
        (UiPayloadEvent(name="confetti", payload={}), "ui"),
        (PartEvent(part=part_out(CARD)), "part"),
        (InputHintEvent(hint=hint), "input_hint"),
        (MessageEvent(text="Fertig.", parts=[part_out(CITATION)], hint=hint), "message"),
        (ErrorEvent(code="turn_failed", message="boom"), "error"),
    ]
    for event, name in events:
        dumped = event.model_dump()
        assert dumped["event"] == name
    assert StatusEvent.model_validate(StatusEvent(node="x").model_dump()).node == "x"
    assert (
        MessageEvent.model_validate_json(
            MessageEvent(text="t", parts=[], hint=hint).model_dump_json()
        ).hint
        == hint
    )


def test_format_sse_frames_an_event() -> None:
    frame = format_sse(StatusEvent(node="persona"))
    lines = frame.splitlines()
    assert lines[0] == "event: status"
    assert lines[1].startswith("data: ")
    import json

    payload = json.loads(lines[1][len("data: ") :])
    assert payload == {"event": "status", "node": "persona"}
    assert frame.endswith("\n\n")
