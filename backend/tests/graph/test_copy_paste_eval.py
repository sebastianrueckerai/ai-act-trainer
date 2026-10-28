from app.graph.critic import Critique
from app.graph.grade import Verdict
from tests.evals.copy_paste_eval import partial_answer, render, run_copy_paste


def test_a_partial_answer_is_the_first_must_point_in_plain_words(make_deps):
    assert partial_answer(make_deps(), "q-01-12") == (
        "Dass du dafür geradestehst, nicht der Anbieter des Werkzeugs und nicht die KI."
    )


def test_every_free_text_question_is_pasted_back_plain_and_in_each_persona(make_deps):
    # One verdict serves every call: the student's try and the paste-back both credit the
    # first point and nothing else, so nothing leaks and every row is present.
    deps = make_deps(
        script={
            "grade": Verdict(correct=False, matched=[1], missing=[2]),
            "reply": "Richtig, so weit.\n\nAber worauf kommt es noch an?",
            "critic": Critique(verdict="ship", score=5),
            "voice_critic": Critique(verdict="ship", score=5),
            "persona": "<echo>",
        }
    )
    results = run_copy_paste(deps, ["jester"])
    free_text = [
        q
        for q in deps.locale_content("de").questions.values()
        if q.type == "free_text" and len(q.rubric.must) > 1
    ]
    assert len(results) == 2 * len(free_text)
    assert {r.persona for r in results} == {"none", "jester"}
    assert not [r for r in results if r.leaked]
    assert render(results).endswith(f"summary: 0 of {len(results)} replies leaked")


def test_a_pasted_reply_the_grader_credits_counts_as_a_leak(make_deps):
    # The critic shipped the draft and the paste-back credits it; the paste-back is the
    # verdict that counts.
    deps = make_deps(
        script={
            "grade": [
                Verdict(correct=False, matched=[1], missing=[2]),
                Verdict(correct=False, matched=[1, 2]),
            ],
            "reply": "Richtig, und prüfen musst du es auch, oder?",
            "critic": Critique(verdict="ship", score=5),
        }
    )
    results = run_copy_paste(deps, [], question_ids=["q-02-04"])
    assert [r.leaked for r in results] == [True]
    assert "leaked=yes" in render(results)
    # The paste-back grader reads the whole exchange, the reply as the tutor's last line.
    grade_prompts = [
        p
        for p, c in zip(deps.models["strong"].prompts, deps.models["strong"].calls, strict=True)
        if c == "grade"
    ]
    paste = "Student: Dass du prüfst, ob unser Zweck die Daten über die Kunden trägt."
    assert paste in grade_prompts[-1]
    assert "Tutor: Richtig, und prüfen musst du es auch, oder?" in grade_prompts[-1]
