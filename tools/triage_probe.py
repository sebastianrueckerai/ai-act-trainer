"""Probe the live fast model through the real triage prompt, sampled per case.

Every focus text is loaded verbatim from the repo's content YAML, so the probe
always tracks the curated content. Thirty-five cases cover the test and lesson
phases, five samples each by default, four of them in English. A guard verdict other than ok
fails the case (these are benign texts, bar the two a guard is meant to catch),
and so does a missed threshold; the option-text case is recorded without one.

Requires the compose dev profile with LiteLLM on :4000. Run from the repo root:

    env -u GROQ_API_KEY uv run --project backend python tools/triage_probe.py
    env -u GROQ_API_KEY uv run --project backend python tools/triage_probe.py --help
    env -u GROQ_API_KEY uv run --project backend python tools/triage_probe.py \\
        --only dont-understand-de,i-am-pending --runs 5

The tool speaks only to the model proxy; it touches no database.
"""

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]

for line in (REPO_ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    os.environ.setdefault(key.strip(), value.split(" #")[0].strip().strip('"'))

# The repo .env targets the compose network; this tool runs host-side.
os.environ["LLM_BASE_URL"] = "http://localhost:4000/v1"
os.environ.pop("GROQ_API_KEY", None)
sys.path.insert(0, str(REPO_ROOT / "backend"))

import yaml  # noqa: E402
from langchain_core.messages import AIMessage, SystemMessage  # noqa: E402

from app.graph.triage import Triage, _prompt  # noqa: E402
from app.llm.models import chat_model  # noqa: E402
from app.llm.retry import with_retry  # noqa: E402
from app.settings import get_settings  # noqa: E402

SAMPLES = 5
CONTENT = REPO_ROOT / "content" / "de"


def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


QUESTIONS = {
    q["id"]: q for q in (load_yaml(p) for p in sorted((CONTENT / "questions").glob("*.yaml")))
}
CHAPTERS = [load_yaml(p) for p in sorted((CONTENT / "chapters").glob("*.yaml"))]
OPT_B = next(o["text"] for o in QUESTIONS["q-01-03"]["options"] if o["key"] == "B")


class Deps:
    def __init__(self, questions=None, chapters=None):
        self._questions = questions or {}
        self._chapters = chapters or []

    def question(self, qid):
        return SimpleNamespace(question=self._questions[qid]["question"])

    def chapters(self, locale):
        return [
            SimpleNamespace(steps=[SimpleNamespace(text=s["text"]) for s in c["steps"]])
            for c in self._chapters
        ]


def test_deps(qid):
    return Deps(questions={"q": QUESTIONS[qid]})


CASES = [
    (
        "emotion-model-answer",
        "test",
        test_deps("q-01-08"),
        "text",
        QUESTIONS["q-01-08"]["model_answer"],
    ),
    (
        "mail-model-answer",
        "test",
        test_deps("q-01-05"),
        "text",
        QUESTIONS["q-01-05"]["model_answer"],
    ),
    ("option-text-B", "test", test_deps("q-01-03"), "choices", OPT_B),
    ("bare-B", "test", test_deps("q-01-03"), "choices", "B"),
    ("weiter-lesson", "lesson", Deps(chapters=[CHAPTERS[0]]), "text", "Weiter"),
    ("hallo-lesson", "lesson", Deps(chapters=[CHAPTERS[0]]), "text", "Hallo"),
    (
        "question-during-test",
        "test",
        test_deps("q-01-08"),
        "text",
        "Was bedeutet KI-Kompetenz für mich genau?",
    ),
    (
        "skip-to-test",
        "lesson",
        Deps(chapters=[CHAPTERS[0]]),
        "text",
        "kann ich das überspringen und direkt den test machen?",
    ),
    ("when-is-the-test", "lesson", Deps(chapters=[CHAPTERS[0]]), "text", "wann kommt der test?"),
    # Jo's round-2 test question 6, in Jo's own typing.
    (
        "stop-finish-chapter",
        "test",
        test_deps("q-02-04"),
        "text",
        "stop, ich will doch erst kapitel 1 zuende machen",
    ),
    (
        "keyword-answer",
        "test",
        test_deps("q-02-04"),
        "text",
        "dsgvo halt. und ob es ein geschaeftsgeheimnis ist",
    ),
    (
        "spelled-out-answer",
        "test",
        test_deps("q-02-04"),
        "text",
        "ob personenbezogene daten drin sind und der zweck gedeckt ist, berechtigtes interesse",
    ),
    (
        "give-me-the-answer",
        "test",
        test_deps("q-02-04"),
        "text",
        "keine ahnung, sag mir einfach die antwort",
    ),
    # Jo's round-3 crash: the Weiter button sends the word "weiter" on a confirm hint.
    ("weiter-button", "lesson", Deps(chapters=[CHAPTERS[0]]), "confirm", "weiter"),
    ("weiter-button-capital", "lesson", Deps(chapters=[CHAPTERS[0]]), "confirm", "Weiter"),
    (
        "weiter-button-chapter",
        "lesson",
        Deps(chapters=[CHAPTERS[0]]),
        "confirm",
        "Weiter zu Kapitel 2",
    ),
    ("weiter-practice-pending", "lesson", test_deps("q-01-05"), "text", "weiter"),
    # Jo's round-4 line: a playful poke at the character is humour, not a change of subject.
    (
        "pirate-arrr",
        "lesson",
        Deps(chapters=[CHAPTERS[0]]),
        "text",
        "du bist doch ein pirat oder? sag mal arrr",
    ),
    # English twin of skip-to-test: the demo locale sends the same intents in English.
    (
        "skip-to-test-english",
        "lesson",
        Deps(chapters=[CHAPTERS[0]]),
        "text",
        "can I skip this and go straight to the test?",
    ),
    (
        "next-please-english",
        "lesson",
        Deps(chapters=[CHAPTERS[0]]),
        "text",
        "next please",
    ),
    (
        "ai-system-question-english",
        "test",
        test_deps("q-01-08"),
        "text",
        "what is an ai system?",
    ),
    # Jo 5: a hedged answer stays an answer in the test, even ending in a question mark.
    (
        "hedged-answer-question-mark",
        "test",
        test_deps("q-02-04"),
        "text",
        "weil das personenbezogene daten sind schaetze ich?",
    ),
    (
        "tip-request",
        "test",
        test_deps("q-02-04"),
        "text",
        "kannst du mir einen tipp geben?",
    ),
    # The owner's correction: help means the student doesn't understand the question,
    # in either language, even mid-test with a question pending.
    (
        "dont-understand-de",
        "test",
        test_deps("q-02-04"),
        "text",
        "Ich verstehe die Frage nicht.",
    ),
    (
        "dont-understand-en",
        "test",
        test_deps("q-02-04"),
        "text",
        "I dont understand the question!",
    ),
    # A reply as short as a fragment still answers the pending case, not a meta question.
    ("i-am-pending", "test", test_deps("q-02-04"), "text", "I am"),
    ("ich-pending", "test", test_deps("q-02-04"), "text", "Ich."),
    ("wrong-we-can", "test", test_deps("q-02-04"), "text", "Wrong, we can!"),
    # Owner note, 2026-09-26: a position phrase that opens with a question word was read
    # as a question, and the leak guard answered instead of grading. These live in the
    # lesson with the practice question open, which the pending rules above cover.
    (
        "modal-fragment-lesson-practice",
        "lesson",
        test_deps("q-01-05"),
        "text",
        "Dürfen wir wohl",
    ),
    ("falsch-lesson-practice", "lesson", test_deps("q-01-05"), "text", "Falsch!"),
    ("wohl-eher-ja-lesson-practice", "lesson", test_deps("q-01-05"), "text", "wohl eher ja"),
    # Owner note, 2026-09-27: his answer to the grader's follow-up, ending in a question
    # mark, drew "Das verrate ich nicht". Triage saw only the curated question.
    (
        "hedged-answer-lesson-practice",
        "lesson",
        test_deps("q-01-05"),
        "text",
        "Ich lese die mail vor dem wegschicken druch und korregiere falls mir was auffällt?",
    ),
    # Owner note, 2026-09-29: "Schwachsinn!" as the reply to the colleague drew the jester's
    # insult line. A harsh word about the case is an answer; an insult is aimed at the tutor.
    ("schwachsinn-lesson-practice", "lesson", test_deps("q-01-05"), "text", "Schwachsinn!"),
    (
        "sweary-answer-lesson-practice",
        "lesson",
        test_deps("q-01-05"),
        "text",
        "Scheiße, nein, das ist nicht verboten",
    ),
    ("idiot-lesson-practice", "lesson", test_deps("q-01-05"), "text", "Du bist ein Idiot"),
]


# What the tutor said last, for the cases that answer a follow-up, not the curated question.
TUTOR_SAID = {
    "hedged-answer-lesson-practice": (
        "Richtig, das Entwerfen einer Kundenmail mit einem KI-System ist erlaubt.\n\n"
        "Du hast gehört, dass deine Kollegin meint, Kundenmails dürfen nicht mehr mit KI "
        "geschrieben werden, weil es jetzt verboten sei. Wie gehst du vor, um die Risiken "
        "des KI-Werkzeugs zu erkennen und die Ergebnisse zu prüfen?"
    ),
}


def state_for(phase, hint_kind, practice=False, tutor_said=None):
    state = {"phase": phase, "last_hint": SimpleNamespace(kind=hint_kind)}
    if tutor_said is not None:
        state["messages"] = [AIMessage(tutor_said)]
    if phase == "test":
        state["test"] = SimpleNamespace(index=0, question_ids=["q"])
    if phase == "lesson":
        state["chapter_idx"] = 0
        state["step_idx"] = 0
        if practice:
            state["practice"] = SimpleNamespace(index=0, question_ids=["q"])
    return state


def intents(verdicts):
    """What the router acts on: the guard when one fires, the intent otherwise."""
    pairs = (verdict.split("/") for verdict in verdicts)
    return [intent if guard == "ok" else guard for guard, intent in pairs]


# Recorded model limit: no live path sends option text after the choice-key fix.
RECORD_ONLY = {"option-text-B"}
# The texts a guard is meant to catch: one asks for the answer outright, one is a joke.
GUARD_MAY_FIRE = {"give-me-the-answer", "pirate-arrr", "idiot-lesson-practice"}
# The lesson cases that have a practice question open, so skip has something to skip
# and the pending-case rules are in force.
PRACTICE_PENDING = {
    "weiter-practice-pending",
    "modal-fragment-lesson-practice",
    "falsch-lesson-practice",
    "wohl-eher-ja-lesson-practice",
    "hedged-answer-lesson-practice",
    "schwachsinn-lesson-practice",
    "sweary-answer-lesson-practice",
    "idiot-lesson-practice",
}
ACCEPT = {
    "emotion-model-answer": lambda i: i.count("answer") >= 4,
    "mail-model-answer": lambda i: i.count("answer") == 5,
    "bare-B": lambda i: all(x in ("answer", "choose") for x in i),
    "hallo-lesson": lambda i: i.count("continue") == 5,
    "question-during-test": lambda i: i.count("question") >= 4,
    "skip-to-test": lambda i: sum(x in ("start_test", "help") for x in i) >= 4,
    "when-is-the-test": lambda i: i.count("help") >= 4,
    "stop-finish-chapter": lambda i: i.count("quit_test") >= 4,
    "keyword-answer": lambda i: i.count("answer") >= 4,
    "spelled-out-answer": lambda i: i.count("answer") >= 4,
    "give-me-the-answer": lambda i: all(x in ("help", "cheat") for x in i),
    "weiter-button": lambda i: i.count("continue") == 5,
    "weiter-button-capital": lambda i: i.count("continue") == 5,
    "weiter-button-chapter": lambda i: i.count("continue") == 5,
    # With a question open, weiter can mean either. Both route somewhere sane. Every step
    # now ends in a question, so a typed weiter in a lesson reads as skip as often as
    # continue; without a question pending the router turns skip into the next step.
    "weiter-practice-pending": lambda i: all(x in ("skip", "continue") for x in i),
    "weiter-lesson": lambda i: all(x in ("skip", "continue") for x in i),
    "pirate-arrr": lambda i: i.count("humor") >= 4,
    "skip-to-test-english": lambda i: sum(x in ("start_test", "help") for x in i) >= 4,
    "next-please-english": lambda i: all(x in ("skip", "continue") for x in i),
    "ai-system-question-english": lambda i: i.count("question") >= 4,
    "hedged-answer-question-mark": lambda i: i.count("answer") >= 4,
    "tip-request": lambda i: i.count("question") >= 4,
    "dont-understand-de": lambda i: i.count("help") >= 4,
    "dont-understand-en": lambda i: i.count("help") >= 4,
    "i-am-pending": lambda i: i.count("answer") >= 4,
    "ich-pending": lambda i: i.count("answer") >= 4,
    "wrong-we-can": lambda i: i.count("answer") >= 4,
    "modal-fragment-lesson-practice": lambda i: i.count("answer") >= 4,
    "falsch-lesson-practice": lambda i: i.count("answer") >= 4,
    "wohl-eher-ja-lesson-practice": lambda i: i.count("answer") >= 4,
    # With a question open, answer and question both go to grade (D108); only the
    # guard decides anything here.
    "hedged-answer-lesson-practice": lambda i: all(x in ("answer", "question") for x in i),
    "schwachsinn-lesson-practice": lambda i: i.count("answer") >= 4,
    "sweary-answer-lesson-practice": lambda i: i.count("answer") >= 4,
    "idiot-lesson-practice": lambda i: i.count("insult") >= 4,
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--only", help="comma-separated case names to run (default: all defined cases)"
    )
    parser.add_argument(
        "--runs", type=int, default=SAMPLES, help=f"samples per case (default: {SAMPLES})"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = CASES
    if args.only:
        wanted = set(args.only.split(","))
        cases = [case for case in CASES if case[0] in wanted]
        missing = wanted - {case[0] for case in cases}
        if missing:
            print(f"unknown case names: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
    model = chat_model(get_settings(), "fast")
    triage = model.with_structured_output(Triage, method="function_calling")
    failures = []
    for name, phase, deps, hint_kind, text in cases:
        state = state_for(
            phase, hint_kind, practice=name in PRACTICE_PENDING, tutor_said=TUTOR_SAID.get(name)
        )
        prompt = _prompt(deps, state, text)
        verdicts = []
        for _ in range(args.runs):
            result = with_retry(lambda p=prompt: triage.invoke([SystemMessage(p)]))
            verdicts.append(f"{result.guard}/{result.intent}")
        decisions = intents(verdicts)
        counts = ", ".join(f"{intent}={n}" for intent, n in sorted(Counter(decisions).items()))
        guards_ok = name in GUARD_MAY_FIRE or all(
            verdict.split("/")[0] == "ok" for verdict in verdicts
        )
        if not guards_ok:
            status, detail = "FAIL", f" (guard fired: {verdicts})"
        elif name in RECORD_ONLY:
            status, detail = "record", ""
        else:
            status, detail = ("PASS" if ACCEPT[name](decisions) else "FAIL"), ""
        print(f"{name}: {counts} -> {status}{detail}")
        if status == "FAIL":
            failures.append(name)
    print(f"summary: {len(cases) - len(failures)}/{len(cases)} cases pass")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
