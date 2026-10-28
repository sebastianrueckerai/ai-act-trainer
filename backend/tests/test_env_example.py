from pathlib import Path

from app.settings import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def test_env_example_loads_as_written(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    settings = Settings(_env_file=ENV_EXAMPLE)
    assert settings.proxy_trusted_addresses == []
    assert settings.content_dir == Settings.model_fields["content_dir"].default
    assert settings.auth_backend == "dev"
    assert settings.data_level == 0
