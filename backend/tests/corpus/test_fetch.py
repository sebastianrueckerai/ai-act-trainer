import hashlib
import io
import shutil
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest
import yaml

from app.content.law_summaries import source_sha
from app.corpus.build import build_library
from app.corpus.fetch import (
    VersionChange,
    fetch_act,
    fetch_all,
    latest_gii_version,
    latest_union_version,
    update_all,
)
from app.corpus.manifest import (
    ActSource,
    CorpusManifest,
    SourceFile,
    load_corpus_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

CELLAR_CSV = '"id"\n"02024R1689-20260727"\n"02024R1689-20240712"\n'
GII_XML = b'<?xml version="1.0"?><dokumente builddate="20260729215513" doknr="X"></dokumente>'
CURRENT_UNION = "02024R1689-20260727"
OLD_UNION = "02024R1689-20240712"
CURRENT_GII = "20260729215513"
OLD_GII = "20210101000000"


def _zip_of(member: str, body: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member, body)
    return buffer.getvalue()


def _statute(builddate: str, purpose: str) -> bytes:
    """A two-section gesetze-im-internet statute whose second section never moves."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<dokumente builddate="{builddate}">\n'
        " <norm>\n"
        "  <metadaten><enbez>\u00a7 2</enbez><titel>Zweck</titel></metadaten>\n"
        "  <textdaten><text><Content>\n"
        f"   <P>(1) {purpose}</P>\n"
        "  </Content></text></textdaten>\n"
        " </norm>\n"
        " <norm>\n"
        "  <metadaten><enbez>\u00a7 3</enbez><titel>Schutz</titel></metadaten>\n"
        "  <textdaten><text><Content>\n"
        "   <P>(1) Dieser Absatz bleibt unver\u00e4ndert.</P>\n"
        "  </Content></text></textdaten>\n"
        " </norm>\n"
        "</dokumente>\n"
    ).encode()


def _write_yaml(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _two_act_corpus(tmp_path: Path, ai_act_version: str, kimig_version: str = CURRENT_GII) -> Path:
    """A corpus of one regulation and one statute, laid out like the repo corpus.

    The bodies are the smallest each parser accepts, so update can parse the act before and
    after the move. The manifest hashes are the real hashes of the bytes on disk.
    """
    corpus_dir = tmp_path / "corpus"
    xhtml = b"<html/>"
    formex = _zip_of("BJNR0DF0B0034.fmx.xml", b'<?xml version="1.0"?><FORMEX/>')
    statute = _statute(kimig_version, "Dieser Absatz gilt als Test.")
    for path, body in {
        f"raw/{ai_act_version}/de.xhtml": xhtml,
        "raw/32024R1689/formex-de.zip": formex,
        "raw/kimig/BJNR0DF0B0026.xml": statute,
    }.items():
        target = corpus_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    manifest = CorpusManifest(
        downloaded=date(2026, 9, 16),
        acts=[
            ActSource(
                id="ai_act",
                kind="regulation",
                jurisdiction="eu",
                short_name="KI-VO",
                title="Verordnung (EU) 2024/1689",
                lang="de",
                version=ai_act_version,
                source_url="https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/deu",
                attribution="Test fixture, not law.",
                files=[
                    SourceFile(
                        path=f"raw/{ai_act_version}/de.xhtml",
                        url=f"http://publications.europa.eu/resource/celex/{ai_act_version}",
                        sha256=hashlib.sha256(xhtml).hexdigest(),
                    ),
                    SourceFile(
                        path="raw/32024R1689/formex-de.zip",
                        url="http://publications.europa.eu/resource/celex/32024R1689",
                        sha256=hashlib.sha256(formex).hexdigest(),
                    ),
                ],
            ),
            ActSource(
                id="kimig",
                kind="statute",
                jurisdiction="de",
                short_name="KI-MIG",
                title="Gesetz zur Markt\u00fcberwachung",
                lang="de",
                version=kimig_version,
                source_url="https://www.gesetze-im-internet.de/ki-mig/",
                attribution="Test fixture, not law.",
                files=[
                    SourceFile(
                        path="raw/kimig/BJNR0DF0B0026.xml",
                        url="https://www.gesetze-im-internet.de/ki-mig/xml.zip",
                        sha256=hashlib.sha256(statute).hexdigest(),
                    )
                ],
            ),
        ],
    )
    _write_yaml(corpus_dir / "manifest.yaml", manifest.model_dump(mode="json"))
    _write_yaml(
        tmp_path / "content" / "manifest.yaml",
        {
            "course_version": "0.1.0",
            "locales": ["de"],
            "reference_locale": "de",
        },
    )
    return corpus_dir


def test_fetch_all_writes_every_file_the_manifest_lists(tmp_path: Path):
    shutil.copy(REPO_ROOT / "corpus" / "manifest.yaml", tmp_path / "manifest.yaml")
    bodies = {
        (
            "publications.europa.eu",
            "/resource/celex/02024R1689-20260727",
            "deu",
        ): b"<html>de</html>",
        ("publications.europa.eu", "/resource/celex/32024R1689", "deu"): b"PK-de",
        (
            "publications.europa.eu",
            "/resource/celex/02016R0679-20160504",
            "deu",
        ): b"<html>gdpr-de</html>",
        (
            "digital-strategy.ec.europa.eu",
            "/de/faqs/ai-literacy-questions-answers",
            None,
        ): b"<html>qa-de</html>",
    }

    statutes = {
        "/ki-mig/xml.zip": "BJNR0DF0B0026.xml",
        "/bdsg_2018/xml.zip": "BJNR209710017.xml",
        "/betrvg/xml.zip": "BJNR000130972.xml",
        "/geschgehg/xml.zip": "BJNR046610019.xml",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        lang = request.headers.get("accept-language")
        key = (request.url.host, request.url.path, lang)
        if key[0] == "www.gesetze-im-internet.de":
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(statutes[request.url.path], "<dokumente/>")
            return httpx.Response(200, content=buffer.getvalue())
        assert key in bodies, key
        return httpx.Response(200, content=bodies[key])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    manifest = fetch_all(tmp_path, client)

    assert (tmp_path / "raw/02024R1689-20260727/de.xhtml").read_bytes() == b"<html>de</html>"
    assert (tmp_path / "raw/32024R1689/formex-de.zip").read_bytes() == b"PK-de"
    assert (tmp_path / "raw/kimig/BJNR0DF0B0026.xml").read_text() == "<dokumente/>"
    assert (tmp_path / "raw/bdsg/BJNR209710017.xml").read_text() == "<dokumente/>"
    assert (tmp_path / "raw/betrvg/BJNR000130972.xml").read_text() == "<dokumente/>"
    assert (tmp_path / "raw/geschgehg/BJNR046610019.xml").read_text() == "<dokumente/>"
    assert (tmp_path / "raw/02016R0679-20160504/de.xhtml").read_bytes() == b"<html>gdpr-de</html>"
    assert (tmp_path / "raw/qa/de.html").read_bytes() == b"<html>qa-de</html>"
    assert [act.id for act in manifest.acts] == [
        "ai_act",
        "kimig",
        "bdsg",
        "betrvg",
        "geschgehg",
        "gdpr",
        "qa",
    ]
    assert manifest.acts[0].files[0].sha256 == hashlib.sha256(b"<html>de</html>").hexdigest()

    written = load_corpus_manifest(tmp_path)
    assert written.acts[0].version == "02024R1689-20260727"
    assert written.acts[0].files[0].sha256 == manifest.acts[0].files[0].sha256
    assert written.acts[1].title == manifest.acts[1].title


def test_the_newest_union_consolidation_is_the_first_row():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "02024R1689" in request.url.params["query"]
        return httpx.Response(200, text=CELLAR_CSV)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert latest_union_version(client, "02024R1689") == "02024R1689-20260727"


def test_a_german_statute_carries_its_version_in_the_file():
    assert latest_gii_version(GII_XML) == "20260729215513"


def _update_handler(sparql: str, cellar: bytes, gii: bytes):
    def handler(request: httpx.Request) -> httpx.Response:
        if "sparql" in str(request.url):
            return httpx.Response(200, text=sparql)
        if request.url.host == "www.gesetze-im-internet.de":
            return httpx.Response(200, content=gii)
        return httpx.Response(200, content=cellar)

    return handler


def test_update_reports_nothing_when_every_act_is_current(tmp_path: Path, capsys):
    corpus_dir = _two_act_corpus(tmp_path, ai_act_version="02024R1689-20260727")
    before = (corpus_dir / "manifest.yaml").read_text(encoding="utf-8")

    client = httpx.Client(
        transport=httpx.MockTransport(
            _update_handler(CELLAR_CSV, b"<html/>", _zip_of("BJNR0DF0B0026.xml", GII_XML))
        )
    )
    assert update_all(corpus_dir, client) == []
    assert (corpus_dir / "manifest.yaml").read_text(encoding="utf-8") == before
    assert capsys.readouterr().out == ""


def test_update_reports_and_rewrites_an_act_that_moved(tmp_path: Path):
    corpus_dir = _two_act_corpus(tmp_path, ai_act_version="02024R1689-20240712")

    client = httpx.Client(
        transport=httpx.MockTransport(
            _update_handler(CELLAR_CSV, b"<html/>", _zip_of("BJNR0DF0B0026.xml", GII_XML))
        )
    )
    changes = update_all(corpus_dir, client)
    assert [(c.act_id, c.new_version) for c in changes] == [("ai_act", "02024R1689-20260727")]
    assert "02024R1689-20260727" in (corpus_dir / "manifest.yaml").read_text(encoding="utf-8")


def test_update_downloads_only_the_files_that_carry_the_version(tmp_path: Path):
    corpus_dir = _two_act_corpus(tmp_path, ai_act_version=OLD_UNION)
    formex_before = (corpus_dir / "raw/32024R1689/formex-de.zip").read_bytes()

    client = httpx.Client(
        transport=httpx.MockTransport(
            _update_handler(CELLAR_CSV, b"<html>new</html>", _zip_of("BJNR0DF0B0026.xml", GII_XML))
        )
    )
    changes = update_all(corpus_dir, client)

    assert [(c.act_id, c.old_version, c.new_version) for c in changes] == [
        ("ai_act", OLD_UNION, CURRENT_UNION)
    ]
    assert (corpus_dir / "raw/02024R1689-20260727/de.xhtml").read_bytes() == b"<html>new</html>"
    assert (corpus_dir / "raw/32024R1689/formex-de.zip").read_bytes() == formex_before
    ai_act = load_corpus_manifest(corpus_dir).acts[0]
    assert ai_act.version == CURRENT_UNION
    assert ai_act.files[0].path == "raw/02024R1689-20260727/de.xhtml"
    assert ai_act.files[0].sha256 == hashlib.sha256(b"<html>new</html>").hexdigest()
    assert ai_act.files[1].path == "raw/32024R1689/formex-de.zip"
    assert ai_act.files[1].sha256 == hashlib.sha256(formex_before).hexdigest()


def test_a_republished_statute_under_a_new_document_number_is_picked_up(tmp_path: Path):
    corpus_dir = _two_act_corpus(tmp_path, ai_act_version=CURRENT_UNION, kimig_version=OLD_GII)
    moved = _statute(CURRENT_GII, "Dieser Absatz gilt als ge\u00e4ndert.")

    client = httpx.Client(
        transport=httpx.MockTransport(
            _update_handler(CELLAR_CSV, b"<html/>", _zip_of("BJNR0DF0B0099.xml", moved))
        )
    )
    changes = update_all(corpus_dir, client)

    assert changes == [VersionChange(act_id="kimig", old_version=OLD_GII, new_version=CURRENT_GII)]
    assert (corpus_dir / "raw/kimig/BJNR0DF0B0099.xml").read_bytes() == moved
    kimig = load_corpus_manifest(corpus_dir).acts[1]
    assert kimig.version == CURRENT_GII
    assert kimig.files[0].path == "raw/kimig/BJNR0DF0B0099.xml"
    assert kimig.files[0].sha256 == hashlib.sha256(moved).hexdigest()


def test_a_rolled_back_statute_builddate_is_no_update(tmp_path: Path):
    corpus_dir = _two_act_corpus(tmp_path, ai_act_version=CURRENT_UNION, kimig_version=CURRENT_GII)
    before = (corpus_dir / "manifest.yaml").read_text(encoding="utf-8")
    rollback = _zip_of("BJNR0DF0B0026.xml", _statute(OLD_GII, "Dieser Absatz gilt als Rollback."))

    client = httpx.Client(
        transport=httpx.MockTransport(_update_handler(CELLAR_CSV, b"<html/>", rollback))
    )
    assert update_all(corpus_dir, client) == []
    assert (corpus_dir / "manifest.yaml").read_text(encoding="utf-8") == before
    assert "Rollback" not in (corpus_dir / "raw/kimig/BJNR0DF0B0026.xml").read_text(
        encoding="utf-8"
    )


def test_an_empty_sparql_answer_is_an_error():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text='"id"\n'))
    )
    with pytest.raises(RuntimeError, match="no consolidation found for 02024R1689"):
        latest_union_version(client, "02024R1689")


def test_a_statute_xml_without_a_builddate_is_an_error():
    with pytest.raises(RuntimeError, match="no builddate"):
        latest_gii_version(b'<?xml version="1.0"?><dokumente doknr="X"/>')


def test_a_zip_without_an_xml_member_names_the_archive(tmp_path: Path):
    corpus_dir = _two_act_corpus(tmp_path, ai_act_version=CURRENT_UNION)
    kimig = load_corpus_manifest(corpus_dir).acts[1]
    served = _zip_of("index.html", b"<html/>")
    client = httpx.Client(
        transport=httpx.MockTransport(_update_handler(CELLAR_CSV, b"<html/>", served))
    )
    with pytest.raises(RuntimeError, match=r"xml\.zip.*index\.html"):
        fetch_act(corpus_dir, kimig, client)


def _chapter(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "content" / "de" / "chapters" / "01-test.yaml",
        {
            "id": "01-test",
            "title": "Testkapitel",
            "intro": "Ein Kapitel zum Testen.",
            "duration_minutes": 3,
            "steps": [
                {
                    "id": "schritt-1",
                    "text": "Nennt den Zweck des Gesetzes.",
                    "citations": ["KI-MIG \u00a7 2"],
                },
                {
                    "id": "schritt-2",
                    "text": "Nennt den Schutz.",
                    "citations": ["KI-MIG \u00a7 3"],
                },
            ],
            "summary": "Ein Satz.",
            "may": "Das weißt du jetzt: Der Zweck steht in § 2 KI-MIG.",
            "last_change": {
                "date": date(2026, 9, 16),
                "by": "human",
                "trigger": "initial",
                "summary": "Erstfassung",
            },
        },
    )


def _question(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "content" / "de" / "questions" / "q-01-01.yaml",
        {
            "id": "q-01-01",
            "chapter": "01-test",
            "type": "free_text",
            "difficulty": 1,
            "question": "Welche Pflicht nennt das Gesetz?",
            "model_answer": "Die Pflicht aus \u00a7 2.",
            "explanation": "KI-MIG \u00a7 3 nennt den Schutz.",
            "citations": ["KI-MIG \u00a7 3"],
            "rubric": {
                "must": [
                    {
                        "point": "nennt die Pflicht aus KI-MIG \u00a7 2",
                        "ask": "Welche Pflicht ist das?",
                    }
                ],
                "should": ["nennt den Schutz aus KI-MIG \u00a7 3"],
            },
            "last_change": {
                "date": date(2026, 9, 16),
                "by": "human",
                "trigger": "initial",
                "summary": "Erstfassung",
            },
        },
    )


def _law_summary(path: Path, node: str, sha: str) -> None:
    _write_yaml(
        path,
        {
            "node": node,
            "summary": "Nennt den Zweck.",
            "source_sha": sha,
            "last_change": {
                "date": date(2026, 9, 16),
                "by": "ai",
                "trigger": "initial generation",
                "summary": "Erstfassung",
            },
        },
    )


def test_the_change_report_names_nodes_content_and_summaries(tmp_path: Path, capsys):
    corpus_dir = _two_act_corpus(tmp_path, ai_act_version=CURRENT_UNION, kimig_version=OLD_GII)
    _chapter(tmp_path)
    _question(tmp_path)
    law_dir = tmp_path / "content" / "de" / "law" / "kimig"
    _law_summary(law_dir / "sec_2.yaml", "kimig:sec_2", "0" * 64)
    fresh = source_sha(build_library(corpus_dir), "kimig:sec_3")
    _law_summary(law_dir / "sec_3.yaml", "kimig:sec_3", fresh)
    moved = _statute(CURRENT_GII, "Dieser Absatz gilt als ge\u00e4ndert.")

    client = httpx.Client(
        transport=httpx.MockTransport(
            _update_handler(CELLAR_CSV, b"<html/>", _zip_of("BJNR0DF0B0099.xml", moved))
        )
    )
    changes = update_all(corpus_dir, client)
    out = capsys.readouterr().out

    assert changes == [VersionChange(act_id="kimig", old_version=OLD_GII, new_version=CURRENT_GII)]
    assert "acts moved: 1" in out
    assert f"kimig {OLD_GII} -> {CURRENT_GII}" in out
    assert "changed nodes: 2" in out
    assert "kimig:sec_2.1" in out
    assert "old: Dieser Absatz gilt als Test." in out
    assert "new: Dieser Absatz gilt als ge\u00e4ndert." in out
    assert "content citing a changed node: 3" in out
    assert "de/01-test cites kimig:sec_2" in out
    assert "de/01-test/schritt-1 cites kimig:sec_2" in out
    assert "de/q-01-01 cites kimig:sec_2" in out
    assert "law summaries whose source moved: 1" in out
    assert "kimig:sec_2: run tools/summarize-law --changed" in out
    assert "schritt-2" not in out
    assert "sec_3" not in out
