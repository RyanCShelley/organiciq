"""Booting with a migration that cannot be applied.

A migration whose down_revision named a revision that did not exist took the
whole API down: start-api.sh ran under `set -e`, alembic failed to resolve the
chain, and the script exited before uvicorn ever started. Every page 404ed and
the cause was a line in a boot log.

The script now records the failure and starts anyway; /health reports it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app, _migration_state


def test_health_is_ok_when_migrations_applied(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("MIGRATION_STATE_FILE", str(state))

    body = TestClient(app).get("/health").json()

    assert body == {"status": "ok", "migrations": "ok"}


def test_health_reports_a_failed_migration_without_failing(tmp_path, monkeypatch):
    """Still 200: a failing healthcheck restarts the service, which is the outage."""
    state = tmp_path / "state"
    state.write_text("failed", encoding="utf-8")
    log = tmp_path / "log"
    log.write_text(
        "INFO  [alembic] Context impl PostgresqlImpl.\n"
        "KeyError: '0034'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MIGRATION_STATE_FILE", str(state))
    monkeypatch.setenv("MIGRATION_LOG", str(log))

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["migrations"] == "failed"
    assert "KeyError" in body["detail"]


def test_a_missing_state_file_is_not_treated_as_failure(tmp_path, monkeypatch):
    """Running outside the start script, in tests, or locally."""
    monkeypatch.setenv("MIGRATION_STATE_FILE", str(tmp_path / "absent"))

    assert _migration_state() == ("unknown", None)


def test_no_state_file_configured_at_all(monkeypatch):
    monkeypatch.delenv("MIGRATION_STATE_FILE", raising=False)

    assert _migration_state() == ("unknown", None)


def _fake_bin(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _run_start_script(tmp_path, *, alembic_exit: int) -> tuple[int, Path, Path]:
    """Run the real start script with alembic and uvicorn stubbed out."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    started = tmp_path / "uvicorn-started"
    _fake_bin(bin_dir, "alembic", f'echo "alembic says no" >&2\nexit {alembic_exit}')
    _fake_bin(bin_dir, "uvicorn", f'echo started > "{started}"')

    script = Path(__file__).resolve().parents[1] / "scripts" / "start-api.sh"
    state = tmp_path / "state"
    result = subprocess.run(
        ["sh", str(script)],
        cwd=script.parent.parent,
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "EMBEDDED_WORKER": "false",
            "MIGRATION_STATE_FILE": str(state),
            "MIGRATION_LOG": str(tmp_path / "log"),
            "PORT": "8000",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, started, state


def test_the_api_still_starts_when_the_migration_fails(tmp_path):
    """The exact outage: alembic fails, and the script used to exit before uvicorn."""
    code, started, state = _run_start_script(tmp_path, alembic_exit=1)

    assert code == 0
    assert started.exists(), "uvicorn was never reached"
    assert state.read_text(encoding="utf-8") == "failed"


def test_a_clean_migration_records_success(tmp_path):
    code, started, state = _run_start_script(tmp_path, alembic_exit=0)

    assert code == 0
    assert started.exists()
    assert state.read_text(encoding="utf-8") == "ok"
