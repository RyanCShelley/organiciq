"""Resetting baselines for every client.

It is irreversible, so what matters most is that it does exactly what it says, only
for an admin, and not at all without the confirmation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from app.models.baseline import BaselineVersion
from app.models.config import ConversionDefinition
from tests.conftest import client_header


def _baselined(db, client, *, versions=2):
    client.baseline_as_of = date(2026, 9, 30)
    client.baseline_period_start = date(2026, 1, 1)
    client.baseline_period_end = date(2026, 9, 30)
    client.baseline_monthly_sessions = 3000
    client.baseline_monthly_leads = 20
    client.baseline_lead_rate_pct = 0.66
    client.baseline_source = "baseline_series"
    client.baseline_notes = "v2 relaunch"
    client.baseline_projection_json = {"checkpoints": [{"month": 3, "monthly_leads": 7}]}
    client.monthly_lead_goal = 35
    client.lead_goal_overrides = {"3": 9}
    for version in range(1, versions + 1):
        db.add(
            BaselineVersion(
                id=uuid4(), client_id=client.id, version=version, reason_code="initial" if version == 1 else "relaunch",
                locked_by="staff@smamarketing.net", locked_at=datetime.now(timezone.utc), status="draft",
                method_version="m", source_type="csv", window_from="2026-01", window_to="2026-09",
                lead_events=[], acknowledged=[], snapshot={"series": []},
            )
        )
    db.commit()


def test_the_preview_lists_only_clients_that_have_something_and_changes_nothing(client, db, client_a, client_b, admin_user):
    _baselined(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    body = client.get("/admin/baselines/reset-preview", headers=headers).json()
    assert [row["slug"] for row in body["clients"]] == [client_a.slug]
    assert body["totals"] == {"clients": 1, "versions": 2}
    assert body["clients"][0]["monthly_lead_goal"] == 35 and body["clients"][0]["goal_corrections"] == 1
    db.refresh(client_a)
    assert client_a.baseline_monthly_sessions == 3000


def test_without_the_confirmation_nothing_is_touched(client, db, client_a, admin_user):
    _baselined(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    for confirm in ("", "reset", "yes", "RESET "):
        response = client.post("/admin/baselines/reset", headers=headers, json={"confirm": confirm})
        assert response.status_code == 400 and "Nothing was changed" in response.json()["detail"]
    db.refresh(client_a)
    assert client_a.baseline_monthly_sessions == 3000 and db.query(BaselineVersion).count() == 2


def test_only_an_admin_can_reset(client, db, client_a, team_user):
    _baselined(db, client_a)
    headers = client_header(client_a.id, team_user.email)
    assert client.post("/admin/baselines/reset", headers=headers, json={"confirm": "RESET"}).status_code == 403
    assert client.get("/admin/baselines/reset-preview", headers=headers).status_code == 403
    db.refresh(client_a)
    assert client_a.baseline_monthly_sessions == 3000


def test_a_reset_clears_baselines_versions_and_goals_for_every_client_and_returns_a_copy(
    client, db, client_a, client_b, admin_user
):
    _baselined(db, client_a)
    _baselined(db, client_b, versions=1)
    client_a.brand_aliases = ["keep me"]
    db.add(ConversionDefinition(client_id=client_a.id, event_name="generate_lead", conversion_name="Lead", conversion_type="lead", active=True))
    db.commit()
    headers = client_header(client_a.id, admin_user.email)

    body = client.post("/admin/baselines/reset", headers=headers, json={"confirm": "RESET"}).json()
    assert body["reset_clients"] == 2 and body["versions_deleted"] == 3
    copy = next(row for row in body["removed"] if row["slug"] == client_a.slug)
    assert copy["client_fields"]["monthly_lead_goal"] == 35 and copy["client_fields"]["baseline_monthly_sessions"] == 3000
    assert [v["version"] for v in copy["versions"]] == [1, 2]

    db.expire_all()
    for row in (client_a, client_b):
        db.refresh(row)
        assert row.baseline_as_of is None and row.baseline_monthly_sessions is None
        assert row.baseline_lead_rate_pct is None and row.baseline_projection_json is None
        assert row.baseline_source is None and row.baseline_notes is None
        assert row.monthly_lead_goal is None and row.lead_goal_overrides == {}
    assert db.query(BaselineVersion).count() == 0
    # Nothing else on the client, and the lead definitions, survive.
    assert client_a.brand_aliases == ["keep me"] and client_a.domain
    assert db.query(ConversionDefinition).filter_by(client_id=client_a.id).count() == 1


def test_a_reset_can_be_limited_to_some_clients_and_a_second_one_finds_nothing_to_do(client, db, client_a, client_b, admin_user):
    _baselined(db, client_a)
    _baselined(db, client_b)
    headers = client_header(client_a.id, admin_user.email)
    one = client.post("/admin/baselines/reset", headers=headers, json={"confirm": "RESET", "client_ids": [str(client_a.id)]}).json()
    assert one["reset_clients"] == 1
    db.expire_all()
    db.refresh(client_b)
    assert client_b.baseline_monthly_sessions == 3000

    client.post("/admin/baselines/reset", headers=headers, json={"confirm": "RESET"})
    again = client.post("/admin/baselines/reset", headers=headers, json={"confirm": "RESET"}).json()
    assert again["reset_clients"] == 0 and again["versions_deleted"] == 0


def test_after_a_reset_a_client_can_be_baselined_again_from_version_one(client, db, client_a, admin_user):
    _baselined(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    client.post("/admin/baselines/reset", headers=headers, json={"confirm": "RESET"})
    csv = "month,sessions,leads\n2026-07,1000,10\n2026-08,1100,12\n2026-09,1050,11\n"
    locked = client.post(
        f"/clients/{client_a.id}/baseline/lock", headers=headers, json={"source": "csv", "csv_text": csv}
    )
    assert locked.status_code == 200 and locked.json()["version"]["version"] == 1
    assert locked.json()["version"]["reason_code"] == "initial"
