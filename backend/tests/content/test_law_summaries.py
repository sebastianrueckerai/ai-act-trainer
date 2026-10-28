from pathlib import Path

import pytest

from app.content.law_summaries import load_law_summaries, source_sha
from app.content.lint import lint
from app.content.loader import load_content
from app.content.models import ContentBundle, LawSummary
from app.corpus.model import Act, Article, Division, Library

REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_CONTENT = REPO_ROOT / "content"
REPO_PERSONAS = REPO_ROOT / "personas"


def _bundle_with_summary(
    tmp_path: Path, node: str, sha: str, summary: str = "Eine Zusammenfassung."
) -> ContentBundle:
    act_id, _, local_id = node.partition(":")
    act_dir = tmp_path / act_id
    act_dir.mkdir(parents=True, exist_ok=True)
    (act_dir / f"{local_id or '_act'}.yaml").write_text(
        f"node: {node}\n"
        f'summary: "{summary}"\n'
        f'source_sha: "{sha}"\n'
        "last_change:\n"
        "  date: 2026-09-16\n"
        "  by: ai\n"
        "  trigger: initial generation\n"
        "  summary: Erstfassung\n",
        encoding="utf-8",
    )
    return load_content(REPO_CONTENT, REPO_PERSONAS, law_dir=tmp_path)


@pytest.fixture
def bundle_with_summaries(tmp_path: Path) -> ContentBundle:
    return _bundle_with_summary(tmp_path, node="ai_act:art_26", sha="0" * 64)


def _library_with_articles(article_count: int) -> Library:
    """A one-division, one-act library, with a chosen number of articles under that division."""
    articles = [
        Article(id=f"art_{i}", number=str(i), title=f"Artikel {i}", division_id="cpt_I")
        for i in range(1, article_count + 1)
    ]
    act = Act(
        id="test_act",
        kind="regulation",
        short_name="Testgesetz",
        title="Testgesetz",
        jurisdiction="eu",
        lang="de",
        version="1",
        source_url="https://example.invalid/test-act",
        attribution="Test fixture, not law.",
        divisions=[Division(id="cpt_I", number="I", title="Kapitel I")],
        articles=articles,
    )
    return Library(acts={"test_act": act})


def test_source_sha_changes_when_a_child_is_added():
    before, after = _library_with_articles(2), _library_with_articles(3)
    assert before.node("test_act:cpt_I").text == after.node("test_act:cpt_I").text
    assert source_sha(before, "test_act:cpt_I") != source_sha(after, "test_act:cpt_I")


def test_source_sha_is_stable_and_differs_for_nodes_with_different_text(library):
    before = source_sha(library, "ai_act:cpt_II")
    assert before == source_sha(library, "ai_act:cpt_II")
    assert before != source_sha(library, "ai_act:cpt_I")


def test_summaries_load_flattened_by_node_id(tmp_path: Path):
    (tmp_path / "ai_act").mkdir(parents=True)
    (tmp_path / "ai_act" / "cpt_II.yaml").write_text(
        "node: ai_act:cpt_II\n"
        "summary: Kapitel II nennt die verbotenen Praktiken.\n"
        'source_sha: "abc"\n'
        "children:\n"
        "  - node: ai_act:art_5\n"
        "    summary: Artikel 5 zaehlt die verbotenen Praktiken auf.\n"
        '    source_sha: "def"\n'
        "last_change:\n"
        "  date: 2026-09-16\n"
        "  by: ai\n"
        "  trigger: initial generation\n"
        "  summary: Erstfassung\n",
        encoding="utf-8",
    )
    summaries: dict[str, LawSummary] = load_law_summaries(tmp_path)
    assert set(summaries) == {"ai_act:cpt_II", "ai_act:art_5"}
    assert summaries["ai_act:art_5"].summary.startswith("Artikel 5")


def test_load_law_summaries_rejects_a_duplicate_node_id(tmp_path: Path):
    act_dir = tmp_path / "ai_act"
    act_dir.mkdir(parents=True)
    (act_dir / "_act.yaml").write_text(
        "node: ai_act\n"
        "summary: Der AI Act regelt Systeme künstlicher Intelligenz.\n"
        'source_sha: "abc"\n'
        "children:\n"
        "  - node: ai_act:cpt_II\n"
        "    summary: Duplikat.\n"
        '    source_sha: "def"\n'
        "last_change:\n"
        "  date: 2026-09-16\n"
        "  by: ai\n"
        "  trigger: initial generation\n"
        "  summary: Erstfassung\n",
        encoding="utf-8",
    )
    (act_dir / "cpt_II.yaml").write_text(
        "node: ai_act:cpt_II\n"
        "summary: Kapitel II nennt die verbotenen Praktiken.\n"
        'source_sha: "ghi"\n'
        "last_change:\n"
        "  date: 2026-09-16\n"
        "  by: ai\n"
        "  trigger: initial generation\n"
        "  summary: Erstfassung\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ai_act:cpt_II"):
        load_law_summaries(tmp_path)


def test_load_law_summaries_rejects_a_node_from_the_wrong_act(tmp_path: Path):
    act_dir = tmp_path / "ai_act"
    act_dir.mkdir(parents=True)
    (act_dir / "cpt_II.yaml").write_text(
        "node: gdpr:cpt_II\n"
        "summary: Kapitel II nennt die verbotenen Praktiken.\n"
        'source_sha: "abc"\n'
        "last_change:\n"
        "  date: 2026-09-16\n"
        "  by: ai\n"
        "  trigger: initial generation\n"
        "  summary: Erstfassung\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        load_law_summaries(tmp_path)
    assert "gdpr" in str(excinfo.value)
    assert "ai_act" in str(excinfo.value)


def test_load_law_summaries_rejects_a_child_from_the_wrong_act(tmp_path: Path):
    act_dir = tmp_path / "ai_act"
    act_dir.mkdir(parents=True)
    (act_dir / "cpt_II.yaml").write_text(
        "node: ai_act:cpt_II\n"
        "summary: Kapitel II nennt die verbotenen Praktiken.\n"
        'source_sha: "abc"\n'
        "children:\n"
        "  - node: gdpr:art_5\n"
        "    summary: Fremdes Gesetz.\n"
        '    source_sha: "def"\n'
        "last_change:\n"
        "  date: 2026-09-16\n"
        "  by: ai\n"
        "  trigger: initial generation\n"
        "  summary: Erstfassung\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        load_law_summaries(tmp_path)
    assert "gdpr:art_5" in str(excinfo.value)


def test_load_law_summaries_ignores_an_entry_that_is_not_a_yaml_file(tmp_path: Path):
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    (tmp_path / "README.md").write_text("Wie diese Dateien entstehen.\n", encoding="utf-8")
    act_dir = tmp_path / "ai_act"
    act_dir.mkdir(parents=True)
    (act_dir / "cpt_II.yaml").write_text(
        "node: ai_act:cpt_II\n"
        "summary: Kapitel II nennt die verbotenen Praktiken.\n"
        'source_sha: "abc"\n'
        "last_change:\n"
        "  date: 2026-09-16\n"
        "  by: ai\n"
        "  trigger: initial generation\n"
        "  summary: Erstfassung\n",
        encoding="utf-8",
    )
    assert set(load_law_summaries(tmp_path)) == {"ai_act:cpt_II"}


def test_load_law_summaries_rejects_a_stray_file_at_the_root(tmp_path: Path):
    stray = tmp_path / "something.yaml"
    stray.write_text('node: ai_act\nsummary: Stray.\nsource_sha: "abc"\n', encoding="utf-8")
    with pytest.raises(ValueError) as excinfo:
        load_law_summaries(tmp_path)
    assert str(stray) in str(excinfo.value)


def test_lint_fails_on_a_stale_source_sha(bundle_with_summaries, library):
    problems = lint(bundle_with_summaries, library)
    assert any("source_sha" in p.message for p in problems)


def test_lint_fails_on_a_summary_for_a_node_that_does_not_exist(library, tmp_path: Path):
    bundle = _bundle_with_summary(tmp_path, node="ai_act:art_999", sha="whatever")
    problems = lint(bundle, library)
    assert any("ai_act:art_999" in p.message for p in problems)


def test_lint_fails_when_an_article_has_no_summary(library, tmp_path: Path):
    bundle = _bundle_with_summary(
        tmp_path, node="ai_act:art_4", sha=source_sha(library, "ai_act:art_4")
    )
    problems = lint(bundle, library)
    assert any("ai_act:art_5" in p.message for p in problems)


def test_lint_fails_when_no_summaries_exist_at_all(library, tmp_path: Path):
    bundle = load_content(REPO_CONTENT, REPO_PERSONAS, law_dir=tmp_path / "nowhere")
    problems = lint(bundle, library)
    assert [p.where for p in problems] == ["law"]
    assert "missing entirely" in problems[0].message


@pytest.mark.parametrize(
    "text",
    [
        "Die Pflichten stehen in Art. 26(7).",
        "Siehe BDSG § 26(1) für Beschäftigtendaten.",
        "Geregelt in § 26 des Gesetzes.",
        "Vergleiche Rec. 20 zur Auslegung.",
        "Die Pflichten stehen in Artikel 5.",
        "Die Liste steht in Anhang III.",
        "Erwägungsgrund 20 erläutert die Auslegung.",
        "Die Pflichten stehen in § 26 Abs. 1.",
        "Daneben gilt § 619a BGB.",
    ],
)
def test_lint_fails_when_a_summary_carries_a_citation(library, tmp_path: Path, text):
    bundle = _bundle_with_summary(
        tmp_path,
        node="ai_act:art_26",
        sha=source_sha(library, "ai_act:art_26"),
        summary=text,
    )
    problems = lint(bundle, library)
    assert any("citation" in p.message for p in problems)
