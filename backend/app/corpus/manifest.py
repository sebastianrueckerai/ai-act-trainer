from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.corpus.model import Act, ActKind, Annex, Article, Division, Jurisdiction, Recital


class SourceFile(BaseModel):
    path: str
    url: str
    sha256: str


class ActSource(BaseModel):
    id: str
    kind: ActKind
    jurisdiction: Jurisdiction
    short_name: str
    title: str
    lang: str
    version: str
    source_url: str
    attribution: str
    files: list[SourceFile]

    def act(
        self,
        divisions: list[Division] | None = None,
        articles: list[Article] | None = None,
        annexes: list[Annex] | None = None,
        recitals: list[Recital] | None = None,
    ) -> Act:
        return Act(
            **self.model_dump(exclude={"files"}),
            divisions=divisions or [],
            articles=articles or [],
            annexes=annexes or [],
            recitals=recitals or [],
        )

    def file(self, suffix: str) -> SourceFile | None:
        return next((file for file in self.files if file.path.endswith(suffix)), None)


class CorpusManifest(BaseModel):
    downloaded: date
    acts: list[ActSource]


def load_corpus_manifest(corpus_dir: Path) -> CorpusManifest:
    with (corpus_dir / "manifest.yaml").open(encoding="utf-8") as handle:
        return CorpusManifest.model_validate(yaml.safe_load(handle))
