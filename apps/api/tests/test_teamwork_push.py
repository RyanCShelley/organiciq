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


# ── Choosing a tasklist ─────────────────────────────────────────────────────


def test_tasklists_carry_the_project_they_belong_to():
    """"Content" means nothing on its own when nine clients each have one.

    v3 returns related records in a sidecar `included` object keyed by id
    rather than nested in each row, so the project name has to be looked up.
    """
    found = teamwork.parse_tasklists(
        {
            "tasklists": [
                {"id": 11, "name": "Content", "projectId": 7},
                {"id": 12, "name": "Content", "projectId": 8},
            ],
            "included": {
                "projects": {"7": {"name": "SMA Marketing"}, "8": {"name": "ACCTek"}}
            },
        }
    )
    assert [(t.id, t.project_name) for t in found] == [
        ("11", "SMA Marketing"),
        ("12", "ACCTek"),
    ]


def test_a_tasklist_with_no_project_still_lists():
    found = teamwork.parse_tasklists({"tasklists": [{"id": 11, "name": "Loose"}]})
    assert found[0].project_name is None
    assert found[0].name == "Loose"


def test_listing_pages_until_teamwork_runs_out():
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages.append(page)
        size = teamwork.TASKLIST_PAGE_SIZE
        rows = (
            [{"id": i, "name": f"L{i}", "projectId": 1} for i in range(size)]
            if page == 1
            else [{"id": 9000, "name": "Last", "projectId": 1}]
        )
        return httpx.Response(200, json={"tasklists": rows})

    found = teamwork.list_tasklists(
        config=teamwork.TeamworkConfig(site="acme", token="t"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert pages == [1, 2]
    assert len(found) == teamwork.TASKLIST_PAGE_SIZE + 1


def test_listing_says_where_the_token_comes_from_when_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized")

    with pytest.raises(teamwork.TeamworkError, match="API & Mobile"):
        teamwork.list_tasklists(
            config=teamwork.TeamworkConfig(site="acme", token="t"),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )


def test_the_endpoint_reports_a_failure_rather_than_erroring(
    client, client_a, admin_user, monkeypatch
):
    """The field falls back to the id box, so it needs the reason, not a 500."""

    def explode(**kwargs):
        raise teamwork.TeamworkError("Teamwork rejected the credentials.")

    monkeypatch.setattr(
        teamwork, "load_config", lambda: teamwork.TeamworkConfig(site="a", token="t")
    )
    monkeypatch.setattr(teamwork, "list_tasklists", explode)
    response = client.get(
        "/decisions/teamwork/tasklists",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "rejected the credentials" in response.json()["error"]


# ── Who the task lands on ───────────────────────────────────────────────────


def test_people_are_matched_on_email_whatever_the_case():
    people = teamwork.parse_people(
        {
            "people": [
                {"id": 5, "email": "Ryan@SMAMarketing.net", "firstName": "Ryan",
                 "lastName": "Shelley"},
            ]
        }
    )
    assert people[0].name == "Ryan Shelley"
    assert teamwork.person_id_for("ryan@smamarketing.net", people) == "5"
    assert teamwork.person_id_for("RYAN@smamarketing.NET", people) == "5"
    # Somebody with no Teamwork account is not a match, and not an error.
    assert teamwork.person_id_for("new.starter@smamarketing.net", people) is None
    assert teamwork.person_id_for(None, people) is None


def test_a_person_with_no_email_is_skipped():
    # Nothing can be matched on, so listing them would offer a choice that
    # cannot be acted on.
    assert teamwork.parse_people({"people": [{"id": 9, "firstName": "Ghost"}]}) == []


def test_the_task_carries_the_assignee(
    client, db: Session, client_a: Client, admin_user, monkeypatch
):
    """Whoever holds the slot here should hold the task there."""
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
                        "action_uid": uid, "slot": 1, "id": "V-1",
                        "title": "Put the term in the title", "target_url": "/a",
                        "why": "w", "done_when": "d", "metric": "Term position",
                        "check_on": "2026-11-07", "effort_min": 30,
                    }
                ],
                "incidents": [],
            },
        )
    )
    client_a.teamwork_tasklist_id = "99"
    db.commit()

    monkeypatch.setattr(
        teamwork, "load_config", lambda: teamwork.TeamworkConfig(site="acme", token="t")
    )
    monkeypatch.setattr(
        teamwork,
        "list_people",
        lambda: [teamwork.Person(id="5", email=admin_user.email.lower(), name="Admin")],
    )
    seen: dict = {}

    def fake_create(**kwargs):
        seen.update(kwargs)
        return {"id": "4821", "url": "https://acme.teamwork.com/app/tasks/4821"}

    monkeypatch.setattr(teamwork, "create_task", fake_create)

    headers = client_header(client_a.id, admin_user.email)
    client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/assign",
        headers=headers,
        json={"assignee_user_id": str(admin_user.id), "due": None},
    )
    assert client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/send", headers=headers
    ).status_code == 200
    assert seen["assignee_teamwork_id"] == "5"


def test_an_assignee_with_no_teamwork_account_still_sends(
    client, db: Session, client_a: Client, admin_user, monkeypatch
):
    """Unassigned in Teamwork beats not created at all."""
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
                        "action_uid": uid, "slot": 1, "id": "V-1",
                        "title": "t", "target_url": "/a", "why": "w",
                        "done_when": "d", "metric": "Term position",
                        "check_on": "2026-11-07", "effort_min": 30,
                    }
                ],
                "incidents": [],
            },
        )
    )
    client_a.teamwork_tasklist_id = "99"
    db.commit()

    monkeypatch.setattr(
        teamwork, "load_config", lambda: teamwork.TeamworkConfig(site="acme", token="t")
    )
    monkeypatch.setattr(teamwork, "list_people", lambda: [])
    seen: dict = {}
    monkeypatch.setattr(
        teamwork,
        "create_task",
        lambda **kw: (seen.update(kw), {"id": "1", "url": "u"})[1],
    )

    headers = client_header(client_a.id, admin_user.email)
    client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/assign",
        headers=headers,
        json={"assignee_user_id": str(admin_user.id), "due": None},
    )
    assert client.post(
        f"/decisions/records/{MONTH}/slots/{uid}/send", headers=headers
    ).status_code == 200
    assert seen["assignee_teamwork_id"] is None
