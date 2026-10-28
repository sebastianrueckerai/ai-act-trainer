import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def test_startup_loads_the_library_and_the_content(client: TestClient):
    state = client.app.state
    assert set(state.library.acts) == {
        "ai_act",
        "gdpr",
        "kimig",
        "bdsg",
        "betrvg",
        "geschgehg",
        "qa",
    }
    assert state.library.acts["ai_act"].lang == "de"
    assert "01-warum-es-dich-betrifft" in state.content.locales["de"].chapters
    assert "clerk" in state.content.personas
    assert len(state.content.law) == 675


def test_startup_refuses_content_that_fails_the_lint(settings: Settings, tmp_path: Path):
    broken = tmp_path / "overlay" / "de" / "questions"
    broken.mkdir(parents=True)
    source = settings.content_dir / "de" / "questions" / "q-01-01.yaml"
    broken.joinpath("q-01-01.yaml").write_text(
        source.read_text(encoding="utf-8").replace('"Art. 4(1)"', '"Art. 999"'), encoding="utf-8"
    )
    settings = settings.model_copy(update={"content_overlay_dir": tmp_path / "overlay"})
    with pytest.raises(RuntimeError, match="content lint failed"), TestClient(create_app(settings)):
        pass


def test_startup_refuses_missing_persona_images(settings: Settings, tmp_path: Path):
    personas = tmp_path / "personas"
    shutil.copytree(settings.personas_dir, personas)
    (personas / "clerk" / "images" / "happy.png").unlink()

    settings = settings.model_copy(update={"personas_dir": personas})
    with pytest.raises(RuntimeError, match="happy"), TestClient(create_app(settings)):
        pass


def test_the_api_docs_serve_outside_production_only(settings: Settings):
    client = TestClient(create_app(settings))
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200

    production = settings.model_copy(
        update={
            "env": "production",
            "auth_backend": "invite",
            "secret_key": "x" * 32,
            "litellm_admin_key": "sk-test",
        }
    )
    client = TestClient(create_app(production))
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
