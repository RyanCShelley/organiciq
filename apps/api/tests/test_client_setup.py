"""The setup checklist, and the dependency order it encodes.

The order is not a preference: the lead-definitions screen offers the client's
own GA4 event names, so it has nothing to show before the first pull, and the
baseline averages GA4 sessions and lead events, so it needs both. Each test
here pins one of those dependencies, because the value of the list is that a
blocked step says what it is waiting for.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscPage
from app.services.client_setup import setup_state
from tests.conftest import client_header

TODAY = date(2026, 10, 10)


def _step(state: dict, key: str) -> dict:
    return next(s for s in state["steps"] if s["key"] == key)


def _ga4(db: Session, client: Client, url: str = "https://x.test/", sessions: int = 10):
    db.add(
        FactGa4Traffic(
            client_id=client.id,
            date=TODAY - timedelta(days=2),
            raw_url=url,
            normalized_url=url,
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=sessions,
        )
    )
    db.commit()


def test_a_fresh_client_is_told_to_connect_a_source_first(
    db: Session, client_a: Client
):
    state = setup_state(db, client_a)
    assert state["next"] == "sources"
    assert _step(state, "account")["done"] is True
    assert _step(state, "sources")["done"] is False


def test_lead_definitions_wait_for_the_ga4_pull(db: Session, client_a: Client):
    state = setup_state(db, client_a)
    # Not "do this next" — there are no event names to choose from yet.
    assert _step(state, "leads")["blocked_by"] == "needs the GA4 pull"

    _ga4(db, client_a)
    state = setup_state(db, client_a)
    assert _step(state, "leads")["blocked_by"] is None


def test_the_baseline_waits_for_the_lead_definitions(db: Session, client_a: Client):
    _ga4(db, client_a)
    state = setup_state(db, client_a)
    assert _step(state, "baseline")["blocked_by"] == "needs lead definitions"

    db.add(
        ConversionDefinition(
            client_id=client_a.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            active=True,
        )
    )
    db.commit()

    state = setup_state(db, client_a)
    assert _step(state, "baseline")["blocked_by"] is None
    assert _step(state, "baseline")["detail"] == "ready to build from GA4"
    assert _step(state, "leads")["detail"] == "1 event marked as leads"


def test_the_baseline_reports_the_goal_it_wrote(db: Session, client_a: Client):
    # The goal comes from here, which is why the add-client form stopped
    # asking for one.
    client_a.baseline_as_of = date(2026, 9, 1)
    client_a.baseline_monthly_sessions = 1200
    client_a.monthly_lead_goal = 31
    db.commit()

    step = _step(setup_state(db, client_a), "baseline")
    assert step["done"] is True
    assert "goal 31/mo" in step["detail"]


def test_page_stages_wait_for_conversion_pages(db: Session, client_a: Client):
    _ga4(db, client_a)
    assert (
        _step(setup_state(db, client_a), "page_stages")["blocked_by"]
        == "needs conversion pages"
    )


def test_the_next_step_is_never_a_blocked_one(db: Session, client_a: Client):
    state = setup_state(db, client_a)
    nxt = _step(state, state["next"])
    assert nxt["blocked_by"] is None
    assert nxt["done"] is False


def test_progress_counts_only_what_is_done(db: Session, client_a: Client):
    state = setup_state(db, client_a)
    assert state["done"] == sum(1 for s in state["steps"] if s["done"])
    assert state["total"] == len(state["steps"])


def test_the_endpoint_serves_the_checklist(client, client_a, admin_user):
    response = client.get(
        f"/clients/{client_a.id}/setup",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 9
    assert [s["key"] for s in body["steps"]] == [
        "account",
        "sources",
        "pull",
        "leads",
        "baseline",
        "conversion_pages",
        "page_stages",
        "keyword_targets",
        "first_run",
    ]


def test_another_clients_setup_is_refused(client, client_b, team_user):
    # team_user is assigned to client_a only.
    response = client.get(
        f"/clients/{client_b.id}/setup",
        headers=client_header(client_b.id, team_user.email),
    )
    assert response.status_code == 403
