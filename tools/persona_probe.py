"""Probe the live persona model through the real voice pipeline, one rewrite per lesson step.

Chapter one's six steps and chapter two's five, in course order, are what Jo reads, followed
by one verdict turn (a right answer and the next step, mood happy) and one short follow-up
(mood neutral). Each draft goes through `voice_rewrite` and `critique_voice`, the functions
the graph node calls, with the conversation carried from turn to turn in the brief, and
through `plain_text`, so what prints is what the bubble shows. Each row reports whether the
critic shipped the rewrite and which faults it named, and which words of another persona's
vocabulary crept in. A foreign word fails the run.

Requires the compose dev profile with LiteLLM on :4000. Run from the repo root:

    env -u GROQ_API_KEY uv run --project backend python tools/persona_probe.py --persona pirate

The tool speaks only to the model proxy; it touches no database.
"""

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

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

from app.content.loader import load_content  # noqa: E402
from app.corpus.build import load_library  # noqa: E402
from app.corpus.search import SearchIndex  # noqa: E402
from app.graph.brief import Brief  # noqa: E402
from app.graph.critic import critique_voice  # noqa: E402
from app.graph.deps import GraphDeps  # noqa: E402
from app.graph.persona import plain_text, voice_rewrite  # noqa: E402
from app.graph.state import Mood, initial_state  # noqa: E402
from app.graph.teach import _step_material  # noqa: E402
from app.llm.models import chat_model  # noqa: E402
from app.settings import get_settings  # noqa: E402

_WORD = re.compile(r"[a-zäöüß-]{6,}")
# German function words of five letters or more: they carry no persona's voice.
STOPWORDS = frozenset(
    """
    alles anderen anderes andere bevor bitte bleibe bleiben bleibt dabei dafür dagegen daher
    damit danach daran darauf darum davon dazu deine deinem deinen deiner deines deren deshalb
    dessen diese diesem diesen dieser dieses durch einem einen einer eines einfach einmal
    etwas eurem euren eurer eures gegen genau gerade haben hatte hätte heute ihnen ihrem ihren
    ihrer ihres indem jedem jeden jeder jedes jemand jetzt kannst keine keinem keinen keiner
    keines kommen kommt können könnte lassen lässt machen machst macht manche meine meinem
    meinen meiner müssen musst nicht nichts niemand schon seine seinem seinen seiner seines
    selbst sobald solange sollen sollst sollte sondern sonst sowie trotzdem unser unsere
    unserem unseren unserer unter viele vielleicht warum welche welchem welchen welcher
    welches wenig weniger werden weshalb wieder wieso wirklich wirst wollen wollte worden
    wurde würde zuerst zwischen
    """.split()  # noqa: SIM905
)


def _foreign_lexicon(settings, persona_id: str, content_text: str) -> set[str]:
    """The distinctive words of every OTHER persona's curated files: a rewrite that uses one
    borrowed another persona's voice (the jester that called the student Landratte). Flavour
    is nouns and calls (Landratte, Schellen, Zack), so only a word that is always capitalised
    in its files counts; a word the course content or the locale file carries is the
    content's, and a function word carries no voice."""
    content_words = set(_WORD.findall(content_text.lower()))
    counts: dict[str, dict[str, int]] = {}
    lowercased: dict[str, set[str]] = {}
    for manifest_path in sorted(settings.personas_dir.glob("*/manifest.yaml")):
        pid = manifest_path.parent.name
        text = manifest_path.read_text(encoding="utf-8")
        prompt_file = manifest_path.parent / "prompts" / "de.md"
        if prompt_file.is_file():
            text += "\n" + prompt_file.read_text(encoding="utf-8")
        cased = re.findall(r"[A-Za-zÄÖÜäöüß-]{6,}", text)
        words = [word.lower() for word in cased]
        counts[pid] = {word: words.count(word) for word in set(words)}
        lowercased[pid] = {word for word in cased if word[0].islower()}
    lexicon: set[str] = set()
    for pid, words in counts.items():
        if pid == persona_id:
            continue
        lexicon |= {
            word
            for word, n in words.items()
            if n >= 2
            and word not in lowercased[pid]
            and word not in STOPWORDS
            and word not in content_words
            and word not in counts[persona_id]
        }
    return lexicon


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", required=True)
    args = parser.parse_args()

    settings = get_settings()
    library = load_library(settings.corpus_dir)
    deps = GraphDeps(
        library=library,
        content=load_content(settings.content_dir, settings.personas_dir),
        search=SearchIndex.build(library),
        models={"strong": chat_model(settings, "strong"), "fast": chat_model(settings, "fast")},
        settings=settings,
        law_version="probe",
    )
    persona = deps.persona(args.persona)
    if persona is None:
        parser.error(f"no such persona: {args.persona}")
    model = deps.models[deps.settings.persona_model_role]

    state = initial_state(args.persona)
    locale = state["locale"]
    chapters = deps.chapters(locale)
    questions = deps.locale_content(locale).questions
    content_text = " ".join(
        [step.text + " " + (step.example or "") for c in chapters for step in c.steps]
        + [
            q.question
            + " "
            + q.model_answer
            + " "
            + q.explanation
            + " ".join(option.text for option in q.options)
            for q in questions.values()
        ]
        + [
            str(value)
            for value in yaml.safe_load(
                (REPO_ROOT / "backend" / "app" / "i18n" / "de.yaml").read_text(encoding="utf-8")
            ).values()
        ]
    )
    foreign_lexicon = _foreign_lexicon(settings, args.persona, content_text)

    turns: list[tuple[str, str, Mood]] = []
    for chapter_idx, key in ((0, "c1"), (1, "c2")):
        for step_idx in range(len(chapters[chapter_idx].steps)):
            draft, _ = _step_material(deps, chapters[chapter_idx], step_idx)
            turns.append((f"{key}s{step_idx + 1}", draft, Mood.neutral))
    # A right answer's verdict, and the next step in the same turn (D89).
    first_case = questions[chapters[0].steps[0].question]
    verdict = f"Genau. {first_case.explanation.split('. ')[0].rstrip('.')}."
    turns.append(("verdict", f"{verdict}\n\n{turns[1][1]}", Mood.happy))
    # A partial answer's reply: the confirmation and the question towards the rest.
    turns.append(
        (
            "followup",
            "Richtig, das darfst du.\n\nAber wer liest den Entwurf, bevor er rausgeht?",
            Mood.neutral,
        )
    )

    rows = []
    recent: list[str] = []
    for label, draft, mood in turns:
        outcome = "right" if mood is Mood.happy else "partial"
        brief = Brief.from_text(
            "Tutor:\nThe tutor of a German course on the EU AI Act. Phase: lesson.\n\n"
            f"Conversation:\n{chr(10).join(recent) or 'none'}\n\nJob:\nOutcome: {outcome}."
        )
        rewrite = voice_rewrite(model, persona, locale, mood, brief.text(), draft)
        critique = critique_voice(deps, brief, draft, rewrite)
        shown = plain_text(rewrite if critique.verdict == "ship" else draft)
        recent = (recent + [f"Tutor: {shown}"])[-6:]
        draft_tokens = set(_WORD.findall(draft.lower()))
        foreign = sorted(
            token
            for token in set(_WORD.findall(shown.lower()))
            if token in foreign_lexicon and token not in draft_tokens
        )
        rows.append(
            {
                "label": label,
                "survived": critique.verdict == "ship",
                "reason": ", ".join(critique.faults) or "-",
                "calls": 2,
                "foreign": foreign,
            }
        )
        print(f"--- {label} draft ---\n{draft}\n--- {label} shown ---\n{shown}\n")
        if critique.verdict != "ship":
            print(f"--- {label} REJECTED ({critique.notes}) ---\n{rewrite}\n")
        if foreign:
            print(f"--- {label} FOREIGN FLAVOUR: {', '.join(foreign)}")

    for row in rows:
        print(
            f"{row['label']}: survived={row['survived']} reason={row['reason']} "
            f"calls={row['calls']}"
        )

    total = len(rows)
    survived = sum(row["survived"] for row in rows)
    foreign_rows = sum(bool(row["foreign"]) for row in rows)
    print(
        f"summary: survival {survived / total:.0%} ({survived}/{total}), "
        f"model calls {sum(r['calls'] for r in rows)}, "
        f"foreign flavour {foreign_rows}/{total}"
    )
    return 1 if foreign_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
