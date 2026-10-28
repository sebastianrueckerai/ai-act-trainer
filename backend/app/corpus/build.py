import argparse
import json
from functools import lru_cache
from pathlib import Path

from app.corpus.manifest import ActSource, load_corpus_manifest
from app.corpus.model import Act, Library
from app.corpus.parse_eurlex import parse_consolidated
from app.corpus.parse_formex import parse_recitals
from app.corpus.parse_gii import parse_gii
from app.corpus.parse_qa import parse_qa


def build_library(corpus_dir: Path) -> Library:
    manifest = load_corpus_manifest(corpus_dir)
    return Library(acts={source.id: build_act(corpus_dir, source) for source in manifest.acts})


@lru_cache
def load_library(corpus_dir: Path) -> Library:
    # Parsing the XHTML costs seconds; the test suite builds about twenty apps through
    # the `client` fixture, so this is cached per corpus_dir.
    return build_library(corpus_dir)


def build_act(corpus_dir: Path, source: ActSource) -> Act:
    if source.kind == "statute":
        divisions, articles = parse_gii(_path(corpus_dir, source, ".xml"))
        return source.act(divisions=divisions, articles=articles)
    if source.kind == "guidance":
        return parse_qa(_path(corpus_dir, source, ".html"), source)
    divisions, articles, annexes = parse_consolidated(_path(corpus_dir, source, ".xhtml"))
    formex = source.file(".zip")
    recitals = parse_recitals(corpus_dir / formex.path) if formex else []
    return source.act(divisions=divisions, articles=articles, annexes=annexes, recitals=recitals)


def _path(corpus_dir: Path, source: ActSource, suffix: str) -> Path:
    file = source.file(suffix)
    if file is None:
        raise FileNotFoundError(f"act {source.id} lists no {suffix} source")
    return corpus_dir / file.path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the library")
    parser.add_argument("--corpus-dir", default=str(Path(__file__).resolve().parents[3] / "corpus"))
    parser.add_argument("--out", help="write the library JSON to this file")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()
    library = build_library(Path(args.corpus_dir))
    if args.out:
        Path(args.out).write_text(library.model_dump_json(indent=2), encoding="utf-8")
    if args.stats or not args.out:
        print(
            json.dumps(
                {
                    "acts": {
                        act.id: {
                            "kind": act.kind,
                            "divisions": len(act.divisions),
                            "articles": len(act.articles),
                            "annexes": len(act.annexes),
                            "recitals": len(act.recitals),
                        }
                        for act in library.acts.values()
                    },
                    "nodes": len(library.index()),
                }
            )
        )


if __name__ == "__main__":
    main()
