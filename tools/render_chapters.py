"""Render the whole German course on one page, to read it without the app.

Every chapter with its intro, every step as a bubble with its paragraphs, its example, its
citations and the question that follows it, and under each question the model answer card.
Run from the repo root:

    uv run --project backend python tools/render_chapters.py

Writes runs/rendered-chapters/index.html (gitignored). Plain HTML, no images, no external assets.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.content.citations import de_ref  # noqa: E402
from app.content.loader import load_content  # noqa: E402
from app.content.models import Chapter, Question  # noqa: E402

OUT = REPO_ROOT / "runs" / "rendered-chapters" / "index.html"
LOCALE = "de"

STYLE = """
  body { margin: 0; background: #0a121f; color: #d0d8e5;
         font: 17px/1.55 system-ui, "Segoe UI", sans-serif; }
  main { max-width: 900px; margin: 0 auto; padding: 40px 24px 80px; }
  h1 { font-size: 28px; margin: 0 0 8px; }
  h2 { font-size: 22px; margin: 48px 0 4px; color: #fbc031; }
  p { margin: 0 0 12px; }
  .lead { color: #8fa3c0; margin: 0 0 20px; }
  .meta { color: #8fa3c0; font-size: 14px; margin: 0 0 24px; }
  .step { border: 1px solid #283d62; border-radius: 10px; padding: 16px 20px; margin: 0 0 12px;
          background: #101c30; }
  .step-id { color: #8fa3c0; font-size: 13px; letter-spacing: .08em; text-transform: uppercase;
             margin: 0 0 10px; }
  .example { color: #8fa3c0; font-style: italic; margin: 12px 0 0; }
  .cites { color: #39bffb; font-size: 14px; margin: 10px 0 0; }
  .ask { margin: 16px 0 0; border-top: 1px solid #283d62; padding-top: 14px; }
  .ask-lead { color: #fbc031; font-size: 14px; margin: 0 0 8px; }
  .options { list-style: none; padding: 0; margin: 10px 0 0; }
  .options li { border: 1px solid #283d62; border-radius: 8px; padding: 8px 12px;
                margin: 0 0 6px; }
  .answer-kind { color: #8fa3c0; font-size: 14px; margin: 10px 0 0; }
  .card { border: 1px solid #3a5a8c; border-left: 4px solid #fbc031; border-radius: 10px;
          padding: 14px 18px; margin: 10px 0 28px 24px; background: #0d1626; }
  .card-title { color: #fbc031; font-size: 13px; letter-spacing: .08em;
                text-transform: uppercase; margin: 0 0 8px; }
  .summary { border: 1px solid #283d62; border-radius: 10px; padding: 16px 20px;
             margin: 8px 0 0; background: #0d1626; }
  a { color: #39bffb; }
""".strip()


def _paragraphs(text: str) -> list[str]:
    return [line.strip() for line in text.split("\n") if line.strip()]


def _cites(refs: list[str]) -> str:
    return " · ".join(de_ref(ref) for ref in refs)


def _answer_block(question: Question) -> list[str]:
    if question.type == "multiple_choice":
        items = "".join(
            f"<li><b>{html.escape(o.key)}</b> {html.escape(o.text)}</li>" for o in question.options
        )
        return [f'<ul class="options">{items}</ul>']
    if question.type == "yes_no":
        return ['<p class="answer-kind">Ja / Nein</p>']
    return ['<p class="answer-kind">Freitext</p>']


def _question_html(question: Question) -> str:
    parts = [
        '<div class="ask">',
        f"<p>{html.escape(question.question)}</p>",
        *_answer_block(question),
        "</div>",
        '<div class="card">',
        f'<p class="card-title">Musterlösung · {html.escape(question.id)}</p>',
        f"<p>{html.escape(question.model_answer)}</p>",
        f"<p>{html.escape(question.explanation)}</p>",
        f'<p class="cites">{html.escape(_cites(question.citations))}</p>',
        "</div>",
    ]
    return "\n".join(parts)


def _chapter_html(chapter: Chapter, questions: dict[str, Question]) -> str:
    parts = [
        f"<h2>{html.escape(chapter.title)}</h2>",
        f'<p class="lead">{html.escape(chapter.intro)}</p>',
        f'<p class="meta">{len(chapter.steps)} Schritte · '
        f"{chapter.duration_minutes} Minuten · {html.escape(chapter.id)}</p>",
    ]
    for step in chapter.steps:
        block = [
            '<div class="step">',
            f'<p class="step-id">{html.escape(step.id)}</p>',
            *(f"<p>{html.escape(p)}</p>" for p in _paragraphs(step.text)),
        ]
        if step.example:
            block.append(f'<p class="example">{html.escape(step.example)}</p>')
        if step.citations:
            block.append(f'<p class="cites">{html.escape(_cites(step.citations))}</p>')
        if step.question:
            block.append(_question_html(questions[step.question]))
        block.append("</div>")
        parts.append("\n".join(block))
    parts.append(
        '<div class="summary"><p class="step-id">Spickzettel</p>'
        f"<p>{html.escape(chapter.summary)}</p></div>"
    )
    return "\n".join(parts)


def main() -> int:
    bundle = load_content(REPO_ROOT / "content", REPO_ROOT / "personas")
    content = bundle.locales[LOCALE]
    chapters = [content.chapters[cid] for cid in sorted(content.chapters)]
    steps = sum(len(chapter.steps) for chapter in chapters)
    minutes = sum(chapter.duration_minutes for chapter in chapters)
    body = "\n".join(_chapter_html(chapter, content.questions) for chapter in chapters)
    page = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Die acht Kapitel zum Lesen</title>
<style>
{STYLE}
</style>
</head>
<body>
<main>
  <h1>Die acht Kapitel zum Lesen</h1>
  <p class="lead">Der ganze Kurs auf einer Seite, in der Form, die D76 beschreibt: ein
  Schritt lehrt einen Begriff, dann fragt er nach einem Nachbarfall, den der Begriff
  entscheidet. Unter jeder Frage steht die Musterlösung, die der Kurs nach der Antwort
  zeigt.</p>
  <p class="meta">{len(chapters)} Kapitel · {steps} Schritte · {minutes} Minuten ·
  erzeugt von tools/render_chapters.py</p>
{body}
</main>
</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}: {len(chapters)} chapters, {steps} steps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
