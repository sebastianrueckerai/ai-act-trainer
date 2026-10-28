import shutil
from pathlib import Path

import pytest
import yaml

from app.content.lint import lint
from app.content.loader import load_content

FIXTURES = Path(__file__).parent / "fixtures"
# The fixture course is a mini course and cannot carry six hundred law summaries, so every
# lint over it reads the repo's real summaries.
REPO_LAW = Path(__file__).resolve().parents[3] / "content" / "de" / "law"


def test_load_content_reads_every_locale_and_persona():
    bundle = load_content(FIXTURES / "content", FIXTURES / "personas")
    assert set(bundle.locales) == {"de", "en"}
    assert set(bundle.locales["de"].chapters) == {"01-test", "02-stub"}
    assert set(bundle.locales["de"].questions) == {"q-01-01", "q-01-02", "q-01-03"}
    assert bundle.personas["testbot"].name["de"] == "Testbot"


def test_lint_passes_on_the_fixture(library):
    bundle = load_content(FIXTURES / "content", FIXTURES / "personas", law_dir=REPO_LAW)
    assert lint(bundle, library) == []


def test_overlay_replaces_a_file(tmp_path: Path, library):
    overlay = tmp_path / "overlay"
    (overlay / "de" / "chapters").mkdir(parents=True)
    (overlay / "en" / "chapters").mkdir(parents=True)
    for locale in ("de", "en"):
        source = FIXTURES / "content" / locale / "chapters" / "01-test.yaml"
        text = source.read_text(encoding="utf-8").replace(
            "duration_minutes: 3", "duration_minutes: 9"
        )
        (overlay / locale / "chapters" / "01-test.yaml").write_text(text, encoding="utf-8")
    bundle = load_content(
        FIXTURES / "content", FIXTURES / "personas", overlay_dir=overlay, law_dir=REPO_LAW
    )
    assert bundle.locales["de"].chapters["01-test"].duration_minutes == 9
    assert lint(bundle, library) == []


def test_overlay_adds_a_new_question(tmp_path: Path, library):
    overlay = tmp_path / "overlay"
    texts = {
        "de": (
            "id: q-01-04\n"
            "chapter: 01-test\n"
            "type: yes_no\n"
            "difficulty: 1\n"
            "question: Gilt Art. 4 auch für Betreiber?\n"
            'correct: "yes"\n'
            "model_answer: Ja.\n"
            "explanation: Art. 4(1) nennt Anbieter und Betreiber.\n"
            'citations: ["Art. 4(1)"]\n'
            "last_change: {date: 2026-09-15, by: human, trigger: initial, summary: fixture}\n"
        ),
        "en": (
            "id: q-01-04\n"
            "chapter: 01-test\n"
            "type: yes_no\n"
            "difficulty: 1\n"
            "question: Does Art. 4 also apply to deployers?\n"
            'correct: "yes"\n'
            "model_answer: Yes.\n"
            "explanation: Art. 4(1) names providers and deployers.\n"
            'citations: ["Art. 4(1)"]\n'
            "last_change: {date: 2026-09-15, by: human, trigger: initial, summary: fixture}\n"
        ),
    }
    for locale, text in texts.items():
        folder = overlay / locale / "questions"
        folder.mkdir(parents=True)
        (folder / "q-01-04.yaml").write_text(text, encoding="utf-8")
    bundle = load_content(
        FIXTURES / "content", FIXTURES / "personas", overlay_dir=overlay, law_dir=REPO_LAW
    )
    assert "q-01-04" in bundle.locales["de"].questions
    assert lint(bundle, library) == []


def test_load_content_rejects_an_id_that_disagrees_with_the_filename(tmp_path: Path):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    chapter_path = content / "de" / "chapters" / "01-test.yaml"
    chapter_path.write_text(
        chapter_path.read_text(encoding="utf-8").replace("id: 01-test", "id: 01-renamed"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"01-renamed.*01-test|01-test.*01-renamed"):
        load_content(content, FIXTURES / "personas")


def test_lint_reports_missing_locale_item_and_bad_citation(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    (content / "en" / "questions" / "q-01-03.yaml").unlink()
    de_q1 = content / "de" / "questions" / "q-01-01.yaml"
    de_q1.write_text(
        de_q1.read_text(encoding="utf-8").replace('"Art. 4(1)"', '"Art. 999"'), encoding="utf-8"
    )
    bundle = load_content(content, FIXTURES / "personas")
    problems = lint(bundle, library)
    messages = [p.message for p in problems]
    assert any("q-01-03" in m and "en" in m for m in messages)
    assert any("Art. 999" in m for m in messages)
    assert any("citations differ" in m for m in messages)


def test_lint_refuses_a_content_directory_that_holds_nothing(tmp_path: Path, library):
    """A wrong CONTENT_DIR used to pass every check, because every loop ran zero times."""
    empty = tmp_path / "content"
    empty.mkdir()
    shutil.copy(FIXTURES / "content" / "manifest.yaml", empty / "manifest.yaml")

    bundle = load_content(empty, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)

    assert [p.where for p in problems] == ["de"]
    assert "content directory is wrong" in problems[0].message


def test_lint_refuses_a_personas_directory_that_holds_nothing(tmp_path: Path, library):
    bundle = load_content(FIXTURES / "content", tmp_path / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)

    assert [p.where for p in problems] == ["personas"]
    assert "personas directory is wrong" in problems[0].message


def test_a_stray_law_directory_under_another_locale_is_ignored(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    stray = content / "en" / "law" / "ai_act"
    stray.mkdir(parents=True)
    (stray / "_act.yaml").write_text("not a law summary\n", encoding="utf-8")

    bundle = load_content(content, FIXTURES / "personas")

    assert bundle.law == {}
    problems = lint(bundle, library)
    assert [p.where for p in problems] == ["law"]
    assert "missing entirely" in problems[0].message


def test_a_summary_naming_a_chapter_by_number_fails_the_lint(tmp_path: Path, library):
    law = tmp_path / "law"
    shutil.copytree(REPO_LAW, law)
    path = law / "ai_act" / "_act.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["summary"] = "Das Gesetz regelt KI-Systeme. Kapitel III nennt die Hochrisiko-Systeme."
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    bundle = load_content(FIXTURES / "content", FIXTURES / "personas", law_dir=law)
    problems = lint(bundle, library)

    assert any("Kapitel III" in p.message and "carries a citation" in p.message for p in problems)


def test_a_stub_chapter_loads_its_flag_and_passes_the_lint_without_questions(library):
    bundle = load_content(FIXTURES / "content", FIXTURES / "personas", law_dir=REPO_LAW)
    assert bundle.locales["de"].chapters["02-stub"].stub is True
    assert bundle.locales["de"].chapters["01-test"].stub is False
    assert lint(bundle, library) == []


def test_a_complete_chapter_missing_a_question_type_fails_the_lint(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    (content / "de" / "questions" / "q-01-02.yaml").unlink()
    (content / "en" / "questions" / "q-01-02.yaml").unlink()
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)
    assert any(
        "chapter has no multiple_choice question" in p.message and "01-test" in p.where
        for p in problems
    )


def test_a_question_on_a_stub_chapter_fails_the_lint(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    question = (
        "id: q-02-99\n"
        "chapter: 02-stub\n"
        "type: free_text\n"
        "difficulty: 1\n"
        "question: Was?\n"
        "rubric:\n  must:\n    - point: nennt irgendetwas\n      ask: Und was?\n"
        "model_answer: Etwas.\n"
        "explanation: Etwas.\n"
        'citations: ["Art. 4(1)"]\n'
        "last_change: {date: 2026-09-18, by: human, trigger: initial, summary: fixture}\n"
    )
    for locale in ("de", "en"):
        (content / locale / "questions" / "q-02-99.yaml").write_text(question, encoding="utf-8")
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)
    assert any("stub" in p.message and "q-02-99" in p.where for p in problems)


def _lint_question(tmp_path: Path, library, rubric_yaml: str, question: str = "Was?"):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    question = (
        "id: q-01-99\n"
        "chapter: 01-test\n"
        "type: free_text\n"
        "difficulty: 1\n"
        f"question: {question}\n"
        f"{rubric_yaml}"
        "model_answer: Etwas.\n"
        "explanation: Etwas.\n"
        'citations: ["Art. 4(1)"]\n'
        "last_change: {date: 2026-09-29, by: human, trigger: initial, summary: fixture}\n"
    )
    for locale in ("de", "en"):
        (content / locale / "questions" / "q-01-99.yaml").write_text(question, encoding="utf-8")
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    return lint(bundle, library)


def test_lint_rejects_an_ask_that_repeats_its_point(tmp_path, library):
    problems = _lint_question(
        tmp_path,
        library,
        "rubric:\n  must:\n    - point: nennt den Anbieter\n      ask: Nennt den Anbieter, oder?\n",
    )
    assert any("ask repeats its point" in p.message for p in problems)


def test_lint_accepts_a_closed_questions_pick_point_without_an_ask(tmp_path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    question = (
        "id: q-01-99\n"
        "chapter: 01-test\n"
        "type: multiple_choice\n"
        "difficulty: 1\n"
        "question: Wer entscheidet?\n"
        "options:\n"
        "  - {key: A, text: Unser Unternehmen entscheidet.}\n"
        "  - {key: B, text: Der Kollege entscheidet.}\n"
        "correct: A\n"
        "rubric:\n  must:\n"
        "    - point: nennt, dass das Unternehmen entscheidet\n"
        "    - point: nennt den Grund\n"
        "      ask: Und warum entscheidet das Haus?\n"
        "model_answer: Etwas.\n"
        "explanation: Etwas.\n"
        'citations: ["Art. 4(1)"]\n'
        "last_change: {date: 2026-10-02, by: human, trigger: initial, summary: fixture}\n"
    )
    for locale in ("de", "en"):
        (content / locale / "questions" / "q-01-99.yaml").write_text(question, encoding="utf-8")
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)
    assert not [p for p in problems if "q-01-99" in p.where]


def test_a_question_on_a_chapter_that_does_not_exist_fails_the_lint(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    question = (
        "id: q-03-99\n"
        "chapter: 03-nope\n"
        "type: free_text\n"
        "difficulty: 1\n"
        "question: Was?\n"
        "rubric:\n  must:\n    - point: nennt irgendetwas\n      ask: Und was?\n"
        "model_answer: Etwas.\n"
        "explanation: Etwas.\n"
        'citations: ["Art. 4(1)"]\n'
        "last_change: {date: 2026-09-18, by: human, trigger: initial, summary: fixture}\n"
    )
    for locale in ("de", "en"):
        (content / locale / "questions" / "q-03-99.yaml").write_text(question, encoding="utf-8")
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)
    assert [(p.where, p.message) for p in problems] == [
        ("de/q-03-99", "chapter 03-nope does not exist"),
        ("en/q-03-99", "chapter 03-nope does not exist"),
    ]


def test_a_step_question_must_exist(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    for locale in ("de", "en"):
        chapter = content / locale / "chapters" / "01-test.yaml"
        chapter.write_text(
            chapter.read_text(encoding="utf-8").replace("question: q-01-03", "question: q-99-99"),
            encoding="utf-8",
        )
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)
    assert [(p.where, p.message) for p in problems] == [
        ("de/01-test/s1", "step question q-99-99 does not exist"),
        ("en/01-test/s1", "step question q-99-99 does not exist"),
    ]


def test_a_step_question_must_belong_to_its_own_chapter(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    question = (
        "id: q-03-99\n"
        "chapter: 03-nope\n"
        "type: free_text\n"
        "difficulty: 1\n"
        "question: Was?\n"
        "rubric:\n  must:\n    - point: nennt irgendetwas\n      ask: Und was?\n"
        "model_answer: Etwas.\n"
        "explanation: Etwas.\n"
        'citations: ["Art. 4(1)"]\n'
        "last_change: {date: 2026-09-22, by: human, trigger: initial, summary: fixture}\n"
    )
    for locale in ("de", "en"):
        (content / locale / "questions" / "q-03-99.yaml").write_text(question, encoding="utf-8")
        chapter = content / locale / "chapters" / "01-test.yaml"
        chapter.write_text(
            chapter.read_text(encoding="utf-8").replace("question: q-01-03", "question: q-03-99"),
            encoding="utf-8",
        )
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)
    assert ("de/01-test/s1", "step question q-03-99 belongs to another chapter") in [
        (p.where, p.message) for p in problems
    ]


def test_a_step_question_may_not_repeat_a_sentence_of_its_step(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    for locale in ("de", "en"):
        chapter = content / locale / "chapters" / "01-test.yaml"
        chapter.write_text(
            chapter.read_text(encoding="utf-8").replace("question: q-01-03", "question: q-01-01"),
            encoding="utf-8",
        )
    de_q1 = content / "de" / "questions" / "q-01-01.yaml"
    de_q1.write_text(
        de_q1.read_text(encoding="utf-8").replace(
            "question: Müssen Anbieter und Betreiber für KI-Kompetenz ihres Personals sorgen?",
            "question: KI-Kompetenz ist Pflicht für Anbieter und Betreiber?",
        ),
        encoding="utf-8",
    )
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)
    assert [(p.where, p.message) for p in problems] == [
        (
            "de/01-test/s1",
            'step question repeats the step: "KI-Kompetenz ist Pflicht für Anbieter und '
            'Betreiber."',
        )
    ]


def test_lint_reports_gendered_language_in_chapter_text(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    chapter = content / "de" / "chapters" / "01-test.yaml"
    chapter.write_text(
        chapter.read_text(encoding="utf-8").replace(
            "Ein kurzes Kapitel.", "Ein kurzes Kapitel für Nutzer*innen."
        ),
        encoding="utf-8",
    )
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)
    matches = [p for p in problems if p.where == "de/01-test" and "gendered" in p.message]
    assert len(matches) == 1
    assert "Nutzer*innen" in matches[0].message


def test_lint_reports_gendered_language_in_a_question_option(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    question = content / "de" / "questions" / "q-01-02.yaml"
    question.write_text(
        question.read_text(encoding="utf-8").replace("Mitgliedstaat", "Mitarbeitende"),
        encoding="utf-8",
    )
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)
    matches = [p for p in problems if p.where == "de/q-01-02" and "gendered" in p.message]
    assert len(matches) == 1
    assert "Mitarbeitende" in matches[0].message


def test_lint_reports_gendered_language_in_a_persona_reaction(tmp_path: Path, library):
    personas = tmp_path / "personas"
    shutil.copytree(FIXTURES / "personas", personas)
    manifest = personas / "testbot" / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'cheat: "No."', 'cheat: "Frag lieber die Kolleginnen und Kollegen."'
        ),
        encoding="utf-8",
    )
    bundle = load_content(FIXTURES / "content", personas, law_dir=REPO_LAW)
    problems = lint(bundle, library)
    matches = [p for p in problems if p.where == "persona/testbot" and "gendered" in p.message]
    assert len(matches) == 1
    assert "Kolleginnen und Kollegen" in matches[0].message


def test_lint_reports_gendered_language_in_a_persona_verdict_line(tmp_path: Path, library):
    personas = tmp_path / "personas"
    shutil.copytree(FIXTURES / "personas", personas)
    manifest = personas / "testbot" / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'right: ["Stimmt."]', 'right: ["Stimmt, liebe Mitarbeitende."]'
        ),
        encoding="utf-8",
    )
    bundle = load_content(FIXTURES / "content", personas, law_dir=REPO_LAW)
    problems = lint(bundle, library)
    matches = [p for p in problems if p.where == "persona/testbot" and "gendered" in p.message]
    assert len(matches) == 1
    assert "Mitarbeitende" in matches[0].message


def test_lint_reports_gendered_language_in_a_persona_milestone_line(tmp_path: Path, library):
    personas = tmp_path / "personas"
    shutil.copytree(FIXTURES / "personas", personas)
    manifest = personas / "testbot" / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            '"Alles fertig."', '"Alles fertig, liebe Teilnehmende."'
        ),
        encoding="utf-8",
    )
    bundle = load_content(FIXTURES / "content", personas, law_dir=REPO_LAW)
    problems = lint(bundle, library)
    matches = [p for p in problems if p.where == "persona/testbot" and "gendered" in p.message]
    assert len(matches) == 1
    assert "Teilnehmende" in matches[0].message


def _lint_may(tmp_path: Path, library, may: str) -> list[str]:
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    chapter = content / "de" / "chapters" / "01-test.yaml"
    chapter.write_text(
        chapter.read_text(encoding="utf-8").replace(
            "Das weißt du jetzt: Betreiber sorgen für KI-Kompetenz (Art. 4 Abs. 1).", may
        ),
        encoding="utf-8",
    )
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    return [p.message for p in lint(bundle, library) if p.where == "de/01-test"]


def test_lint_checks_every_citation_of_a_may_line_against_the_library(tmp_path, library):
    messages = _lint_may(
        tmp_path,
        library,
        "Das darfst du: üben (Art. 4 Abs. 1). Und alles andere (Art. 999 Abs. 1).",
    )
    assert len(messages) == 1
    assert "999" in messages[0]


def test_lint_rejects_a_may_line_that_cites_nothing(tmp_path, library):
    assert _lint_may(tmp_path, library, "Das darfst du: alles.") == ["the may line cites nothing"]


def test_lint_reports_gendered_language_in_a_may_line(tmp_path, library):
    messages = _lint_may(
        tmp_path,
        library,
        "Das weißt du jetzt: Mitarbeitende brauchen KI-Kompetenz (Art. 4 Abs. 1).",
    )
    assert len(messages) == 1
    assert "gendered" in messages[0] and "Mitarbeitende" in messages[0]


def test_lint_reports_gendered_language_in_a_law_summary(tmp_path: Path, library):
    law = tmp_path / "law"
    shutil.copytree(REPO_LAW, law)
    path = law / "ai_act" / "_act.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["summary"] = "Das Gesetz gilt für Mitarbeitende in jedem Betrieb."
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    bundle = load_content(FIXTURES / "content", FIXTURES / "personas", law_dir=law)
    problems = lint(bundle, library)

    assert any("gendered" in p.message and "Mitarbeitende" in p.message for p in problems)


def test_a_stub_chapter_is_still_linted_for_citations(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    for locale in ("de", "en"):
        chapter = content / locale / "chapters" / "02-stub.yaml"
        chapter.write_text(
            chapter.read_text(encoding="utf-8").replace('"Art. 4(1)"', '"Art. 999"'),
            encoding="utf-8",
        )
    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)
    assert [(p.where, p.message) for p in problems] == [
        ("de/02-stub/s1", "'Art. 999' resolves to ai_act:art_999, which is not in the library"),
        ("en/02-stub/s1", "'Art. 999' resolves to ai_act:art_999, which is not in the library"),
    ]


def test_a_sentence_may_not_stand_twice_in_the_courses_prose(tmp_path: Path, library):
    """A sentence that stands twice is a teaching point the course teaches twice."""
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    taught = "KI-Kompetenz ist Pflicht für Anbieter und Betreiber."
    chapter = content / "de" / "chapters" / "01-test.yaml"
    chapter.write_text(
        chapter.read_text(encoding="utf-8").replace(
            f"    text: {taught}\n", f"    text: {taught}\n    example: {taught}\n"
        ),
        encoding="utf-8",
    )
    stub = content / "de" / "chapters" / "02-stub.yaml"
    stub.write_text(
        stub.read_text(encoding="utf-8").replace(
            "    text: Dieses Kapitel entsteht noch.", f"    text: {taught}"
        ),
        encoding="utf-8",
    )

    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)

    assert [(p.where, p.message) for p in problems] == [
        (
            "de/01-test/s1",
            f'example repeats a sentence that already stands in de/01-test/s1 text: "{taught}"',
        ),
        (
            "de/02-stub/s1",
            f'text repeats a sentence that already stands in de/01-test/s1 text: "{taught}"',
        ),
    ]


def test_a_step_text_may_not_grow_past_a_hundred_and_twenty_words(tmp_path: Path, library):
    content = tmp_path / "content"
    shutil.copytree(FIXTURES / "content", content)
    long_text = " ".join(f"Wort{n}" for n in range(1, 122)) + "."
    chapter = content / "de" / "chapters" / "01-test.yaml"
    chapter.write_text(
        chapter.read_text(encoding="utf-8").replace(
            "    text: KI-Kompetenz ist Pflicht für Anbieter und Betreiber.",
            f"    text: {long_text}",
        ),
        encoding="utf-8",
    )

    bundle = load_content(content, FIXTURES / "personas", law_dir=REPO_LAW)
    problems = lint(bundle, library)

    assert [(p.where, p.message) for p in problems] == [
        ("de/01-test/s1", "step text is 121 words, the limit is 120")
    ]


def test_lint_rejects_a_stem_that_asks_two_things_and_a_point_with_a_reason(tmp_path, library):
    problems = _lint_question(
        tmp_path,
        library,
        "rubric:\n  must:\n    - point: nennt, dass es gilt, weil das Haus es sagt\n"
        "      ask: Gilt es?\n",
        question="Gilt die Regel, und warum?",
    )
    messages = [p.message for p in problems]
    assert any("asks two things" in m for m in messages)
    assert any("point holds two facts" in m for m in messages)
