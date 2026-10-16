"""Locking a baseline: the rules, the versions, and what reaches the client.

Anyone on staff may lock. The protection is in the rules: every blocker has to be
acknowledged, a re-baseline has to say why, and the numbers are recomputed from the
source on the server, never accepted from the screen.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.models.baseline import BaselineVersion
from app.models.ga4 import FactGa4Event
from app.models.config import OrganicChannel
from tests.conftest import client_header

ACC = [
    ("2025-10", 1100, 0), ("2025-11", 1106, 1), ("2025-12", 1115, 10), ("2026-01", 863, 14),
    ("2026-02", 761, 14), ("2026-03", 745, 10), ("2026-04", 707, 9), ("2026-05", 654, 6),
    ("2026-06", 739, 11), ("2026-07", 608, 12), ("2026-08", 744, 4), ("2026-09", 806, 14),
]
CSV = "month,sessions,leads\n" + "\n".join(f"{m},{s},{l}" for m, s, l in ACC) + "\n"


def _lock(client, headers, client_id, **body):
    payload = {"source": "csv", "csv_text": CSV, "regime_start": "2025-12", **body}
    return client.post(f"/clients/{client_id}/baseline/lock", headers=headers, json=payload)


def test_the_first_lock_makes_version_one_and_fills_the_clients_baseline(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    response = _lock(client, headers, client_a.id)
    assert response.status_code == 200, response.text
    body = response.json()
    version = body["version"]
    assert version["version"] == 1 and version["reason_code"] == "initial" and version["locked_by"] == admin_user.email
    assert version["status"] == "draft" and version["regime_start"] == "2025-12"
    assert version["goal_monthly_leads"] < version["monthly_leads"]          # the low end of the range

    db.refresh(client_a)
    assert client_a.baseline_source == "baseline_series"
    assert client_a.baseline_monthly_sessions == round(version["monthly_sessions"])
    assert client_a.baseline_period_start == date(2025, 12, 1) and client_a.baseline_as_of == date(2026, 9, 30)
    projection = client_a.baseline_projection_json
    assert projection["baseline_version"] == 1 and projection["checkpoints"]
    assert projection["window"]["fully_covered"] is True           # the shape the dashboard already reads
    # No goal yet, so the lock sets the suggested one.
    assert body["goal_set_by_lock"] and client_a.monthly_lead_goal == body["suggested_monthly_lead_goal"]


def test_an_existing_goal_is_left_alone_unless_one_is_given(client, db, client_a, admin_user):
    client_a.monthly_lead_goal = 77
    db.commit()
    headers = client_header(client_a.id, admin_user.email)
    assert _lock(client, headers, client_a.id).json()["goal_set_by_lock"] is False
    db.refresh(client_a)
    assert client_a.monthly_lead_goal == 77

    again = _lock(client, headers, client_a.id, reason_code="correction", reason_note="Fixed the start month", monthly_lead_goal=40)
    assert again.status_code == 200
    db.refresh(client_a)
    assert client_a.monthly_lead_goal == 40


def test_blockers_must_be_acknowledged_before_a_lock(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    refused = _lock(client, headers, client_a.id, regime_start=None)
    assert refused.status_code == 400 and "tracking_gap" in refused.json()["detail"]
    assert db.query(BaselineVersion).count() == 0

    accepted = _lock(client, headers, client_a.id, regime_start=None, acknowledged=["tracking_gap"])
    assert accepted.status_code == 200
    assert accepted.json()["version"]["acknowledged"] == ["tracking_gap"]


def test_a_rebaseline_needs_a_reason_and_a_real_note_and_keeps_the_old_version(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    _lock(client, headers, client_a.id)

    assert _lock(client, headers, client_a.id).status_code == 400                                   # no reason
    assert _lock(client, headers, client_a.id, reason_code="relaunch", reason_note="short").status_code == 400
    assert _lock(client, headers, client_a.id, reason_code="because", reason_note="a long enough note").status_code == 400

    second = _lock(client, headers, client_a.id, reason_code="relaunch", reason_note="New site went live on 14 September", regime_start="2026-01")
    assert second.status_code == 200 and second.json()["version"]["version"] == 2

    listing = client.get(f"/clients/{client_a.id}/baseline/versions", headers=headers).json()
    assert [v["version"] for v in listing] == [2, 1]
    assert listing[1]["regime_start"] == "2025-12" and listing[0]["regime_start"] == "2026-01"
    assert listing[0]["reason_note"].startswith("New site")

    old = client.get(f"/clients/{client_a.id}/baseline/versions/1", headers=headers).json()
    assert old["snapshot"]["window"]["from"] == "2025-12" and old["snapshot"]["series"]
    assert client.get(f"/clients/{client_a.id}/baseline/versions/9", headers=headers).status_code == 404

    db.refresh(client_a)
    assert client_a.baseline_notes.startswith("v2 relaunch") and client_a.baseline_projection_json["baseline_version"] == 2


def test_the_first_baseline_cannot_claim_a_rebaseline_reason(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    assert _lock(client, headers, client_a.id, reason_code="relaunch", reason_note="not the first one really").status_code == 400


def test_a_baseline_locked_with_one_month_is_provisional(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    body = _lock(client, headers, client_a.id, regime_start="2026-09").json()
    assert body["version"]["status"] == "provisional"


def test_what_is_locked_is_what_the_series_route_computes_not_anything_sent(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    shown = client.post(
        f"/clients/{client_a.id}/baseline/series", headers=headers, json={"csv_text": CSV, "regime_start": "2025-12"}
    ).json()
    locked = _lock(client, headers, client_a.id).json()["version"]
    assert locked["monthly_sessions"] == shown["baseline"]["monthly_sessions"]
    assert locked["lead_rate_pct"] == shown["baseline"]["lead_rate_pct"]


def test_any_staff_member_with_access_can_lock_and_one_without_cannot(client, db, client_a, client_b, team_user):
    assert _lock(client, client_header(client_a.id, team_user.email), client_a.id).status_code == 200
    assert _lock(client, client_header(client_b.id, team_user.email), client_b.id).status_code == 403


def test_the_event_picker_lists_events_busiest_first_with_the_months_they_ran(client, db, client_a, admin_user):
    def event(name, day, count):
        db.add(
            FactGa4Event(
                id=uuid4(), client_id=client_a.id, date=day, raw_url="https://x.test/", normalized_url="https://x.test/",
                session_source="google", session_medium="organic", channel=OrganicChannel.ORGANIC_SEARCH,
                event_name=name, event_count=count,
            )
        )

    event("generate_lead", date(2026, 2, 10), 5)
    event("generate_lead", date(2026, 8, 10), 7)
    event("form_submit", date(2026, 3, 1), 1)
    db.commit()
    body = client.get(f"/clients/{client_a.id}/baseline/events", headers=client_header(client_a.id, admin_user.email)).json()
    assert [e["name"] for e in body["events"]] == ["generate_lead", "form_submit"]
    assert body["events"][0] == {"name": "generate_lead", "total": 12, "first_month": "2026-02", "last_month": "2026-08"}
