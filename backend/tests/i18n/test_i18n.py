import json
from pathlib import Path

import pytest
import yaml

from app.content.gender import find_gendered
from app.i18n import format_date, has_locale, t

_I18N_DIR = Path(__file__).resolve().parents[2] / "app" / "i18n"
_FRONTEND_DE = Path(__file__).resolve().parents[3] / "frontend" / "src" / "locales" / "de.json"


def _leaf_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _leaf_strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _leaf_strings(v)]
    return []


def test_a_known_key_returns_the_german_string():
    assert t("de", "hedge").startswith("Ich bin ein Trainer")


def test_formatting_fills_the_placeholder():
    assert t("de", "test_count", met=1, total=2) == "1 von 2 geforderten Punkten. Noch einmal:"


def test_a_date_is_written_the_german_way():
    assert format_date("de", "2026-09-20") == "20.09.2026"


def test_only_a_locale_with_a_yaml_file_counts_as_bundled():
    assert has_locale("de")
    assert not has_locale("fr")


def test_an_unknown_key_raises_with_locale_and_key():
    with pytest.raises(KeyError, match="de.*no-such-key"):
        t("de", "no-such-key")


def test_an_unknown_locale_raises():
    with pytest.raises(FileNotFoundError):
        t("fr", "hedge")


def test_the_new_settings_have_their_defaults():
    from app.settings import Settings

    settings = Settings(_env_file=None, env="test")
    assert settings.compact_tokens == 6000
    assert settings.persona_model_role == "strong"


def test_the_checkpointer_packages_import():
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: F401
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: F401


def test_no_backend_locale_string_is_gendered():
    data = yaml.safe_load((_I18N_DIR / "de.yaml").read_text(encoding="utf-8"))
    for key, text in data.items():
        assert find_gendered(str(text)) == [], key


def test_no_frontend_locale_string_is_gendered():
    if not _FRONTEND_DE.is_file():
        pytest.skip("frontend/src/locales/de.json not present")
    data = json.loads(_FRONTEND_DE.read_text(encoding="utf-8"))
    for key, text in data.items():
        for s in _leaf_strings(text):
            assert find_gendered(s) == [], key
