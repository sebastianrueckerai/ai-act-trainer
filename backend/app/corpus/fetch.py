import argparse
import hashlib
import io
import re
import zipfile
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml
from pydantic import BaseModel

from app.content.citations import FORMS, parse_citation, scan_citations, with_raw_citations
from app.content.law_summaries import source_sha
from app.content.loader import load_content
from app.content.models import ContentBundle, Question
from app.corpus.build import build_act, build_library
from app.corpus.manifest import ActSource, CorpusManifest, SourceFile, load_corpus_manifest
from app.corpus.model import Act, Library

CELLAR = "publications.europa.eu"
CELLAR_LANG = {"de": "deu", "en": "eng"}
FORMEX = "application/zip;mtype=fmx4"
ACCEPT = {
    ".xhtml": "application/xhtml+xml",
    ".html": "text/html",
    ".zip": "application/zip",
}
SPARQL = "http://publications.europa.eu/webapi/rdf/sparql"
QUERY = (
    "PREFIX cdm:<http://publications.europa.eu/ontology/cdm#> "
    "SELECT ?id WHERE {{ ?w cdm:resource_legal_id_celex ?id . "
    "FILTER(STRSTARTS(STR(?id), '{prefix}')) }} ORDER BY DESC(?id) LIMIT 1"
)


class VersionChange(BaseModel):
    act_id: str
    old_version: str
    new_version: str


# The undated CELEX returns 404, so the SPARQL query is the mechanism and not a convenience.
def latest_union_version(client: httpx.Client, celex_prefix: str) -> str:
    response = client.get(
        SPARQL,
        params={"query": QUERY.format(prefix=celex_prefix), "format": "text/csv"},
        timeout=120.0,
    )
    response.raise_for_status()
    rows = [line.strip().strip('"') for line in response.text.splitlines() if line.strip()]
    if len(rows) < 2:
        raise RuntimeError(f"no consolidation found for {celex_prefix}")
    return rows[1]


def latest_gii_version(content: bytes) -> str:
    match = re.search(rb'builddate="(\d+)"', content)
    if match is None:
        raise RuntimeError("no builddate in the gesetze-im-internet XML")
    return match.group(1).decode()


def _get(client: httpx.Client, url: str, accept: str, lang: str | None) -> bytes:
    headers = {"Accept": accept}
    if lang:
        headers["Accept-Language"] = lang
    response = client.get(url, headers=headers, follow_redirects=True, timeout=120.0)
    response.raise_for_status()
    return response.content


def _sent(file: SourceFile) -> str:
    """The format the server sends: the URL names it, or the stored file does.

    The Cellar addresses a document by CELEX and names no format, so there the stored file
    decides. A gesetze-im-internet URL names a zip that holds the XML we store.
    """
    return Path(urlsplit(file.url).path).suffix or Path(file.path).suffix


def _body(client: httpx.Client, act: ActSource, file: SourceFile) -> tuple[str, bytes]:
    """The path the download produced, and the bytes to store under it.

    A gesetze-im-internet zip holds one XML member whose name can change with a
    republication, so the member is found by suffix and the produced path names the member
    found inside the zip.
    """
    sent = _sent(file)
    cellar = CELLAR in file.url
    accept = FORMEX if cellar and sent == ".zip" else ACCEPT[sent]
    body = _get(client, file.url, accept, CELLAR_LANG[act.lang] if cellar else None)
    if sent == ".zip" and Path(file.path).suffix != ".zip":
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = archive.namelist()
            member = next((name for name in members if name.endswith(".xml")), None)
            if member is None:
                raise RuntimeError(f"{file.url} holds no XML member: {members}")
            return str(Path(file.path).parent / member), archive.read(member)
    return file.path, body


def fetch_act(corpus_dir: Path, act: ActSource, client: httpx.Client) -> ActSource:
    """Download the act's files, write them under the corpus and hash what landed."""
    files: list[SourceFile] = []
    for file in act.files:
        path, body = _body(client, act, file)
        target = corpus_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        files.append(SourceFile(path=path, url=file.url, sha256=hashlib.sha256(body).hexdigest()))
    return act.model_copy(update={"files": files})


def _write_manifest(corpus_dir: Path, manifest: CorpusManifest) -> None:
    (corpus_dir / "manifest.yaml").write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def fetch_all(corpus_dir: Path, client: httpx.Client) -> CorpusManifest:
    """Download every file the manifest lists, at the version the manifest names."""
    manifest = load_corpus_manifest(corpus_dir)
    fetched = CorpusManifest(
        downloaded=date.today(),
        acts=[fetch_act(corpus_dir, act, client) for act in manifest.acts],
    )
    _write_manifest(corpus_dir, fetched)
    return fetched


def _update_statute(
    corpus_dir: Path, act: ActSource, client: httpx.Client
) -> tuple[ActSource, VersionChange | None, Act | None]:
    """The statute against the build date its XML carries.

    gesetze-im-internet publishes no version index, so update learns the version by
    downloading the zip. A republication can carry a new document number, so the entry
    records the member name the download produced. A build date that is not newer, such as
    a rolled-back one, is not an update.
    """
    file = act.file(".xml")
    if file is None:
        raise FileNotFoundError(f"act {act.id} lists no .xml source")
    path, body = _body(client, act, file)
    newest = latest_gii_version(body)
    if int(newest) <= int(act.version):
        return act, None, None
    old = build_act(corpus_dir, act)
    target = corpus_dir / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    fresh = SourceFile(path=path, url=file.url, sha256=hashlib.sha256(body).hexdigest())
    files = [fresh if entry.path == file.path else entry for entry in act.files]
    return (
        act.model_copy(update={"version": newest, "files": files}),
        VersionChange(act_id=act.id, old_version=act.version, new_version=newest),
        old,
    )


def _redated(corpus_dir: Path, act: ActSource, newest: str, client: httpx.Client) -> ActSource:
    """The regulation with its version-dated files downloaded at the new version.

    A Cellar URL addresses a consolidation by CELEX and date, so a dated file moves by
    rewriting its URL and path. A file that names no version, such as the original in
    Formex, does not move with a consolidation and keeps its entry.
    """
    dated = {
        file.path: file.model_copy(
            update={
                "url": file.url.replace(act.version, newest),
                "path": file.path.replace(act.version, newest),
            }
        )
        for file in act.files
        if act.version in file.url
    }
    fetched = fetch_act(corpus_dir, act.model_copy(update={"files": list(dated.values())}), client)
    fresh = {file.path: file for file in fetched.files}
    files = [fresh[dated[file.path].path] if file.path in dated else file for file in act.files]
    return act.model_copy(update={"version": newest, "files": files})


def update_all(corpus_dir: Path, client: httpx.Client) -> list[VersionChange]:
    """Resolve the newest version of every act and download only what moved.

    A guidance page names no version, so update leaves it to fetch. Each act that moved is
    parsed before and after the download, so the report can name every node whose text
    changed. The report names the summaries grown stale, and tools/summarize-law --changed
    rewrites them.
    """
    manifest = load_corpus_manifest(corpus_dir)
    changes: list[VersionChange] = []
    old_acts: dict[str, Act] = {}
    acts: list[ActSource] = []
    for act in manifest.acts:
        if act.kind == "guidance":
            acts.append(act)
            continue
        if act.kind == "statute":
            updated, change, old = _update_statute(corpus_dir, act, client)
        else:
            newest = latest_union_version(client, act.version.partition("-")[0])
            if newest == act.version:
                updated, change, old = act, None, None
            else:
                change = VersionChange(act_id=act.id, old_version=act.version, new_version=newest)
                old = build_act(corpus_dir, act)
                updated = _redated(corpus_dir, act, newest, client)
        if change is None:
            acts.append(act)
            continue
        changes.append(change)
        old_acts[act.id] = old
        acts.append(updated)
    if changes:
        _write_manifest(corpus_dir, CorpusManifest(downloaded=date.today(), acts=acts))
        _change_report(corpus_dir, changes, old_acts)
    return changes


def _node_diff(old: Act, new: Act) -> list[tuple[str, str | None, str | None]]:
    """Every node whose text moved, was added or was dropped, old text and new text."""
    old_index, new_index = old.index(), new.index()
    pairs = []
    for node_id in sorted(set(old_index) | set(new_index)):
        before = old_index[node_id].text if node_id in old_index else None
        after = new_index[node_id].text if node_id in new_index else None
        if before != after:
            pairs.append((node_id, before, after))
    return pairs


def _question_citations(question: Question) -> Iterator[str]:
    """A question cites through its citation list and through the rubric's free text."""
    yield from question.citations
    if question.rubric is None:
        return
    for line in [*question.rubric.must_texts, *question.rubric.should]:
        for form in FORMS:
            yield from (match.group(0) for match in form.pattern.finditer(line))


def _citing_items(bundle: ContentBundle, changed: set[str]) -> list[tuple[str, str]]:
    """Every step, may line, question and rubric whose citation names a changed node."""
    hits: dict[str, str] = {}
    for locale, content in sorted(bundle.locales.items()):
        for chapter in content.chapters.values():
            for citation in scan_citations(with_raw_citations(chapter.may)):
                if citation.node_id in changed:
                    hits.setdefault(f"{locale}/{chapter.id}", citation.node_id)
            for step in chapter.steps:
                for ref in step.citations:
                    node_id = parse_citation(ref).node_id
                    if node_id in changed:
                        hits.setdefault(f"{locale}/{chapter.id}/{step.id}", node_id)
        for question in content.questions.values():
            for ref in _question_citations(question):
                node_id = parse_citation(ref).node_id
                if node_id in changed:
                    hits.setdefault(f"{locale}/{question.id}", node_id)
    return sorted(hits.items())


def _stale_summaries(bundle: ContentBundle, library: Library) -> list[str]:
    """Every summary whose node text moved, named so summarize-law --changed can run."""
    lines = []
    for node_id, summary in sorted(bundle.law.items()):
        if library.node(node_id) is None:
            lines.append(f"{node_id}: its node is gone from the library")
        elif summary.source_sha != source_sha(library, node_id):
            lines.append(f"{node_id}: run tools/summarize-law --changed")
    return lines


def _change_report(
    corpus_dir: Path, changes: list[VersionChange], old_acts: dict[str, Act]
) -> None:
    """Name what moved: nodes, the content citing them, and the summaries grown stale."""
    library = build_library(corpus_dir)
    print(f"acts moved: {len(changes)}")
    for change in changes:
        print(f"  {change.act_id} {change.old_version} -> {change.new_version}")
    pairs = [
        pair
        for change in changes
        for pair in _node_diff(old_acts[change.act_id], library.acts[change.act_id])
    ]
    print(f"changed nodes: {len(pairs)}")
    for node_id, before, after in pairs:
        print(f"  {node_id}")
        print(f"    old: {before if before is not None else '(absent)'}")
        print(f"    new: {after if after is not None else '(absent)'}")
    bundle = load_content(corpus_dir.parent / "content", corpus_dir.parent / "personas")
    citing = _citing_items(bundle, {node_id for node_id, _, _ in pairs})
    print(f"content citing a changed node: {len(citing)}")
    for where, node_id in citing:
        print(f"  {where} cites {node_id}")
    stale = _stale_summaries(bundle, library)
    print(f"law summaries whose source moved: {len(stale)}")
    for line in stale:
        print(f"  {line}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the corpus sources into corpus/raw")
    parser.add_argument("--corpus-dir", default=str(Path(__file__).resolve().parents[3] / "corpus"))
    parser.add_argument("command", nargs="?", default="fetch", choices=("fetch", "update"))
    args = parser.parse_args()
    with httpx.Client() as client:
        if args.command == "update":
            update_all(Path(args.corpus_dir), client)
            return
        manifest = fetch_all(Path(args.corpus_dir), client)
    for act in manifest.acts:
        print(f"fetched {act.id} {act.version}: {len(act.files)} files")


if __name__ == "__main__":
    main()
