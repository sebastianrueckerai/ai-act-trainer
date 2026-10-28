from langchain_core.messages import HumanMessage

from app.content.models import Question
from app.graph.answer import _final_text, answer_agent
from app.graph.brief import Brief, Kind, build_brief
from app.graph.critic import Critique, critique_reply, retry_block
from app.graph.deps import GraphDeps
from app.graph.govern import Governed, deadline, govern
from app.graph.prompts import EXPERTISE_RULES, REPLY, mark
from app.graph.state import GradedAnswer, SessionState
from app.graph.tools import library_brief
from app.graph.working import announce
from app.llm.retry import with_retry

WRITER_EXAMPLES = (
    "Examples from a case that is not in this course: a colleague wants the assistant to "
    "sort the team's holiday requests (Urlaubsanträge), and the question asks who decides "
    "and what has to be in place. The points there: the manager decides, not the "
    "assistant; the people concerned are told a system was used. Their Ask now lines: "
    "'Wer entscheidet über die Urlaubsanträge?' for the first, 'Und die Kollegen, deren "
    "Anträge da durchlaufen: was steht ihnen zu?' for the second.\n"
    "- right, the student wrote 'Der Chef entscheidet, und das Team weiß Bescheid': Genau. "
    "Die Entscheidung bleibt beim Menschen, und wer betroffen ist, erfährt vom Werkzeug.\n"
    "- partial, the student wrote 'Der Chef entscheidet': Richtig, die Entscheidung bleibt "
    "beim Chef. Und die Kollegen, deren Anträge da durchlaufen: was steht ihnen zu?\n"
    "- on_track, the student wrote 'Da muss man wohl aufpassen.': Du bist auf dem richtigen "
    "Weg: aufpassen ist das Stichwort. Wer entscheidet über die Urlaubsanträge?\n"
    "- not_an_attempt, the student wrote 'Was heißt Betreiber?': Betreiber ist, wer ein "
    "KI-System in eigener Verantwortung einsetzt, hier dein Unternehmen. Wer entscheidet "
    "über die Urlaubsanträge?\n"
    "- settled: Der Chef entscheidet, das Werkzeug sortiert nur vor. Und das Team erfährt, "
    "dass ein System mitgewirkt hat.\n"
    "- wrong, and this is a leak, never write it: Noch nicht ganz. Ergänze, dass das Team "
    "vom Werkzeug erfährt. (That hands the missing point over.)"
)


WRITER_PREAMBLE = (
    "You are the tutor of a German course on the EU AI Act and you write the tutor's next "
    "message. The fenced block below is the situation: the sections marked verbatim are "
    "the course's own German text and the chat exactly as it happened, the verdict is "
    "machine output about the student's last message, and the JOB section says what your "
    "reply must do. Course material and the chat stay German. Everything outside the "
    "fence, including this paragraph, is instructions in English."
)


def reply_prompt(
    deps: GraphDeps,
    brief: Brief,
    previous: str | None = None,
    critique: Critique | None = None,
) -> str:
    blocks = [
        WRITER_PREAMBLE,
        brief.text(),
        "Answer from the bundled acts alone when the student asks about the law:\n"
        f"{library_brief(deps.library, deps.content)}",
        EXPERTISE_RULES,
        WRITER_EXAMPLES,
    ]
    if previous is not None and critique is not None:
        blocks.append(retry_block(previous, critique))
    blocks.append("Write the reply. Return it as text and nothing else.")
    return mark("\n\n".join(blocks), REPLY)


def write_reply(
    deps: GraphDeps, brief: Brief, previous: str | None = None, critique: Critique | None = None
) -> str:
    """The whole reply to a student message while a question is open, from the brief. A
    retry gets the rejected draft and the checker's whole finding."""
    agent = answer_agent(deps, reply_prompt(deps, brief, previous, critique))
    result = with_retry(lambda: agent.invoke({"messages": [HumanMessage(brief.message)]}))
    return _final_text(result)


def governed_reply(
    deps: GraphDeps,
    state: SessionState,
    kind: Kind,
    question: Question,
    graded: GradedAnswer,
    tries: int,
    nudges: int = 0,
) -> tuple[Brief, Governed]:
    """The brief and the reply the critic loop shipped for one answer turn. On a retry the
    writer gets the checker's whole finding, the proposed revision included."""
    brief = build_brief(deps, state, kind, question, graded, tries, nudges)
    holder: dict[str, Critique] = {}

    def produce(previous: str | None, _notes: str | None) -> str:
        return write_reply(deps, brief, previous, holder.get("critique"))

    def judge(draft: str) -> Critique:
        holder["critique"] = critique_reply(deps, brief, draft)
        return holder["critique"]

    governed = govern(
        "reply",
        produce,
        judge,
        deadline(state, deps.settings),
        lambda step: announce(deps, state, step),
    )
    return brief, governed
