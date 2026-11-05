"""A task goes to Teamwork with a subtask for each piece of the work; content items carry a prompt for the client's Claude project."""

from __future__ import annotations

from datetime import date

import pytest

from app.integrations import teamwork
from app.models.engine_task import EngineTask
from app.models.schema_tools import ContentItem
from app.services import content_calendar, content_prompts, teamwork_subtasks


def _item(db, client, **kw) -> ContentItem:
    fields = dict(client_id=client.id, kind="new_page", title="Winter lawn care", target="winter lawn care tips", source_area="manual",
                  status="planned", due=date(2026, 12, 1), notes="Sections\n- Fertilizing\nQuestions to answer\n- When to stop mowing", created_by="a@b.c")
    fields.update(kw)
    row = ContentItem(**fields)
    db.add(row)
    db.commit()
    return row


def test_a_new_page_has_a_subtask_for_title_headings_body_and_publishing(db, client_a):
    subs = content_prompts.subtasks(_item(db, client_a), client_a)
    assert [s.key for s in subs] == ["title", "headings", "body", "publish"]
    title = subs[0].description
    assert f"Paste this into the {client_a.client_name} Claude project." in title
    assert "winter lawn care tips" in title and "When to stop mowing" in title  # the brief travels with the prompt
    assert "60 characters" in title and "155 characters" in title
    assert "H1" in subs[1].name and "H2" in subs[1].description
    assert "[paste the outline" in subs[2].description


def test_a_refresh_asks_to_review_before_rewriting(db, client_a):
    subs = content_prompts.subtasks(_item(db, client_a, kind="refresh", target="https://x.test/page", title="Lawn page"), client_a)
    assert [s.name for s in subs] == ["Title and meta description", "Headings (H1 to H3)", "Update the content", "Republish"]
    assert "https://x.test/page" in subs[0].description and "[paste them]" in subs[0].description


def test_a_growth_action_makes_a_subtask_of_each_part():
    subs = teamwork_subtasks.from_steps(["# Fix the title", "Shorten to 60 characters", "Lead with the subject", "# Add a FAQ", "Write three answers"], growth=True)
    assert [s.name for s in subs] == ["Fix the title", "Add a FAQ"]
    assert "[ ] Shorten to 60 characters" in subs[0].description


def test_any_other_task_makes_a_subtask_of_each_step():
    subs = teamwork_subtasks.from_steps(["Open the page", "Add the link"], growth=False)
    assert [s.name for s in subs] == ["Open the page", "Add the link"]


@pytest.mark.real_subtasks
def test_a_send_that_stopped_halfway_finishes_without_repeating(db, client_a, monkeypatch):
    item = _item(db, client_a)
    calls: list[str] = []
    fail_on = {"headings"}

    def fake(**kw):
        key = {"Title and meta description": "title", "Headings (H1 to H3)": "headings", "Write the page": "body", "Publish and link": "publish"}[kw["name"]]
        if key in fail_on:
            raise teamwork.TeamworkError("down")
        calls.append(key)
        return {"id": f"id-{key}", "url": ""}

    monkeypatch.setattr(teamwork, "create_subtask", fake)
    subs = content_prompts.subtasks(item, client_a)
    item.teamwork_task_id = "T1"
    db.commit()
    assert teamwork_subtasks.send(db, item, "T1", subs, due=None, assignee=None) == 3  # stopped at the second
    assert calls == ["title"]
    fail_on.clear()
    assert teamwork_subtasks.send(db, item, "T1", subs, due=None, assignee=None) == 0
    assert calls == ["title", "headings", "body", "publish"]  # the first was not made twice
    assert len(item.teamwork_subtasks) == 4


@pytest.mark.real_subtasks
def test_the_subtask_is_posted_under_its_parent():
    seen = {}

    class R:
        status_code = 200
        text = ""

        def json(self):
            return {"task": {"id": 9}}

    class C:
        def post(self, url, json, headers):
            seen["url"], seen["json"] = url, json
            return R()

    cfg = teamwork.TeamworkConfig(site="acme", token="t")
    made = teamwork.create_subtask(parent_task_id="77", name="Headings", description="d", due="2026-12-01", config=cfg, client=C())
    assert seen["url"].endswith("/projects/api/v3/tasks/77/subtasks.json")
    assert seen["json"]["task"]["name"] == "Headings" and seen["json"]["task"]["dueAt"] == "2026-12-01"
    assert made["id"] == "9"
