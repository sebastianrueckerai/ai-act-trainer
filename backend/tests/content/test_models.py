import pytest
from pydantic import ValidationError

from app.content.models import MustPoint, Option, PersonaManifest, Question, Rubric


def _must(text: str) -> MustPoint:
    return MustPoint(point=text, ask="Und?")


BASE = {
    "id": "q-01-01",
    "chapter": "01-test",
    "difficulty": 1,
    "question": "Frage?",
    "model_answer": "Antwort.",
    "explanation": "Erklärung.",
    "citations": ["Art. 4"],
    "last_change": {
        "date": "2026-09-15",
        "by": "human",
        "trigger": "initial",
        "summary": "written",
    },
}


def test_yes_no_requires_correct_yes_or_no_and_nothing_else():
    q = Question(**BASE, type="yes_no", correct="yes")
    assert q.correct == "yes"
    with pytest.raises(ValidationError, match="correct"):
        Question(**BASE, type="yes_no", correct="A")
    with pytest.raises(ValidationError, match="options"):
        Question(**BASE, type="yes_no", correct="yes", options=[Option(key="A", text="x")])


def test_multiple_choice_requires_two_options_and_a_matching_key():
    options = [Option(key=k, text=f"Option {k}") for k in "ABC"]
    q = Question(**BASE, type="multiple_choice", correct="B", options=options)
    assert [o.key for o in q.options] == ["A", "B", "C"]
    pair = Question(**BASE, type="multiple_choice", correct="A", options=options[:2])
    assert len(pair.options) == 2
    with pytest.raises(ValidationError, match="options"):
        Question(**BASE, type="multiple_choice", correct="A", options=options[:1])
    with pytest.raises(ValidationError, match="correct"):
        Question(**BASE, type="multiple_choice", correct="D", options=options)


def test_a_closed_question_carries_a_why_rubric():
    rubric = Rubric(
        must=[
            MustPoint(point="nennt, dass der Chef recht hat"),
            MustPoint(point="begründet es mit der Untergrenze", ask="Was sagst du dem Kollegen?"),
        ]
    )
    q = Question(
        **BASE,
        type="multiple_choice",
        correct="A",
        options=[
            Option(key="A", text="Der Chef hat recht: die Anweisung gilt."),
            Option(key="B", text="Der Kollege hat recht: ohne Verordnung gilt sie nicht."),
        ],
        rubric=rubric,
    )
    assert q.rubric is not None
    assert q.rubric.next_ask([]) is None
    assert q.rubric.next_ask(["nennt, dass der Chef recht hat"]) == "Was sagst du dem Kollegen?"


def test_a_closed_rubrics_first_point_is_the_pick_and_carries_no_ask():
    with pytest.raises(ValidationError, match="pick"):
        Question(
            **BASE,
            type="yes_no",
            correct="yes",
            rubric=Rubric(
                must=[
                    MustPoint(point="die Position", ask="Welche?"),
                    MustPoint(point="der Grund", ask="Warum?"),
                ]
            ),
        )


def test_every_why_point_of_a_closed_question_needs_an_ask():
    with pytest.raises(ValidationError, match="needs an ask"):
        Question(
            **BASE,
            type="yes_no",
            correct="yes",
            rubric=Rubric(must=[MustPoint(point="die Position"), MustPoint(point="der Grund")]),
        )


def test_free_text_requires_a_rubric_and_no_correct_key():
    q = Question(**BASE, type="free_text", rubric=Rubric(must=[_must("nennt Art. 4")], should=[]))
    assert q.rubric is not None
    with pytest.raises(ValidationError, match="rubric"):
        Question(**BASE, type="free_text")
    with pytest.raises(ValidationError, match="correct"):
        Question(**BASE, type="free_text", correct="yes", rubric=Rubric(must=[_must("x")]))


def test_a_must_point_carries_an_ask_that_ends_in_a_question_mark():
    point = MustPoint(point="nennt den Anbieter", ask="Wer stellt das System bereit?")
    assert point.ask.endswith("?")
    with pytest.raises(ValidationError, match="question mark"):
        MustPoint(point="nennt den Anbieter", ask="Der Anbieter.")
    with pytest.raises(ValidationError):
        MustPoint(point="nennt den Anbieter", ask="")


def test_a_question_ends_in_a_question_mark():
    rubric = Rubric(must=[_must("nennt Art. 4")])
    with pytest.raises(ValidationError, match="question mark"):
        Question(**{**BASE, "question": "Nenne den Anbieter."}, type="free_text", rubric=rubric)


def test_next_ask_is_the_first_unmet_must_points_question():
    rubric = Rubric(
        must=[
            MustPoint(point="nennt A", ask="Was ist A?"),
            MustPoint(point="nennt B", ask="Und B?"),
        ],
        should=["nennt C"],
    )
    assert rubric.must_texts == ["nennt A", "nennt B"]
    assert rubric.next_ask([]) == "Was ist A?"
    assert rubric.next_ask(["nennt A"]) == "Und B?"
    assert rubric.next_ask(["nennt B"]) == "Was ist A?"
    assert rubric.next_ask(["nennt A", "nennt B"]) is None
    assert rubric.next_ask(["nennt C"]) == "Was ist A?"


PERSONA_BASE = {
    "id": "testbot",
    "name": {"de": "Testbot", "en": "Testbot"},
    "tagline": {"de": "Nur zum Testen", "en": "Only for tests"},
    "voice": "Neutral test persona.",
    "style_rules": ["Say little."],
    "verdicts": {"right": ["Stimmt."], "wrong": ["Leider nicht."]},
    "milestones": {"chapter": ["Eins.", "Zwei.", "Drei."], "course": ["Fertig."]},
}
REACTIONS = {
    "cheat": "No.",
    "insult": "Hm.",
    "profanity": "Ok.",
    "humor": "Ha.",
    "offtopic": "Back.",
}


def test_persona_manifest_requires_a_right_and_a_wrong_verdict_line():
    base = {key: value for key, value in PERSONA_BASE.items() if key != "verdicts"}
    with pytest.raises(ValidationError, match="lacks verdict lines for: wrong"):
        PersonaManifest(**base, reactions=REACTIONS, verdicts={"right": ["Stimmt."]})
    with pytest.raises(ValidationError, match="lacks verdict lines for: right"):
        PersonaManifest(**base, reactions=REACTIONS, verdicts={"right": [], "wrong": ["Nein."]})
    persona = PersonaManifest(**PERSONA_BASE, reactions=REACTIONS)
    assert persona.verdicts["wrong"] == ["Leider nicht."]


def test_persona_manifest_requires_three_chapter_lines_and_one_course_line():
    base = {key: value for key, value in PERSONA_BASE.items() if key != "milestones"}
    with pytest.raises(ValidationError, match="needs milestone lines"):
        PersonaManifest(**base, reactions=REACTIONS)
    with pytest.raises(ValidationError, match="'chapter': 2, 'course': 1"):
        PersonaManifest(
            **base, reactions=REACTIONS, milestones={"chapter": ["a", "b"], "course": ["c"]}
        )
    with pytest.raises(ValidationError, match="'chapter': 3, 'course': 2"):
        PersonaManifest(
            **base,
            reactions=REACTIONS,
            milestones={"chapter": ["a", "b", "c"], "course": ["d", "e"]},
        )
    persona = PersonaManifest(**PERSONA_BASE, reactions=REACTIONS)
    assert persona.milestones["course"] == ["Fertig."]


def test_persona_manifest_requires_every_reaction_key():
    with pytest.raises(ValidationError, match="lacks reactions for: humor, offtopic, profanity"):
        PersonaManifest(**PERSONA_BASE, reactions={"cheat": "No.", "insult": "Hm."})
    persona = PersonaManifest(
        **PERSONA_BASE,
        reactions={
            "cheat": "No.",
            "insult": "Hm.",
            "profanity": "Ok.",
            "humor": "Ha.",
            "offtopic": "Back.",
        },
    )
    assert set(persona.reactions) == {"cheat", "insult", "profanity", "humor", "offtopic"}


def test_a_manifest_refuses_a_working_step_the_turn_does_not_have():
    with pytest.raises(ValidationError, match="unknown working steps"):
        PersonaManifest(
            id="x",
            name={"de": "X"},
            tagline={"de": "x"},
            voice="v",
            style_rules=["r"],
            reactions={
                "cheat": "a",
                "insult": "b",
                "profanity": "c",
                "humor": "d",
                "offtopic": "e",
            },
            verdicts={"right": ["r"], "wrong": ["w"]},
            milestones={"chapter": ["a", "b", "c"], "course": ["d"]},
            working={"dreaming": ["z"]},
        )
