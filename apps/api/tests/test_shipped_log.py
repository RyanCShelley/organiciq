"""Marking work shipped writes it to the account history.

The team asked for a running list of what has been completed and published.
The history already existed for typed and imported entries; shipping from the
plan did not touch it, so the list was only as complete as somebody's memory.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.annotation import Annotation, AnnotationType
from app.models.client import Client
from app.models.decision import MonthlyRecord
from tests.conftest import client_header

MONTH = "2026-10"


def _record(db: Session, client: Client) -> None:
    def row(uid, action_id, title, url, term=None):
        return {"action_uid": uid, "id": action_id, "title": title, "target_url": url,
                "term": term, "metric": "Average position on the term", "slot": 1}

    db.add(
        MonthlyRecord(
            client_id=client.id, month=MONTH, run_saved_at=datetime.now(timezone.utc),
            constraint_name="visibility", held_since=MONTH, confidence="medium",
            record={
                "actions": [row("u-growth", "V-1", "Fix the links", "/a")],
                "incidents": [],
                "updates": [row("u-refresh", "U-5", "Refresh this page", "/old")],
                "new_content": [row("u-new", "C-2", "Write the page for “heat pumps”", "", "heat pumps")],
            },
        )
    )
    db.commit()


def _ship(client, headers, uid, on):
    return client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/shipped", headers=headers, json={"shipped_on": on}
    )


def _entries(db: Session, client_a: Client) -> dict[str, Annotation]:
    db.expire_all()
    return {
        row.engine_uid: row
        for row in db.query(Annotation).filter(Annotation.client_id == client_a.id)
    }


def test_shipping_writes_one_entry_of_the_right_kind(client, db: Session, client_a, admin_user):
    _record(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    for uid in ("u-growth", "u-refresh", "u-new"):
        assert _ship(client, headers, uid, "2026-10-14").status_code == 200

    entries = _entries(db, client_a)
    assert entries["u-new"].annotation_type is AnnotationType.CONTENT_PUBLISHED
    assert entries["u-refresh"].annotation_type is AnnotationType.CONTENT_UPDATED
    assert entries["u-growth"].annotation_type is AnnotationType.GROWTH_ACTION
    new = entries["u-new"]
    assert new.description == "Write the page for “heat pumps”"
    assert new.page_url is None and new.date == date(2026, 10, 14) == new.completed_at
    assert entries["u-refresh"].page_url == "/old"
    assert entries["u-growth"].success_metric == "Average position on the term"


def test_shipping_twice_updates_the_entry_instead_of_adding_a_second(
    client, db: Session, client_a, admin_user
):
    _record(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    _ship(client, headers, "u-new", "2026-10-14")
    _ship(client, headers, "u-new", "2026-10-16")

    entries = _entries(db, client_a)
    assert len(entries) == 1 and entries["u-new"].date == date(2026, 10, 16)


def test_clearing_the_shipped_date_removes_only_that_entry(
    client, db: Session, client_a, admin_user
):
    _record(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    db.add(
        Annotation(
            client_id=client_a.id, date=date(2026, 10, 1), completed_at=None,
            annotation_type=AnnotationType.MANUAL_NOTE, description="Typed by hand",
        )
    )
    db.commit()
    _ship(client, headers, "u-new", "2026-10-14")
    _ship(client, headers, "u-new", None)

    db.expire_all()
    rows = db.query(Annotation).filter(Annotation.client_id == client_a.id).all()
    assert [r.description for r in rows] == ["Typed by hand"]


def test_a_note_added_to_the_entry_survives_shipping_again(
    client, db: Session, client_a, admin_user
):
    _record(db, client_a)
    headers = client_header(client_a.id, admin_user.email)
    _ship(client, headers, "u-new", "2026-10-14")
    entry = _entries(db, client_a)["u-new"]
    entry.notes = "Client approved the draft on the 12th"
    db.commit()

    _ship(client, headers, "u-new", "2026-10-15")
    assert _entries(db, client_a)["u-new"].notes == "Client approved the draft on the 12th"
