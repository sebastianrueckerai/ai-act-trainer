from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DIR = Path(__file__).parent


@lru_cache(maxsize=8)
def _bundle(locale: str) -> dict[str, str]:
    path = _DIR / f"{locale}.yaml"
    data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {key: str(value).strip() for key, value in data.items()}


def t(locale: str, key: str, **fmt: object) -> str:
    """The fixed German string `key` for the pipeline, formatted with `fmt`."""
    bundle = _bundle(locale)
    if key not in bundle:
        raise KeyError(f"locale {locale!r} has no string {key!r}")
    return bundle[key].format(**fmt)


def has_locale(locale: str) -> bool:
    """Whether a fixed-string bundle is bundled for this locale."""
    return (_DIR / f"{locale}.yaml").is_file()


def format_date(locale: str, iso_date: str) -> str:
    """An ISO date written the way the locale writes dates."""
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime(t(locale, "date_format"))
