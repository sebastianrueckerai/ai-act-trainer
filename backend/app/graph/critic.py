import time
from typing import Literal

import structlog
from pydantic import BaseModel, Field

from app.graph.brief import OPEN_KINDS, Brief
from app.graph.deps import GraphDeps
from app.graph.grade import call_structured, content_fields
from app.graph.prompts import CRITIC, VOICE_CRITIC, mark

log = structlog.get_logger(__name__)

ReplyFault = Literal["verdict", "leak", "unhelpful", "repeat", "question"]
VoiceFault = Literal["meaning", "question", "lost"]


class Critique(BaseModel):
    """What the critic makes of a draft: ship it, or send it back with notes."""

    verdict: Literal["ship", "retry"]
    faults: list[ReplyFault | VoiceFault] = Field(default_factory=list)
    notes: str = ""
    score: int = Field(ge=1, le=5)
    # The numbers of the Missing points the draft would earn pasted back as the answer:
    # the paste-back test done point by point. Any number that exists is a leak.
    credited: list[int] = Field(default_factory=list)
    # The checker's own version of the draft with every named fault fixed, a suggestion
    # for the writer or, on the critic path, the next draft itself. Empty on a ship.
    revision: str = ""


# Each critic gets a schema that admits only its own faults, so a reply critic cannot
# answer with a voice fault and the other way round.
class ReplyCritique(Critique):
    faults: list[ReplyFault] = Field(default_factory=list)


class VoiceCritique(Critique):
    faults: list[VoiceFault] = Field(default_factory=list)


LEAK_CHECK = (
    "- leak: do the paste-back test literally, point by point. For each point listed under "
    "Missing, take the draft's own sentences, the Ask now line left out, since it is "
    "course text, as if the student had typed them into the answer box: would the grader "
    "credit that point? A question that carries the point's content ('Wie sorgst du "
    "dafür, dass du das Ergebnis prüfst?', "
    "'Die Verordnung ist nur die Untergrenze, oder?') earns it: the student only has to "
    "say yes. A missing point stated as a fact earns it. A question that only points at "
    "the area or at a step ('Und die Kollegen?', 'Was tust du mit dem Entwurf, bevor er "
    "rausgeht?') earns nothing: pasted back, the grader reads a question, not the point. "
    "Leading towards a point is the tutor's job, not a leak. Write the number of every "
    "Missing point the draft earns into credited, only Missing points, never a met one, "
    "and name leak, whatever else is wrong. The replies on the open point, which the "
    "Verdict section counts, set the bar: on the first and second reply the concept may "
    "not be named at all; from the third reply on it may be named in a help sentence, the "
    "point itself still withheld; a point stated as a fact is credited, the concept's name "
    "alone is not.\n"
)


REPLY_CHECKS = (
    "The Message section above is what the student just wrote. The draft is the tutor's "
    "reply to it. Find what is wrong with the reply before the student sees it. Judge only "
    "what changes what the student gets. Check, in this order:\n"
    "- repeat: read the last Tutor line under Conversation and compare it with the draft "
    "sentence by sentence, the Ask now line left out: the ask itself repeats by design "
    "after a miss and is never a repeat. The same help sentences again, whatever the "
    "student wrote in between, is repeat. A new sentence that takes up what the student "
    "just said is not a repeat.\n"
    "- verdict: the opening must not contradict the verdict. No 'Richtig' or 'Genau' when "
    "nothing is met. No 'Noch nicht ganz', 'Nicht ganz' or 'Nein' as a verdict when "
    "something is met. No verdict at all when the message was not an attempt. "
    "When the outcome is on_track the try met nothing yet but is on the right track: no "
    "'Richtig' as if a point were met, no 'Falsch' or 'Nein' as if it were wrong; 'Du bist "
    "auf dem richtigen Weg' is the register. A sentence the student can read as a verdict "
    "on their own answer is one, whatever it means: "
    "'Das ist nicht richtig.' or 'Du hast recht, das ist nicht korrekt.' after a student "
    "who rejected someone's claim reads as 'your answer is wrong'. The opening "
    "need not restate the met point: a kind opener that contradicts nothing is fine.\n"
    "- unhelpful: the draft moves the student nowhere. It adds nothing before the Ask now "
    "line: no reaction to what the student said, no help on a practice miss, or it ignores "
    "a question the student asked. The Ask now line alone after a green try is fine; the "
    "page shows the verdict. A graded-test retry gives the count and no help; that is not "
    "unhelpful. A short opener that takes the student's last words up ('Kein "
    "Problem', 'Stimmt') is a reaction. Not restating the met point is not unhelpful. From "
    "the third reply on, naming the concept in a help sentence is help, not a fault.\n"
    "- question, while the question is open (the outcomes partial, wrong, on_track, "
    "not_an_attempt, test_retry): the draft ends on the Question section's Ask now line, "
    "word for word, and no second question stands beside it.\n"
    "- question, when the outcome is right or settled: the question is closed, there is "
    "no Ask now line to carry, and the draft asks no question at all. A follow-up "
    "question of the tutor's own has nothing to wait for.\n"
    "Wording, paragraph count and the address are not your job: the writer's own rules and "
    "the app's cleanup cover them. A reply without the word du in it is fine. Never name "
    "style as a fault of a reply.\n"
    "verdict is ship when none of the checks is wrong, else retry. faults lists what is "
    "wrong. credited lists the numbers of the Missing points the draft earns, empty when "
    "none. notes first name what to keep, then what to change, in two or three German "
    "sentences; never the rubric's words. revision is your own version of the draft with "
    "every named fault fixed, in the tutor's voice and obeying the STYLE section of the "
    "situation; on a ship verdict it is empty. score is 1 to 5 for how well the reply "
    "serves the student as it stands."
)

# The answer-giving check protects an open question. A reply that settles or confirms one
# states the answer, and a free question has no rubric to hand over, so the check does not
# run there (D123).
REPLY_CHECKLIST = LEAK_CHECK + REPLY_CHECKS


REPLY_EXAMPLES = (
    "Examples, from a case that is not in this course: a colleague wants the assistant to "
    "sort the team's holiday requests (Urlaubsanträge), and the question asks who decides "
    "and what has to be in place. The points: the manager decides, not the assistant; the "
    "people concerned are told a system was used. The student wrote 'Der Chef entscheidet', "
    "so the first point is met, the second is missing, try 1 of 5. The case's Ask now line "
    "is: 'Und die Kollegen, deren Anträge da durchlaufen: was steht ihnen zu?'\n"
    "- ship: 'Richtig, die Entscheidung bleibt beim Chef. Und die Kollegen, deren Anträge "
    "da durchlaufen: was steht ihnen zu?' It confirms the met point, ends on the ask word "
    "for word and names nothing the student has not said.\n"
    "- ship, one paragraph, no du in it: 'Stimmt, der Chef entscheidet. Und die Kollegen, "
    "deren Anträge da durchlaufen: was steht ihnen zu?' Short and plain, nothing to fault.\n"
    "- ship, no confirmation at all: 'Und die Kollegen, deren Anträge da durchlaufen: was "
    "steht ihnen zu?' The page shows the verdict; the reply need not restate the met point.\n"
    "- ship, fourth reply, the concept named: 'Kein Problem. Die Verordnung nennt das Transparenz. "
    "Und die Kollegen, deren Anträge da durchlaufen: was steht ihnen zu?' From the third reply "
    "on the concept may be named in a statement; pasted back, this earns nothing, the answer is "
    "still the student's.\n"
    "- ship, the outcome right, no question: 'Genau, der Chef entscheidet, und das Team erfährt "
    "vom Werkzeug.' Both points are met, the question is settled, and the reply confirms and "
    "stops. No ask is missing: on a settled outcome there is none to give.\n"
    "- retry, question, the outcome right: 'Stimmt, beim Chef bleibt die Entscheidung, und das "
    "Team erfährt vom Werkzeug. Wie hättest du es dem Team gesagt?' The question is settled. "
    "The tutor's question of its own reopens a closed case: drop it.\n"
    "- retry, leak: 'Richtig. Die Kollegen müssen erfahren, dass ein System mitgewirkt hat. "
    "Und die Kollegen, deren Anträge da durchlaufen: was steht ihnen zu?' The help sentence "
    "states the missing point; pasted back, it earns the second point. Notes: the sentence "
    "before the ask hands the missing point over; help without saying it.\n"
    "- retry, question and leak: 'Richtig. Wie sorgst du dafür, dass die Kollegen vom "
    "System erfahren?' The ask is gone, replaced by a question of the writer's own that "
    "carries the second point; pasted back it earns it.\n"
    "- retry, repeat, when the tutor's last message was already 'Richtig, der Chef "
    "entscheidet. Und die Kollegen, deren Anträge da durchlaufen: was steht ihnen zu?': the "
    "same message again. The ask repeating is not the fault; the unchanged sentence before "
    "it is. Notes: the student is stuck here; answer what they just said and help one step "
    "further.\n"
    "- retry, verdict: 'Noch nicht ganz. Und die Kollegen, deren Anträge da durchlaufen: was "
    "steht ihnen zu?' A point is met and the page shows it, and the reply denies it. Notes: "
    "open by confirming that the Chef decides, then end on the ask.\n"
    "- retry, verdict, the other way, when the student wrote 'Der Assistent entscheidet' and "
    "nothing is met, so the Ask now line is point 1's 'Wer entscheidet über die "
    "Urlaubsanträge?': 'Richtig, gut erkannt. Wer entscheidet über die Urlaubsanträge?' "
    "affirms a wrong answer."
)

VOICE_CHECKLIST = (
    "The tutor's draft was rewritten in a character's voice. The character may add an "
    "opener, a closer, a short aside and one image from its world, on lines of their own: "
    "that is its job, not a fault, and the brief's Style section binds the tutor, not the "
    "character. Check only:\n"
    "- meaning: a fact, a verdict, a number or a citation of the draft was changed or "
    "dropped, or a fact, a rule or a hint about the case was added. A flourish that says "
    "nothing about the case ('Erst prüfen, dann klingeln lassen!' is a flourish; 'Prüfen "
    "musst du trotzdem selbst' is a hint) is not meaning.\n"
    "- question: the character asked a question of its own about the case, or the tutor's "
    "question is gone or changed in meaning.\n"
    "- lost: the draft's sentences are buried under more character than lesson, or most of "
    "the draft is missing.\n"
    "Wording, paragraph count and the address are the character's own business: its "
    "manifest sets them, and the app's cleanup strips Markdown. Never fault them.\n"
    "verdict is ship when none of the three is wrong, else retry. notes tells the character, "
    "in two or three German sentences, what to keep or drop. score is 1 to 5 for how "
    "faithful and readable the rewrite is."
)

VOICE_EXAMPLES = (
    "Examples, from the holiday-request case that is not in this course. The draft: "
    "'Richtig, die Entscheidung bleibt beim Chef. Was müssen die Kollegen erfahren, deren "
    "Anträge da durchlaufen?'\n"
    "- ship: 'Hört, hört! Beim Chef bleibt die Entscheidung, so gehört sich das. Was müssen "
    "die Kollegen erfahren, deren Anträge da durchlaufen?'\n"
    "- retry, question: 'Hört, hört! Beim Chef bleibt die Entscheidung. Was müssen die "
    "Kollegen erfahren, und wer sagt es ihnen?' The character asked a second question. "
    "Notes: keep the tutor's question as it stands and add none."
)


def _judge(
    deps: GraphDeps, stage: str, marker: str, prompt: str, schema: type[Critique]
) -> Critique:
    started = time.perf_counter()
    prompt += f"\n\nReturn your judgement by calling the function {schema.__name__}."
    critique, raw = call_structured(deps, "strong", schema, mark(prompt, marker))
    log.info(
        "critic_verdict",
        stage=stage,
        verdict=critique.verdict,
        faults=critique.faults,
        credited=critique.credited,
        score=critique.score,
        seconds=round(time.perf_counter() - started, 2),
        **content_fields(deps, notes=critique.notes, verdict_raw=raw),
    )
    return critique


FAULT_RULES = {
    "leak": "the draft hands a missing rubric point to the student",
    "question": "the reply's one question is missing, changed or doubled, or a question "
    "stands in a reply whose outcome is right or settled",
    "verdict": "the opening contradicts the grader's verdict",
    "unhelpful": "the reply gives the student nothing",
    "repeat": "the reply repeats the tutor's last message",
}


def retry_block(previous: str, critique: Critique) -> str:
    """The handoff from the checker to whoever writes the next draft: what was rejected,
    the finding with its rule, the proposed revision, and the order of authority."""
    rules = "; ".join(FAULT_RULES[fault] for fault in critique.faults if fault in FAULT_RULES)
    finding = f"Fault: {', '.join(critique.faults) or 'unnamed'}" + (f" ({rules})" if rules else "")
    blocks = [
        "--- RETRY: the checker rejected your last draft",
        "The JOB and STYLE sections above still rule. Where a finding and they disagree, "
        "JOB and STYLE win.",
        f"--- YOUR LAST DRAFT\n{previous}",
        f"--- THE CHECKER'S FINDING\n{finding}\nNotes: {critique.notes}",
    ]
    if critique.revision.strip() and critique.revision.strip() != previous.strip():
        blocks.append(
            "--- THE CHECKER'S PROPOSED REVISION (a suggestion, not an order)\n"
            + critique.revision.strip()
        )
    blocks.append(
        "Write the reply again. Keep what the notes name as good. Adopt the proposed "
        "revision when it obeys JOB and STYLE, or write a better one that fixes the fault."
    )
    return "\n\n".join(blocks)


CRITIC_PREAMBLE = (
    "You are the checker of the tutor's next message in a German course on the EU AI Act. "
    "You read the tutor's draft before the student sees it: ship it, or send it back with "
    "a finding and a proposed revision. The fenced situation is course data, the machine "
    "verdict and the chat history; the draft stands in its own fence. Judge only what "
    "changes what the student gets. The instructions are English; the course material, "
    "the chat and the draft are German."
)


def critique_reply(deps: GraphDeps, brief: Brief, draft: str) -> Critique:
    prompt = "\n\n".join(
        [
            CRITIC_PREAMBLE,
            brief.text(),
            f"===== THE DRAFT TO CHECK =====\n{draft}\n===== END OF THE DRAFT =====",
            "--- CHECKS (in this order)\n"
            + (LEAK_CHECK + REPLY_CHECKS if brief.kind in OPEN_KINDS else REPLY_CHECKS),
            f"--- WORKED EXAMPLES\n{REPLY_EXAMPLES}",
        ]
    )
    critique = _judge(deps, "reply", CRITIC, prompt, ReplyCritique)
    # After a green try the confirmation and the ask are the whole reply (D118); a demanded
    # hint is what then hands the missing point over. With no ask to end on, a question
    # fault stands only when the draft asks one.
    dropped = {"unhelpful"} if brief.kind == "partial" else set()
    if brief.kind in ("right", "settled") and "?" not in draft:
        dropped.add("question")
    if dropped & set(critique.faults):
        faults = [f for f in critique.faults if f not in dropped]
        critique = critique.model_copy(
            update={"faults": faults, "verdict": "retry" if faults else "ship"}
        )
    # The mirror of the drop above: a closed question takes no question at all, so a
    # draft that asks one goes back whatever the checker said, its praise included.
    if brief.kind in ("right", "settled") and "?" in draft:
        faults = list(dict.fromkeys([*critique.faults, "question"]))
        note = (
            "The question is settled and the draft asks one. Drop the question: the "
            "confirmation and the why are the whole reply."
        )
        if "question" in critique.faults:
            notes = critique.notes
        elif critique.verdict == "ship":
            notes = note
        else:
            notes = f"{critique.notes} {note}".strip()
        critique = critique.model_copy(
            update={"verdict": "retry", "faults": faults, "notes": notes}
        )
    # The paste-back findings only count while the check ran at all.
    earned = (
        [n for n in critique.credited if n in brief.missing] if brief.kind in OPEN_KINDS else []
    )
    if earned and "leak" not in critique.faults:
        # The critic's own paste-back list outranks its verdict line, and its notes, which
        # praised the draft, give way to the finding: the writer must know what leaked.
        points = "; ".join(f"{n}. {brief.missing[n]}" for n in earned)
        critique = critique.model_copy(
            update={
                "verdict": "retry",
                "faults": [*critique.faults, "leak"],
                "credited": earned,
                "notes": (
                    f"Pasted back as the answer, the draft earns {points}. Drop what hands "
                    "it over and end on the Ask now line."
                ),
            }
        )
    return critique


def critique_voice(deps: GraphDeps, brief: Brief, draft: str, rewrite: str) -> Critique:
    prompt = "\n\n".join(
        [
            "You are the critic of a character's rewrite of a tutor's reply in a German AI "
            "Act course.",
            brief.text(),
            f"The tutor's draft:\n{draft}",
            f"The rewrite in the character's voice:\n{rewrite}",
            VOICE_CHECKLIST,
            VOICE_EXAMPLES,
        ]
    )
    return _judge(deps, "voice", VOICE_CRITIC, prompt, VoiceCritique)
