"""Pushing a slot into Teamwork.

The task has to stand on its own: read in Teamwork three weeks later there is
no page around it, so the page, the reason, the finish line and the metric all
travel with it. And a second press must link the task that exists rather than
creating a twin — the failure mode of every "create" button that forgets what
it created.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.orm import Session

from app.integrations import teamwork
from app.models.client import Client
from app.models.decision import EngineAction, MonthlyRecord
from tests.conftest import client_header

MONTH = "2026-10"


def test_base_url_takes_a_bare_site_name():
    config = teamwork.TeamworkConfig(site="smamarketing", token="t")
    assert config.base_url == "https://smamarketing.teamwork.com"
    assert teamwork.TeamworkConfig(site="acme.teamwork.com", token="t").base_url == (
        "https://acme.teamwork.com"
    )


def test_the_task_carries_what_the_doer_needs():
    name, description = teamwork.task_body(
        title="Put “seo agency” in the title",
        why="The page never says the phrase.",
        done_when="It appears in the title and one H2.",
        target_url="https://example.com/seo",
        metric="Term position",
        check_on="2026-11-07",
        effort_min=30,
        record_url="https://app/sma/decision-engine?run=2026-10",
    )
    assert name == "Put “seo agency” in the title"
    for expected in (
        "https://example.com/seo",
        "The page never says the phrase.",
        "It appears in the title and one H2.",
        "Measured on Term position, checked 2026-11-07",
        "Estimated 30 minutes",
        "run=2026-10",
    ):
        assert expected in description


def test_create_task_without_a_tasklist_names_the_gap():
    config = teamwork.TeamworkConfig(site="acme", token="t")
    with pytest.raises(teamwork.TeamworkError, match="no Teamwork tasklist"):
        teamwork.create_task(tasklist_id="", name="x", description="", config=config)


def test_create_task_posts_the_task_and_returns_its_url():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = request.read().decode()
        return httpx.Response(201, json={"task": {"id": 4821}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    created = teamwork.create_task(
        tasklist_id="99",
        name="Do the thing",
        description="Here is how.",
        due="2026-10-20",
        config=teamwork.TeamworkConfig(site="acme", token="tok"),
        client=http,
    )

    assert created == {"id": "4821", "url": "https://acme.teamwork.com/app/tasks/4821"}
    assert seen["url"] == "https://acme.teamwork.com/projects/api/v3/tasklists/99/tasks.json"
    assert seen["auth"].startswith("Basic ")
    # v3's `dueAt` is `format: date` — an ISO date. The YYYYMMDD this used to
    # send is v1's shape, and v3 would have refused it.
    assert '"dueAt":"2026-10-20"' in seen["body"]


def test_teamwork_refusing_is_reported_with_its_own_words():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Tasklist is archived")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(teamwork.TeamworkError, match="Tasklist is archived"):
        teamwork.create_task(
            tasklist_id="99",
            name="x",
            description="",
            config=teamwork.TeamworkConfig(site="acme", token="tok"),
            client=http,
        )


def test_a_second_send_links_the_existing_task(
    client, db: Session, client_a: Client, admin_user, monkeypatch
):
    uid = f"{client_a.slug}-{MONTH}-s1"
    db.add(
        MonthlyRecord(
            client_id=client_a.id,
            month=MONTH,
            run_saved_at=datetime.now(timezone.utc),
            constraint_name="visibility",
            held_since=MONTH,
            confidence="medium",
            record={
                "actions": [
                    {
                        "action_uid": uid,
                        "slot": 1,
                        "id": "V-1",
                        "title": "Put the term in the title",
                        "target_url": "/a",
                        "why": "w",
                        "done_when": "d",
                        "metric": "Term position",
                        "check_on": "2026-11-07",
                        "effort_min": 30,
                    }
                ],
                "incidents": [],
            },
        )
    )
    client_a.teamwork_tasklist_id = "99"
    db.commit()

    calls: list[str] = []

    def fake_create(**kwargs):
        calls.append(kwargs["name"])
        return {"id": "4821", "url": "https://acme.teamwork.com/app/tasks/4821"}

    monkeypatch.setenv("TEAMWORK_SITE", "acme")
    monkeypatch.setenv("TEAMWORK_API_TOKEN", "tok")
    monkeypatch.setattr(teamwork, "create_task", fake_create)

    headers = client_header(client_a.id, admin_user.email)
    first = client.post(f"/decisions/records/{MONTH}/slots/{uid}/send", headers=headers)
    assert first.status_code == 200
    assert first.json()["teamwork_task_id"] == "4821"
    assert first.json()["sent_at"] is not None

    second = client.post(f"/decisions/records/{MONTH}/slots/{uid}/send", headers=headers)
    assert second.status_code == 200
    assert second.json()["teamwork_task_url"] == "https://acme.teamwork.com/app/tasks/4821"
    assert len(calls) == 1, "the second press created a second task"

    rows = db.query(EngineAction).filter(EngineAction.uid == uid).all()
    assert len(rows) == 1
