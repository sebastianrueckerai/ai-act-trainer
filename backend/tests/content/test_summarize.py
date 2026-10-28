import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from app.content import summarize
from app.content.law_summaries import load_law_summaries, source_sha
from app.content.models import LawSummary
from app.content.summarize import LawNodeSummary, summarize_library, system_prompt
from app.corpus.model import Library
from app.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_KINDS = {"act", "division", "article", "annex"}


@dataclass
class FakeModel:
    """A chat model that answers every summary call with a canned German line.

    It reads the node id off the first line of the human message, which is how the tool names
    the node it is asking about, and keeps the whole payload under that id. A test can then ask
    which nodes the run called for, in which order, and what each call carried.
    """

    kwargs: list[dict[str, Any]] = field(default_factory=list)
    called_nodes: list[str] = field(default_factory=list)
    payloads: dict[str, str] = field(default_factory=dict)

    def with_structured_output(self, schema: type[BaseModel], **kwargs: Any) -> Runnable:
        self.kwargs.append(kwargs)

        def answer(messages: list[BaseMessage]) -> Any:
            payload = str(messages[-1].content)
            node = payload.splitlines()[0].removeprefix("Node: ")
            self.called_nodes.append(node)
            self.payloads[node] = payload
            return schema(summary=f"Zusammenfassung von {node}.")

        return RunnableLambda(answer)

    def call_for(self, node: str) -> str:
        return self.payloads[node]


@pytest.fixture
def fake_model() -> FakeModel:
    return FakeModel()


def _walk(summaries: list[LawSummary]) -> Iterator[LawSummary]:
    for summary in summaries:
        yield summary
        yield from _walk(summary.children)


def _every_summary(result: dict[str, list[LawSummary]]) -> list[LawSummary]:
    return [summary for files in result.values() for summary in _walk(files)]


def _stored(library: Library) -> dict[str, LawSummary]:
    """A stored summary for every node the tool covers, each carrying the current hash."""
    return {
        node_id: LawSummary(node=node_id, summary="alt", source_sha=source_sha(library, node_id))
        for node_id, node in library.index().items()
        if node.kind in SUMMARY_KINDS
    }


def test_a_leaf_summary_is_written_from_the_article_text(fake_model, library):
    result = summarize_library(fake_model, library, existing={})

    assert "ai_act" in result
    call = fake_model.call_for("ai_act:art_26")
    assert call.startswith(
        "Node: ai_act:art_26\nArtikel 26: Pflichten der Betreiber von Hochrisiko-KI-Systemen\n"
    )
    assert "technische und organisatorische Maßnahmen" in call


def test_a_long_article_reaches_the_model_whole(fake_model, library):
    summarize_library(fake_model, library, existing={})

    text = library.node("ai_act:art_3").text
    assert len(text) > 10000
    assert text in fake_model.call_for("ai_act:art_3")


def test_a_division_summary_is_written_from_its_article_summaries_not_the_articles(
    fake_model, library
):
    summarize_library(fake_model, library, existing={})

    division_call = fake_model.call_for("ai_act:cpt_II")
    assert "Artikel 5" in division_call
    assert len(library.node("ai_act:art_5").text) > 4000
    assert len(division_call) < 4000


def test_an_act_summary_is_written_from_its_division_summaries_and_its_own_leaves(
    fake_model, library
):
    summarize_library(fake_model, library, existing={})

    act_call = fake_model.call_for("ai_act")
    assert "Zusammenfassung von ai_act:cpt_II." in act_call
    assert "Zusammenfassung von ai_act:anx_III." in act_call
    assert "Zusammenfassung von ai_act:art_5." not in act_call


def test_only_changed_skips_a_node_whose_hash_still_matches(fake_model, library):
    existing = {
        node_id: LawSummary(node=node_id, summary="alt", source_sha=source_sha(library, node_id))
        for node_id in ("ai_act:art_4",)
    }

    summarize_library(fake_model, library, existing, only_changed=True)

    assert "ai_act:art_4" not in fake_model.called_nodes


def test_only_changed_makes_no_call_when_no_hash_moved(fake_model, library):
    summarize_library(fake_model, library, _stored(library), only_changed=True)

    assert fake_model.called_nodes == []


def test_a_changed_node_also_rewrites_its_ancestors(fake_model, library):
    existing = _stored(library)
    existing["ai_act:art_4"] = LawSummary(node="ai_act:art_4", summary="alt", source_sha="stale")

    summarize_library(fake_model, library, existing, only_changed=True)

    assert fake_model.called_nodes == ["ai_act:art_4", "ai_act:cpt_I", "ai_act"]


def test_a_carried_forward_summary_keeps_its_text(fake_model, library):
    existing = _stored(library)
    existing["ai_act:art_4"] = LawSummary(
        node="ai_act:art_4",
        summary="Artikel 4 verlangt KI-Kompetenz.",
        source_sha=source_sha(library, "ai_act:art_4"),
    )

    result = summarize_library(fake_model, library, existing, only_changed=True)

    carried = {summary.node: summary.summary for summary in _every_summary(result)}
    assert carried["ai_act:art_4"] == "Artikel 4 verlangt KI-Kompetenz."


def test_without_only_changed_every_node_is_rewritten(fake_model, library):
    result = summarize_library(fake_model, library, _stored(library))

    written = _every_summary(result)
    assert len(fake_model.called_nodes) == len(written)
    assert all(summary.summary.startswith("Zusammenfassung von") for summary in written)


def test_the_model_never_sets_the_source_hash(fake_model, library):
    result = summarize_library(fake_model, library, existing={})

    for files in result.values():
        for entry in _walk(files):
            assert entry.source_sha == source_sha(library, entry.node)


def test_every_act_division_article_and_annex_gets_exactly_one_summary(fake_model, library):
    result = summarize_library(fake_model, library, existing={})

    covered = [summary.node for summary in _every_summary(result)]
    expected = {node_id for node_id, node in library.index().items() if node.kind in SUMMARY_KINDS}
    assert len(covered) == len(expected)
    assert set(covered) == expected


def test_the_act_file_holds_the_annexes_and_the_articles_under_no_division(fake_model, library):
    result = summarize_library(fake_model, library, existing={})

    roots = result["ai_act"]
    children = library.children("ai_act")
    assert roots[0].node == "ai_act"
    assert [child.node for child in roots[0].children] == [
        child.id for child in children if child.kind != "division"
    ]
    assert [root.node for root in roots[1:]] == [
        child.id for child in children if child.kind == "division"
    ]


def test_a_division_file_nests_its_articles(fake_model, library):
    result = summarize_library(fake_model, library, existing={})

    division = next(root for root in result["ai_act"] if root.node == "ai_act:cpt_II")
    assert [child.node for child in division.children] == ["ai_act:art_5"]


def test_an_act_without_divisions_writes_one_file(fake_model, library):
    result = summarize_library(fake_model, library, existing={})

    assert len(result["qa"]) == 1
    assert len(result["qa"][0].children) == 37


def test_the_structured_output_method_stays_pinned(fake_model, library):
    summarize_library(fake_model, library, _stored(library), only_changed=True)

    assert fake_model.kwargs == [{"method": "function_calling"}]


def test_the_schema_carries_a_docstring():
    assert LawNodeSummary.__doc__


def test_the_system_prompt_names_the_function_and_asks_for_german():
    prompt = system_prompt()

    assert "LawNodeSummary" in prompt
    assert "German" in prompt


def content_dir(tmp_path: Path) -> Path:
    content = tmp_path / "content"
    (content / "de").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "content" / "manifest.yaml", content / "manifest.yaml")
    return content


def run_cli(monkeypatch: pytest.MonkeyPatch, content: Path, *args: str) -> FakeModel:
    """Run the summarize CLI against a fake model and return the fake."""
    model = FakeModel()
    monkeypatch.setattr(summarize, "chat_model", lambda *_args, **_kwargs: model)
    monkeypatch.setattr(
        summarize, "get_settings", lambda: Settings(_env_file=None, content_dir=content)
    )
    monkeypatch.setattr(sys, "argv", ["summarize-law", *args])
    summarize.main()
    return model


def test_the_command_writes_one_file_per_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    content = content_dir(tmp_path)

    run_cli(monkeypatch, content, "--act", "geschgehg")

    law_dir = content / "de" / "law"
    assert sorted(path.name for path in (law_dir / "geschgehg").iterdir()) == [
        "_act.yaml",
        "cpt_1.yaml",
        "cpt_2.yaml",
        "cpt_3.yaml",
        "cpt_4.yaml",
    ]
    assert len(load_law_summaries(law_dir)) == 28


def test_a_written_file_records_who_wrote_it_and_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    content = content_dir(tmp_path)

    run_cli(monkeypatch, content, "--act", "geschgehg")

    written = yaml.safe_load(
        (content / "de" / "law" / "geschgehg" / "cpt_1.yaml").read_text(encoding="utf-8")
    )
    assert written["last_change"]["by"] == "ai"
    assert written["last_change"]["trigger"] == "initial generation"
    assert written["last_change"]["date"] == date.today().isoformat()


def test_a_rewrite_of_an_existing_file_says_law_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    content = content_dir(tmp_path)
    run_cli(monkeypatch, content, "--act", "geschgehg")

    run_cli(monkeypatch, content, "--act", "geschgehg")

    written = yaml.safe_load(
        (content / "de" / "law" / "geschgehg" / "cpt_1.yaml").read_text(encoding="utf-8")
    )
    assert written["last_change"]["trigger"] == "law update"


def mark_by_hand(path: Path) -> str:
    """Edit a written file the way a human would, leaving it valid for the loader."""
    file = yaml.safe_load(path.read_text(encoding="utf-8"))
    file["summary"] = "Von Hand geschrieben."
    path.write_text(yaml.safe_dump(file, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path.read_text(encoding="utf-8")


def test_changed_leaves_every_untouched_file_alone(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    content = content_dir(tmp_path)
    run_cli(monkeypatch, content, "--act", "geschgehg")
    path = content / "de" / "law" / "geschgehg" / "cpt_1.yaml"
    edited = mark_by_hand(path)

    model = run_cli(monkeypatch, content, "--act", "geschgehg", "--changed")

    assert model.called_nodes == []
    assert path.read_text(encoding="utf-8") == edited


def test_a_dry_run_writes_nothing_and_calls_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
):
    content = content_dir(tmp_path)

    model = run_cli(monkeypatch, content, "--act", "geschgehg", "--dry-run")

    assert model.called_nodes == []
    assert not (content / "de" / "law").exists()
    printed = capsys.readouterr().out
    assert "geschgehg/_act.yaml" in printed
    assert "geschgehg/cpt_4.yaml" in printed


def test_a_dry_run_after_a_full_run_would_leave_every_file_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
):
    content = content_dir(tmp_path)
    run_cli(monkeypatch, content, "--act", "geschgehg")
    capsys.readouterr()

    run_cli(monkeypatch, content, "--act", "geschgehg", "--changed", "--dry-run")

    lines = capsys.readouterr().out.splitlines()
    assert len([line for line in lines if line.startswith("leave")]) == 5
    assert [line for line in lines if line.startswith("write")] == []


def test_the_command_refuses_an_act_the_library_does_not_hold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    content = content_dir(tmp_path)

    with pytest.raises(SystemExit):
        run_cli(monkeypatch, content, "--act", "no_such_act")
