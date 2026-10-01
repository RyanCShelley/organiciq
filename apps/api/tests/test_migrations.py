"""The migration chain itself.

A migration declaring `down_revision = "0034"` when every revision in this
project is identified by its full slug took the API down: alembic could not
resolve the chain, `alembic upgrade head` failed, and start-api.sh runs under
`set -e`. The whole suite passed regardless, because conftest builds the schema
with `Base.metadata.create_all` and never runs a migration.

These tests exercise the chain the way production does.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(url: str | None = None) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    if url:
        config.set_main_option("sqlalchemy.url", url)
    return config


def test_the_chain_has_exactly_one_head():
    """Two heads means someone branched; none means the graph is broken."""
    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    assert len(heads) == 1, f"expected a single head, found {heads}"


def test_every_down_revision_names_a_revision_that_exists():
    """The exact failure that took production down."""
    script = ScriptDirectory.from_config(_alembic_config())
    known = {revision.revision for revision in script.walk_revisions()}
    for revision in script.walk_revisions():
        for parent in revision._all_down_revisions:
            assert parent in known, (
                f"{revision.revision} declares down_revision {parent!r}, "
                f"which is not a revision in this project"
            )


def test_upgrade_head_runs_against_an_empty_database(db):
    """Resolving is not running: a migration can resolve and still fail on the DDL.

    Uses a scratch database so the suite's own schema is untouched. `db` is
    requested only to be sure the server is reachable before trying.
    """
    from alembic import command

    admin_url = sa.engine.make_url(os.environ["DATABASE_URL"])
    scratch = f"{admin_url.database}_migrations"

    engine = sa.create_engine(admin_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(sa.text(f'drop database if exists "{scratch}"'))
        conn.execute(sa.text(f'create database "{scratch}"'))

    scratch_url = admin_url.set(database=scratch)
    try:
        command.upgrade(_alembic_config(scratch_url.render_as_string(hide_password=False)), "head")

        check = sa.create_engine(scratch_url)
        with check.connect() as conn:
            applied = conn.execute(sa.text("select version_num from alembic_version")).scalar()
        check.dispose()

        script = ScriptDirectory.from_config(_alembic_config())
        assert applied == script.get_current_head()
    finally:
        with engine.connect() as conn:
            conn.execute(
                sa.text(
                    "select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname = :name and pid <> pg_backend_pid()"
                ),
                {"name": scratch},
            )
            conn.execute(sa.text(f'drop database if exists "{scratch}"'))
        engine.dispose()
