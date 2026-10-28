"""Walk the full course of the trainer end to end over the live API.

Logs in as a dev user, brings the session to the done phase by answering
every pooled question correctly (the answers come from the repo's own
question files), and asserts the done phase, the finale event and that a
resume reports done; the completion record itself is checked outside the
walk, straight against the store. Used to verify the compose dev profile
wiring with real models.

Usage: uv run --project backend python tools/demo_walk.py \
         --base-url http://localhost:8000 --subject anna \
         --questions content/de/questions
"""

import argparse
import json
import sys
from pathlib import Path

import httpx
import yaml

PERSONA = "clerk"
OVERLAP_MIN = 0.8

EXPECTED_CHAPTERS = 8


def check_pdf(client: httpx.Client, part: dict, label: str) -> None:
    response = client.get(part["url"])
    response.raise_for_status()
    assert response.headers["content-type"] == "application/pdf", part["url"]
    assert response.content.startswith(b"%PDF"), part["url"]
    out = Path(f"/tmp/m5-walk-{label}.pdf")
    out.write_bytes(response.content)
    print(f"pdf ok: {part['url']} -> {out}")


def load_questions(directory: Path) -> dict[str, dict]:
    questions = {}
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        questions[data["id"]] = data
    return questions


def correct_answer(question: dict) -> str:
    if question["type"] == "yes_no":
        return "Ja" if question["correct"] == "yes" else "Nein"
    if question["type"] == "multiple_choice":
        return question["correct"]
    return question["model_answer"]


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def match_question(message_text: str, hint: dict, questions: dict[str, dict]) -> dict | None:
    """Find the pool question the tutor is asking, or None.

    The graph embeds a question verbatim in its draft and the input hint
    carries a multiple-choice question's option texts verbatim, so both match
    exactly. A persona rewrite may reword the question, so fall back to token
    overlap.
    """
    message = _normalize(message_text)
    exact = [q for q in questions.values() if _normalize(q["question"]) in message]
    if len(exact) == 1:
        return exact[0]
    if hint.get("kind") == "choices":
        labels = {_normalize(choice["label"]) for choice in hint.get("choices", [])}
        by_options = [
            q
            for q in questions.values()
            if q["type"] == "multiple_choice"
            and {_normalize(option["text"]) for option in q["options"]} == labels
        ]
        if len(by_options) == 1:
            return by_options[0]
    words = set(message.split())
    best, best_score = None, 0.0
    for question in questions.values():
        tokens = {word for word in _normalize(question["question"]).split() if len(word) > 3}
        score = len(tokens & words) / len(tokens) if tokens else 0.0
        if score > best_score:
            best, best_score = question, score
    return best if best_score >= OVERLAP_MIN else None


def parse_sse(text: str) -> list[dict]:
    events = []
    for frame in text.split("\n\n"):
        for line in frame.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def take_opening(client: httpx.Client, session_id: int) -> list[dict]:
    with client.stream("POST", f"/api/chat/{session_id}/opening") as response:
        body = response.read()
        response.raise_for_status()
    return parse_sse(body.decode("utf-8"))


def take_turn(client: httpx.Client, session_id: int, reply: str) -> list[dict]:
    with client.stream("POST", f"/api/chat/{session_id}/turns", json={"text": reply}) as response:
        body = response.read()
        response.raise_for_status()
    return parse_sse(body.decode("utf-8"))


def decide(session: dict, questions: dict[str, dict], resend: str | None):
    """Pick the next student reply from the wire state alone.

    Returns the reply and whether it counts as an answer to a question, which
    is what the caller re-sends when a turn re-asks instead of grading.
    """
    hint = session["hint"]
    messages = session["messages"]
    last_text = messages[-1]["text"] if messages else ""
    matched = match_question(last_text, hint, questions)
    if matched is not None:
        return correct_answer(matched), True
    # A picked question asks its typed why (D127): the ask names the question.
    message = _normalize(last_text)
    asked = [
        q
        for q in questions.values()
        if q.get("rubric")
        and any(
            _normalize(point["ask"]) in message
            for point in q["rubric"]["must"][1:]
            if point.get("ask")
        )
    ]
    if len(asked) == 1:
        return asked[0]["model_answer"], True
    if resend is not None:
        return resend, True
    if hint["kind"] == "choices":
        return hint["choices"][0]["key"], True
    if hint["kind"] == "yes_no":
        return "Ja", True
    return "Weiter", False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--subject", default="anna")
    parser.add_argument("--questions", type=Path, default=Path("content/de/questions"))
    # The full course with retries and coaching runs past 80 turns; the budget is a
    # runaway guard, so it must sit well above the honest walk.
    parser.add_argument("--max-turns", type=int, default=140)
    args = parser.parse_args()

    questions = load_questions(args.questions)
    with httpx.Client(base_url=args.base_url, timeout=180.0) as client:
        login = client.post("/api/auth/dev/login", json={"subject": args.subject})
        login.raise_for_status()
        created = client.post("/api/session", json={"persona_id": PERSONA})
        created.raise_for_status()
        session = created.json()
        session_id = session["id"]
        print(f"session {session_id} persona {session['persona_id']} phase {session['phase']}")
        if not session["messages"]:
            take_opening(client, session_id)
            session = client.get("/api/session").json()

        resend, finale_seen = None, False
        events: list[dict] = []
        chapters_done = 0
        checked_pdf = False
        if session["phase"] == "done":
            print("session already in the done phase; nothing to walk")
            finale_seen = True
        for turn in range(args.max_turns):
            if session["phase"] == "done":
                break
            reply, is_answer = decide(session, questions, resend)
            events = take_turn(client, session_id, reply)
            errors = [e for e in events if e["event"] == "error"]
            if errors:
                print(f"FAILED: turn error {errors[0]}", file=sys.stderr)
                return 1
            message = next((e for e in reversed(events) if e["event"] == "message"), None)
            if message is None:
                print("FAILED: stream carried no message event", file=sys.stderr)
                return 1
            ui = [e["name"] for e in events if e["event"] == "ui"]
            stage = next(
                (e["payload"] for e in events if e["event"] == "ui" and e["name"] == "stage"),
                None,
            )
            if stage is None:
                print("FAILED: turn carried no stage event", file=sys.stderr)
                return 1
            if len(stage["chapters"]) != EXPECTED_CHAPTERS:
                print(
                    f"FAILED: stage lists {len(stage['chapters'])} chapters",
                    file=sys.stderr,
                )
                return 1
            persona = stage["persona"]
            if not persona or not str(persona.get("image_url", "")).startswith("/api/personas/"):
                print(f"FAILED: the stage carries no persona portrait: {persona}", file=sys.stderr)
                return 1
            file_parts = [p for p in message["parts"] if p["kind"] == "file"]
            if "chapter_complete" in ui:
                if not file_parts:
                    print("FAILED: chapter_complete without a file part", file=sys.stderr)
                    return 1
                if not any(p["kind"] == "chapter_done" for p in message["parts"]):
                    print("FAILED: chapter_complete without its divider", file=sys.stderr)
                    return 1
                chapters_done += 1
                if not checked_pdf:
                    check_pdf(client, file_parts[0], "chapter-sheet")
                    checked_pdf = True
            finale_seen = finale_seen or "finale" in ui
            if any(e["event"] == "ui" and e["name"] == "answer_result" for e in events):
                resend = None
            else:
                resend = reply if is_answer else None
            session = client.get("/api/session").json()
            print(f"turn {turn + 1}: {reply!r} -> {message['text'][:70]}... {ui}")

        if session["phase"] != "done" or not finale_seen:
            print(f"FAILED: phase {session['phase']}, finale seen {finale_seen}", file=sys.stderr)
            return 1
        if chapters_done != EXPECTED_CHAPTERS:
            print(
                f"FAILED: walked {chapters_done} chapter completions, want {EXPECTED_CHAPTERS}",
                file=sys.stderr,
            )
            return 1
        last = next(
            (e for e in reversed(events) if e["event"] == "message"),
            {"parts": []},
        )
        final_files = [p for p in last["parts"] if p["kind"] == "file"]
        if len(final_files) < 2:
            print(
                f"FAILED: finale carried {len(final_files)} file parts, "
                "want the sheet and the certificate",
                file=sys.stderr,
            )
            return 1
        check_pdf(client, final_files[-1], "certificate")
        resumed = client.get("/api/session").json()
        if resumed["phase"] != "done":
            print(f"FAILED: resume reports phase {resumed['phase']}", file=sys.stderr)
            return 1
        me = client.get("/api/me").json()
        print(
            f"done; resumed phase {resumed['phase']}; "
            f"me: subject={me['principal']['subject']} data_level={me['data_level']} "
            f"stored={me['stored']}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
