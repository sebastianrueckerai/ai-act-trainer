from datetime import date
from pathlib import Path

from app.corpus.manifest import load_corpus_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_repo_manifest_loads_and_names_every_source_file():
    manifest = load_corpus_manifest(REPO_ROOT / "corpus")
    assert manifest.downloaded == date(2026, 9, 15)
    assert [act.id for act in manifest.acts] == [
        "ai_act",
        "kimig",
        "bdsg",
        "betrvg",
        "geschgehg",
        "gdpr",
        "qa",
    ]
    paths = {file.path for act in manifest.acts for file in act.files}
    assert paths == {
        "raw/02024R1689-20260727/de.xhtml",
        "raw/32024R1689/formex-de.zip",
        "raw/kimig/BJNR0DF0B0026.xml",
        "raw/bdsg/BJNR209710017.xml",
        "raw/betrvg/BJNR000130972.xml",
        "raw/geschgehg/BJNR046610019.xml",
        "raw/02016R0679-20160504/de.xhtml",
        "raw/qa/de.html",
    }
    for act in manifest.acts:
        for file in act.files:
            assert (REPO_ROOT / "corpus" / file.path).is_file(), file.path
            assert len(file.sha256) == 64


def test_every_act_carries_the_metadata_a_parser_no_longer_holds():
    acts = {act.id: act for act in load_corpus_manifest(REPO_ROOT / "corpus").acts}
    assert acts["ai_act"].kind == "regulation"
    assert acts["ai_act"].version == "02024R1689-20260727"
    assert acts["ai_act"].attribution.startswith("© European Union")
    assert acts["kimig"].kind == "statute"
    assert acts["kimig"].jurisdiction == "de"
    assert acts["kimig"].version == "20260729215513"
    assert acts["bdsg"].kind == "statute"
    assert acts["bdsg"].version == "20260713215512"
    assert acts["bdsg"].source_url == "https://www.gesetze-im-internet.de/bdsg_2018/"
    for act_id in ("kimig", "bdsg", "betrvg", "geschgehg"):
        assert acts[act_id].attribution == (
            "§ 5 UrhG (amtliches Werk, gemeinfrei). "
            "Maßgeblich ist die Verkündung im Bundesgesetzblatt."
        )
    assert acts["qa"].kind == "guidance"
    assert acts["qa"].source_url.startswith("https://digital-strategy.ec.europa.eu/de/")
