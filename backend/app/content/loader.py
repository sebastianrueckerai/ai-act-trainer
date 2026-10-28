from pathlib import Path

import yaml

from app.content.law_summaries import load_law_summaries
from app.content.manifest import load_manifest
from app.content.models import Chapter, ContentBundle, LocaleContent, PersonaManifest, Question

KINDS = {"chapters": Chapter, "questions": Question}


def _yaml_files(base: Path, overlay: Path | None, locale: str, kind: str) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for root in (base, overlay):
        if root is None:
            continue
        folder = root / locale / kind
        if folder.is_dir():
            for path in sorted(folder.glob("*.yaml")):
                files[path.name] = path
    return files


def _load_locale(content_dir: Path, overlay_dir: Path | None, locale: str) -> LocaleContent:
    loaded: dict[str, dict] = {}
    for kind, model in KINDS.items():
        items = {}
        for name, path in _yaml_files(content_dir, overlay_dir, locale, kind).items():
            with path.open(encoding="utf-8") as handle:
                item = model.model_validate(yaml.safe_load(handle))
            if item.id != path.stem:
                raise ValueError(
                    f"{path}: id {item.id!r} does not match the expected stem {path.stem!r}"
                )
            if item.id in items:
                raise ValueError(f"duplicate {kind[:-1]} id {item.id} in {locale} ({name})")
            items[item.id] = item
        loaded[kind] = items
    return LocaleContent(locale=locale, chapters=loaded["chapters"], questions=loaded["questions"])


def _load_personas(personas_dir: Path) -> dict[str, PersonaManifest]:
    personas: dict[str, PersonaManifest] = {}
    for manifest_path in sorted(personas_dir.glob("*/manifest.yaml")):
        with manifest_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        prompts = {
            p.stem: p.read_text(encoding="utf-8")
            for p in sorted((manifest_path.parent / "prompts").glob("*.md"))
        }
        persona = PersonaManifest.model_validate({**data, "prompts": prompts})
        personas[persona.id] = persona
    # The picker shows them in this order, and the clerk stands last.
    return dict(sorted(personas.items(), key=lambda item: (item[1].rank, item[0])))


def load_content(
    content_dir: Path,
    personas_dir: Path,
    overlay_dir: Path | None = None,
    law_dir: Path | None = None,
) -> ContentBundle:
    manifest = load_manifest(content_dir)
    locales = {
        locale: _load_locale(content_dir, overlay_dir, locale) for locale in manifest.locales
    }
    if law_dir is None:
        law_dir = content_dir / manifest.reference_locale / "law"
    return ContentBundle(
        manifest=manifest,
        locales=locales,
        personas=_load_personas(personas_dir),
        law=load_law_summaries(law_dir),
    )
