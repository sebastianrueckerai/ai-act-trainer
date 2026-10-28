from app.graph.grade import ProseChoice, Verdict
from tests.evals.paste_back import STATES_THE_ANSWER, gives_away

MUST_ALLOWED = "nennt, dass du prüfst, ob unser Zweck die Daten über die Kunden trägt"
MUST_COMPETENCE = "nennt, dass du prüfst, ob etwas drin ist, das das Haus geheim hält"


def test_a_draft_that_states_a_missing_point_is_a_leak(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=False, attempt=False, matched=[2])})
    credited = gives_away(
        deps, deps.question("q-02-04"), "Prüf halt das Ergebnis.", [MUST_COMPETENCE]
    )
    assert credited == [MUST_COMPETENCE]


def test_a_draft_that_confirms_a_met_point_is_no_leak(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=False, matched=[1], missing=[2])})
    credited = gives_away(
        deps, deps.question("q-02-04"), "Richtig, das ist erlaubt.", [MUST_COMPETENCE]
    )
    assert credited == []


def test_the_paste_back_grades_the_draft_leniently_with_the_step(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=False, matched=[], missing=[1, 2])})
    gives_away(deps, deps.question("q-02-04"), "Denk nach.", [MUST_ALLOWED], step="Der Schritt.")
    prompt = deps.models["strong"].prompts[-1]
    assert "Der Schritt." in prompt
    assert "practice question inside the chapter" in prompt


def test_nothing_missing_means_no_call_and_no_leak(make_deps):
    deps = make_deps(script={})
    assert gives_away(deps, deps.question("q-02-04"), "Genau.", []) == []
    assert deps.models["strong"].calls == []


def test_a_yes_no_draft_that_commits_to_the_answer_is_a_leak(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="yes")})
    credited = gives_away(deps, deps.question("q-01-01"), "Das darfst du schon.", [])
    assert credited == [STATES_THE_ANSWER]


def test_a_yes_no_draft_that_commits_to_nothing_is_no_leak(make_deps):
    deps = make_deps(script={"prose": ProseChoice(answer="unclear")})
    assert gives_away(deps, deps.question("q-01-01"), "Überleg, wer entscheidet.", []) == []


def test_a_choice_draft_that_quotes_the_right_option_beside_a_wrong_one_is_a_leak(make_deps):
    # The right option's text in the draft is the answer whatever stands next to it.
    deps = make_deps(script={})
    question = deps.question("q-01-03")
    right = next(o.text for o in question.options if o.key == "B")
    wrong = next(o.text for o in question.options if o.key == "C")
    draft = f"Es ist nicht {wrong}, sondern {right}. Welche nimmst du?"
    assert gives_away(deps, question, draft, []) == [STATES_THE_ANSWER]
    assert deps.models["fast"].calls == []


def test_a_choice_draft_that_names_the_right_option_is_a_leak(make_deps):
    # "Nimm B." is no bare option letter, so the prose model resolves it, as for a student.
    deps = make_deps(script={"prose": ProseChoice(answer="B")})
    credited = gives_away(deps, deps.question("q-01-03"), "Nimm B.", [])
    assert credited == [STATES_THE_ANSWER]
    assert deps.models["fast"].calls == ["prose"]


def test_the_paste_back_grader_sees_the_conversation_and_the_reply_as_the_tutor_line(make_deps):
    deps = make_deps(script={"grade": Verdict(correct=False, matched=[1], missing=[2])})
    draft = "Richtig. Was tust du, bevor die Mail rausgeht?"
    gives_away(
        deps,
        deps.question("q-02-04"),
        draft,
        [MUST_COMPETENCE],
        step="Der Schritt.",
        recent=["Tutor: Die Frage?", "Student: Erlaubt."],
    )
    prompt = deps.models["strong"].prompts[-1]
    assert "Tutor: Die Frage?\nStudent: Erlaubt.\nTutor: " + draft in prompt
    assert prompt.index("Tutor: " + draft) < prompt.index(f"Student: {draft}")
