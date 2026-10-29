"""The report of mapped pages the engine could not read."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.decision import MonthlyRecord
from app.services import engine_input_coverage
from tests.test_target_page_lookup import SECTIONS, _row


def _client_row(report: dict, client: Client) -> dict:
    return next(row for row in report["clients"] if row["client_id"] == str(client.id))


def test_each_kind_of_unreadable_target_is_named(db: Session, client_a: Client):
    db.add(_row(client_a, "https://a.example/ok", status_code=200, sections=SECTIONS))
    db.add(_row(client_a, "http://a.example/typed", status_code=301, redirect_url="https://a.example/typed", sections=None))
    db.add(_row(client_a, "https://a.example/typed", status_code=200, sections=SECTIONS))
    db.add(_row(client_a, "http://a.example/dead", status_code=301, redirect_url="https://a.example/dead", sections=None))
    db.add(_row(client_a, "https://a.example/old", status_code=200, sections=None))
    for index, url in enumerate(
        (
            "https://a.example/ok",
            "http://a.example/typed",
            "http://a.example/dead",
            "https://a.example/old",
            "https://a.example/missing",
        )
    ):
        db.add(_target_for(client_a, f"term {index}", url))
    db.commit()

    row = _client_row(engine_input_coverage.report(db), client_a)
    assert row["targets"] == 5
    assert row["ok"] == 1
    assert row["redirect_followed"] == 1
    assert row["unreadable"] == 1
    assert row["headings_not_captured"] == 1
    assert row["not_in_crawl"] == 1
    assert {p["status"] for p in row["problems"]} == {
        "redirect_followed",
        "unreadable",
        "headings_not_captured",
        "not_in_crawl",
    }


def test_a_saved_action_on_a_flagged_page_is_listed(db: Session, client_a: Client):
    db.add(_row(client_a, "https://a.example/old", status_code=200, sections=None))
    db.add(_target_for(client_a, "pool leak detection", "https://a.example/old"))
    db.add(
        MonthlyRecord(
            client_id=client_a.id,
            month="2026-09",
            constraint_name="visibility",
            held_since="2026-09",
            confidence="medium",
            record={
                "actions": [
                    {"id": "V-1", "title": "Put it in the title", "target_url": "https://a.example/old"},
                    {"id": "V-6", "title": "Re-home", "target_url": "https://a.example/old"},
                ]
            },
        )
    )
    db.commit()

    row = _client_row(engine_input_coverage.report(db), client_a)
    assert [a["id"] for a in row["affected_actions"]] == ["V-1"]


def test_the_endpoint_is_admin_only_and_read_only(client, client_a, admin_user):
    from tests.conftest import client_header

    response = client.get(
        "/admin/engine-input-coverage", headers=client_header(client_a.id, admin_user.email)
    )
    assert response.status_code == 200
    assert "totals" in response.json()


def _target_for(client: Client, keyword: str, url: str):
    from app.models.decision import KeywordTarget

    return KeywordTarget(
        client_id=client.id, keyword=keyword, target_url=url, source="confirmed", term_role="primary"
    )
