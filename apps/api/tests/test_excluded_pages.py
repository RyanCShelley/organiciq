"""Pages the engine must leave alone, and the refresh gate.

Both tables have existed as long as the engine and neither could be written
to: "we are not working on careers" was a thing somebody could say and not
record, and Boys Electrical's only traffic action was on /careers.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import RefreshQueueEntry
from app.models.decision import ExcludedPage
from app.services.monthly_run import load_exclusions
from tests.conftest import client_header

TODAY = date(2026, 10, 12)


def test_an_exclusion_needs_a_reason(client, client_a, admin_user):
    """A rule nobody can review is one nobody will dare remove."""
    response = client.put(
        "/decisions/excluded-pages",
        headers=client_header(client_a.id, admin_user.email),
        json=[{"url_pattern": "/careers*", "reason": "   "}],
    )
    assert response.status_code == 422
    assert "/careers*" in response.json()["detail"]


def test_the_list_round_trips(client, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    saved = client.put(
        "/decisions/excluded-pages",
        headers=headers,
        json=[
            {"url_pattern": "/careers*", "reason": "Not a focus this year"},
            {"url_pattern": "/legal", "reason": "Nothing to win"},
        ],
    )
    assert saved.status_code == 200
    assert [r["url_pattern"] for r in saved.json()] == ["/careers*", "/legal"]

    # Replacing the whole list is how the panel edits it, so removing a row
    # has to actually remove it.
    trimmed = client.put(
        "/decisions/excluded-pages",
        headers=headers,
        json=[{"url_pattern": "/legal", "reason": "Nothing to win"}],
    )
    assert [r["url_pattern"] for r in trimmed.json()] == ["/legal"]


def test_the_same_pattern_twice_is_refused(client, client_a, admin_user):
    response = client.put(
        "/decisions/excluded-pages",
        headers=client_header(client_a.id, admin_user.email),
        json=[
            {"url_pattern": "/careers*", "reason": "one"},
            {"url_pattern": "/careers*", "reason": "two"},
        ],
    )
    assert response.status_code == 400


def test_a_page_booked_for_a_rewrite_is_excluded_for_that_month(
    db: Session, client_a: Client
):
    """The old lever engine honoured this and the new one did not.

    The rewrite is paid for out of the content allowance, so spending a
    growth slot on it charges the client twice for one job.
    """
    db.add(
        RefreshQueueEntry(
            client_id=client_a.id,
            normalized_url="https://x.test/guide",
            month=date(2026, 10, 1),
        )
    )
    db.commit()

    reasons = {e.url_pattern: e.reason for e in load_exclusions(db, client_a, today=TODAY)}
    assert "https://x.test/guide" in reasons
    assert "booked for a content rewrite" in reasons["https://x.test/guide"]

    # Next month it is fair game again.
    assert load_exclusions(db, client_a, today=date(2026, 11, 12)) == []


def test_both_sources_arrive_together(db: Session, client_a: Client):
    db.add(
        ExcludedPage(
            client_id=client_a.id, url_pattern="/careers*", reason="Not a focus"
        )
    )
    db.add(
        RefreshQueueEntry(
            client_id=client_a.id,
            normalized_url="https://x.test/guide",
            month=date(2026, 10, 1),
        )
    )
    db.commit()
    patterns = {e.url_pattern for e in load_exclusions(db, client_a, today=TODAY)}
    assert patterns == {"/careers*", "https://x.test/guide"}


def test_the_tasklist_id_survives_a_save(client, client_a, admin_user):
    """It silently did not.

    `ClientCreate` and `ClientUpdate` carry the same field names, so an edit
    aimed at the second landed in the first — and the settings form PATCHes,
    so Teamwork's tasklist id was dropped on every save while the field
    appeared to work.
    """
    headers = client_header(client_a.id, admin_user.email)
    saved = client.patch(
        f"/clients/{client_a.id}",
        headers=headers,
        json={"teamwork_tasklist_id": "2859633"},
    )
    assert saved.status_code == 200
    assert saved.json()["teamwork_tasklist_id"] == "2859633"

    fetched = client.get(f"/clients/{client_a.id}", headers=headers)
    assert fetched.json()["teamwork_tasklist_id"] == "2859633"
