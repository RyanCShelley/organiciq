"""The OAuth handshake store has to forget.

The state token is random and single-use, so it does its CSRF job. What it
did not do was expire: a handshake nobody finished stayed in memory for the
life of the process, and the dict only ever grew.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api.routers import oauth_google as mod


def _seed(token: str, *, age: timedelta) -> None:
    mod._oauth_states[token] = {
        "client_id": "c",
        "user_id": "u",
        "started_at": datetime.now(timezone.utc) - age,
    }


def setup_function() -> None:
    mod._oauth_states.clear()


def test_a_handshake_nobody_finished_is_forgotten():
    _seed("abandoned", age=timedelta(hours=2))
    mod._drop_expired_states(datetime.now(timezone.utc))
    assert "abandoned" not in mod._oauth_states


def test_a_handshake_in_progress_survives():
    _seed("live", age=timedelta(minutes=1))
    mod._drop_expired_states(datetime.now(timezone.utc))
    assert "live" in mod._oauth_states


def test_a_state_with_no_start_time_is_dropped():
    """Left by an older build. Keeping it forever is the bug being fixed,
    and it can no longer be completed anyway."""
    mod._oauth_states["legacy"] = {"client_id": "c", "user_id": "u"}
    mod._drop_expired_states(datetime.now(timezone.utc))
    assert "legacy" not in mod._oauth_states


def test_expiry_does_not_touch_the_others():
    _seed("old", age=timedelta(hours=1))
    _seed("new", age=timedelta(seconds=5))
    mod._drop_expired_states(datetime.now(timezone.utc))
    assert set(mod._oauth_states) == {"new"}
