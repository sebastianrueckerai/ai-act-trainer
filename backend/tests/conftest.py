from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.corpus.build import load_library
from app.corpus.model import Library
from app.main import create_app
from app.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "corpus"


@pytest.fixture(scope="session")
def library() -> Library:
    return load_library(CORPUS_DIR)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        content_dir=REPO_ROOT / "content",
        personas_dir=REPO_ROOT / "personas",
        corpus_dir=CORPUS_DIR,
        frontend_dist=tmp_path / "no-dist",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
