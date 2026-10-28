import logging
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.storage.migrate import run_migrations
from app.storage.models import Base


def test_migrations_create_every_model_table(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    run_migrations(url)
    inspector = inspect(create_engine(url))
    tables = set(inspector.get_table_names())
    assert "alembic_version" in tables
    assert set(Base.metadata.tables) <= tables
    assert any(
        index["name"] == "uq_training_sessions_one_active" and index["unique"]
        for index in inspector.get_indexes("training_sessions")
    )


def test_migrated_schema_matches_the_model_metadata(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'compared.db'}"
    run_migrations(url)
    with create_engine(url).connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_migrations_are_idempotent(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'twice.db'}"
    run_migrations(url)
    run_migrations(url)


def test_run_migrations_leaves_logging_configuration_alone(tmp_path: Path):
    access_logger = logging.getLogger("uvicorn.access")
    root_level = logging.getLogger().level
    run_migrations(f"sqlite:///{tmp_path / 'logging.db'}")
    assert access_logger.disabled is False
    assert logging.getLogger().level == root_level


def test_migrations_accept_a_percent_sign_in_the_url(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'b%25c.db'}"
    run_migrations(url)
    assert "alembic_version" in set(inspect(create_engine(url)).get_table_names())
