from pathlib import Path

import yaml
from pydantic import BaseModel


class LawAmendments(BaseModel):
    amended_by: list[str] = []


class CourseManifest(BaseModel):
    course_version: str
    locales: list[str]
    reference_locale: str
    law: LawAmendments = LawAmendments()


def load_manifest(content_dir: Path) -> CourseManifest:
    path = content_dir / "manifest.yaml"
    with path.open(encoding="utf-8") as handle:
        return CourseManifest.model_validate(yaml.safe_load(handle))
