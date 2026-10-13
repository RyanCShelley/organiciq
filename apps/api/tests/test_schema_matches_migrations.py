"""The migrated schema has to match the models.

The rest of the suite builds its tables with `Base.metadata.create_all`,
so a model column that no migration ever created is invisible to it: the
tests pass, and production raises UndefinedColumn on the first insert.
That is not hypothetical — `staging_ser_audit_pages.inbound_editorial_links`
was added to the model with no migration, and every SE Ranking audit sync
failed for three weeks while 1,256 tests stayed green.

This builds a scratch database with alembic and compares it to the models.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.db import Base
from app.core.settings import get_settings

#: Alembic's own bookkeeping, which no model describes.
IGNORED_TABLES = {"alembic_version"}

DRIFT_DB = "organiciq_schema_drift"


@pytest.fixture(scope="module")
def migrated_url() -> str:
    """A database built only by running every migration in order."""
    url = get_settings().database_url
    if "organiciq_test" not in url:
        pytest.skip("Not pointed at the test database")

    base, _ = url.rsplit("/", 1)
    admin = create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{DRIFT_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{DRIFT_DB}"'))
    admin.dispose()

    target = f"{base}/{DRIFT_DB}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", target)
    command.upgrade(config, "head")

    yield target

    admin = create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{DRIFT_DB}" WITH (FORCE)'))
    admin.dispose()


def test_every_model_table_was_migrated(migrated_url: str):
    engine = create_engine(migrated_url)
    try:
        present = set(inspect(engine).get_table_names()) - IGNORED_TABLES
    finally:
        engine.dispose()
    missing = sorted(set(Base.metadata.tables) - present)
    assert not missing, f"Models declare tables no migration creates: {missing}"


def test_every_model_column_was_migrated(migrated_url: str):
    """A column the model writes and the schema has not got.

    This is the direction that breaks production: the insert names the
    column and Postgres rejects the statement.
    """
    engine = create_engine(migrated_url)
    try:
        inspector = inspect(engine)
        present = set(inspector.get_table_names())
        missing: list[str] = []
        for name, table in Base.metadata.tables.items():
            if name not in present:
                continue
            columns = {c["name"] for c in inspector.get_columns(name)}
            missing += [
                f"{name}.{column.name}"
                for column in table.columns
                if column.name not in columns
            ]
    finally:
        engine.dispose()
    assert not missing, f"Models declare columns no migration creates: {sorted(missing)}"


def test_no_column_was_left_behind(migrated_url: str):
    """A migrated column no model describes.

    Harmless to read and write around, but it means a model lost a field
    without a migration to drop it, and the next person to read the schema
    is told something untrue about what the table holds.
    """
    engine = create_engine(migrated_url)
    try:
        inspector = inspect(engine)
        orphans: list[str] = []
        for name in set(inspector.get_table_names()) - IGNORED_TABLES:
            table = Base.metadata.tables.get(name)
            if table is None:
                continue
            declared = {column.name for column in table.columns}
            orphans += [
                f"{name}.{column['name']}"
                for column in inspector.get_columns(name)
                if column["name"] not in declared
            ]
    finally:
        engine.dispose()
    assert not orphans, f"Schema has columns no model describes: {sorted(orphans)}"
