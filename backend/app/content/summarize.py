import argparse
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.content.law_summaries import (
    SUMMARY_KINDS,
    load_law_summaries,
    source_sha,
    summary_path,
)
from app.content.manifest import load_manifest
from app.content.models import LastChange, LawSummary, LawSummaryFile
from app.corpus.build import load_library
from app.corpus.model import Library, Node
from app.llm.models import chat_model
from app.llm.retry import with_retry
from app.settings import get_settings


class LawNodeSummary(BaseModel):
    """Eine kurze deutsche Zusammenfassung eines Abschnitts eines Gesetzes."""

    summary: str


SYSTEM = (
    "You write the index of a law library for a tutor that teaches the EU AI Act. For the piece "
    "of law you are given, write one German summary that says what it does, whom it binds and "
    "when it applies. Write about 40 words for an article or a statute section, and about 80 "
    "words for a division or a whole act. Use plain German, short sentences and the active "
    "voice. Keep the official term wherever the law uses one, and write ordinary spaces and "
    "hyphens, not the special ones the law text is printed with. Never name any provision by "
    "its number or its symbol, not of this law and not of another law such as the BGB: no "
    "article, section, chapter, annex, recital, paragraph or list point, neither in figures nor "
    "in Roman numerals. When the text points to another provision, say in your own words what that "
    "provision does instead of quoting the reference, because this text is an index entry and "
    "not a legal claim, and a number would go stale with the next amendment. You are given the "
    "text of the piece itself, or, for a division and for an act, the summary of each of its "
    "parts. Return your summary by calling the function {tool}."
)


def system_prompt() -> str:
    return SYSTEM.format(tool=LawNodeSummary.__name__)


def _summary_children(library: Library, node_id: str) -> list[Node]:
    return [child for child in library.children(node_id) if child.kind in SUMMARY_KINDS]


def _subtree(library: Library, node_id: str) -> list[str]:
    below = (
        n for child in _summary_children(library, node_id) for n in _subtree(library, child.id)
    )
    return [node_id, *below]


def summary_files(library: Library, act_id: str) -> list[list[str]]:
    """The node ids each file of one act holds, the file root first.

    The act's own file holds the act and the children that get no file of their own, which are
    its annexes and the articles under no division. Every top-level division gets a file of its
    own, holding its whole subtree.
    """
    children = _summary_children(library, act_id)
    own = [act_id, *(child.id for child in children if child.kind != "division")]
    divisions = [_subtree(library, child.id) for child in children if child.kind == "division"]
    return [own, *divisions]


def changed_nodes(
    library: Library, existing: dict[str, LawSummary], only_changed: bool
) -> set[str]:
    """Every node this run writes a new summary for.

    With only_changed, a node is rewritten when it has no stored summary, when its own hash no
    longer matches the library, or when a node below it was rewritten, so a division never
    describes articles that moved under it. Without only_changed, every node is rewritten.
    """
    changed: set[str] = set()

    def visit(node_id: str) -> bool:
        below = [visit(child.id) for child in _summary_children(library, node_id)]
        stored = existing.get(node_id)
        rewrite = (
            not only_changed
            or stored is None
            or stored.source_sha != source_sha(library, node_id)
            or any(below)
        )
        if rewrite:
            changed.add(node_id)
        return rewrite

    for act_id in library.acts:
        visit(act_id)
    return changed


def _messages(library: Library, node: Node, children: list[LawSummary]) -> list[BaseMessage]:
    index = library.index()
    if children:
        payload = "\n\n".join(f"{index[child.node].title}\n{child.summary}" for child in children)
    else:
        payload = node.text
    return [
        SystemMessage(system_prompt()),
        HumanMessage(f"Node: {node.id}\n{node.title}\n\n{payload}"),
    ]


def _walk(summary: LawSummary) -> Iterator[LawSummary]:
    yield summary
    for child in summary.children:
        yield from _walk(child)


def _summarize_node(
    runnable: Runnable,
    library: Library,
    existing: dict[str, LawSummary],
    changed: set[str],
    node_id: str,
) -> LawSummary:
    node = library.index()[node_id]
    children = [
        _summarize_node(runnable, library, existing, changed, child.id)
        for child in _summary_children(library, node_id)
    ]
    if node_id in changed:
        print(f"summarising {node_id}: {node.title}", file=sys.stderr)
        answer = with_retry(lambda: runnable.invoke(_messages(library, node, children)))
        summary = answer.summary
    else:
        summary = existing[node_id].summary
    return LawSummary(
        node=node_id,
        summary=summary,
        source_sha=source_sha(library, node_id),
        children=children,
    )


def summarize_library(
    model: BaseChatModel,
    library: Library,
    existing: dict[str, LawSummary],
    only_changed: bool = False,
) -> dict[str, list[LawSummary]]:
    """Summarise every act bottom up, one tree per file, keyed by act id.

    A leaf is summarised from its own text, a division from the summaries of its parts, an act
    from the summaries of its divisions and of the leaves that sit under no division. The model
    returns German prose and nothing else: the node id and the source hash are set here.
    """
    runnable = model.with_structured_output(LawNodeSummary, method="function_calling")
    changed = changed_nodes(library, existing, only_changed)
    result: dict[str, list[LawSummary]] = {}
    for act_id in library.acts:
        tree = _summarize_node(runnable, library, existing, changed, act_id)
        by_id = {summary.node: summary for summary in _walk(tree)}
        roots = []
        for nodes in summary_files(library, act_id):
            root = by_id[nodes[0]]
            held = set(nodes)
            kept = [child for child in root.children if child.node in held]
            roots.append(root.model_copy(update={"children": kept}))
        result[act_id] = roots
    return result


def _dump(root: LawSummary, path: Path, today: date) -> None:
    file = LawSummaryFile(
        node=root.node,
        summary=root.summary,
        source_sha=root.source_sha,
        children=root.children,
        last_change=LastChange(
            date=today,
            by="ai",
            trigger="law update" if path.exists() else "initial generation",
            summary="Aus dem Gesetzestext erzeugt, nicht geprüft",
        ),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            file.model_dump(mode="json"), allow_unicode=True, sort_keys=False, width=100
        ),
        encoding="utf-8",
    )


def _report(library: Library, law_dir: Path, changed: set[str]) -> None:
    for act_id in library.acts:
        for nodes in summary_files(library, act_id):
            path = summary_path(law_dir, nodes[0])
            written = sum(1 for node in nodes if node in changed)
            if written:
                print(f"write {path}: {written} written, {len(nodes) - written} carried forward")
            else:
                print(f"leave {path} alone: {len(nodes)} carried forward")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write the German law summaries the tutor navigates by, bottom up"
    )
    parser.add_argument("--act", help="summarise this act alone")
    parser.add_argument(
        "--changed", action="store_true", help="rewrite only the nodes whose law moved"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="say what would change and write nothing"
    )
    args = parser.parse_args()
    settings = get_settings()
    library = load_library(settings.corpus_dir)
    if args.act:
        act = library.act(args.act)
        if act is None:
            parser.error(f"the library holds no act {args.act!r}")
        library = Library(acts={args.act: act})
    law_dir = settings.content_dir / load_manifest(settings.content_dir).reference_locale / "law"
    existing = load_law_summaries(law_dir)
    changed = changed_nodes(library, existing, args.changed)
    if args.dry_run:
        _report(library, law_dir, changed)
        return
    result = summarize_library(
        chat_model(settings, "strong"), library, existing, only_changed=args.changed
    )
    today = date.today()
    written = 0
    for roots in result.values():
        for root in roots:
            path = summary_path(law_dir, root.node)
            if not any(summary.node in changed for summary in _walk(root)):
                print(f"leave {path} alone")
                continue
            _dump(root, path, today)
            written += 1
            print(f"wrote {path}")
    print(f"wrote {written} files under {law_dir}")


if __name__ == "__main__":
    main()
