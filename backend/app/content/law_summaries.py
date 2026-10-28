import hashlib
from pathlib import Path

import yaml

from app.content.models import LawSummary, LawSummaryFile
from app.corpus.model import Library

SUMMARY_KINDS = frozenset({"act", "division", "article", "annex"})


def source_sha(library: Library, node_id: str) -> str:
    node = library.node(node_id)
    if node is None:
        raise KeyError(node_id)
    lines = [node.text, *(child.id for child in library.children(node_id))]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _act_id(node: str) -> str:
    return node.partition(":")[0]


def _expected_stem(node: str) -> str:
    return node.partition(":")[2] or "_act"


def summary_path(law_dir: Path, node: str) -> Path:
    """Where the file rooted at a node lives, spelled the way the loader expects to find it."""
    return law_dir / _act_id(node) / f"{_expected_stem(node)}.yaml"


def _flatten(summary: LawSummary, target: dict[str, LawSummary], path: Path, act_id: str) -> None:
    if _act_id(summary.node) != act_id:
        raise ValueError(
            f"{path}: node {summary.node!r} belongs to act {_act_id(summary.node)!r}, "
            f"not the {act_id!r} directory it is in"
        )
    if summary.node in target:
        raise ValueError(f"duplicate law summary id {summary.node} in {path}")
    target[summary.node] = summary
    for child in summary.children:
        _flatten(child, target, path, act_id)


def load_law_summaries(law_dir: Path) -> dict[str, LawSummary]:
    summaries: dict[str, LawSummary] = {}
    if not law_dir.is_dir():
        return summaries
    for entry in sorted(law_dir.iterdir()):
        if not entry.is_dir():
            if entry.suffix == ".yaml":
                raise ValueError(f"{entry}: law_dir holds one directory per act, not a stray file")
            continue
        for path in sorted(entry.glob("*.yaml")):
            with path.open(encoding="utf-8") as handle:
                file = LawSummaryFile.model_validate(yaml.safe_load(handle))
            expected = _expected_stem(file.node)
            if path.stem != expected:
                raise ValueError(
                    f"{path}: node {file.node!r} does not match the expected filename "
                    f"{expected}.yaml"
                )
            _flatten(file, summaries, path, entry.name)
    return summaries
