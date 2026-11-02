"""Admin: the client list, and deleting a client for good without touching another."""

from __future__ import annotations

from datetime import date

from app.models.annotation import Annotation, AnnotationType
from app.models.client import Client
from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage
from app.models.integration import Integration
from app.models.llm_visibility import ClientLlmPrompt, LlmRun
from app.models.user import UserClient
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from tests.conftest import auth_header


def seed(db, client: Client):
    db.add(FactGscQueryPage(client_id=client.id, date=date(2026, 9, 1), query="q", raw_url="https://x.example/", normalized_url="https://x.example/",
                            country="usa", device="DESKTOP", impressions=5, clicks=1, ctr=0, average_position=4))
    db.add(EngineTask(client_id=client.id, month="2026-10", kind="growth_action", rule_id="GA", search="s", page_url="https://x.example/", title="t", confirmed_by="a@b.co"))
    b = WatchlistBucket(client_id=client.id, name="B", name_key="b", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client.id, bucket_id=b.id, keyword="k", keyword_key="k"))
    db.add(ClientLlmPrompt(client_id=client.id, prompt="Q?", prompt_key="q?", topic_cluster="Niche"))
    db.add(LlmRun(client_id=client.id, status="completed", platforms=["openai"]))
    db.add(Annotation(client_id=client.id, date=date(2026, 9, 1), annotation_type=AnnotationType.WEBSITE_CHANGE, description="note", baseline_metrics_json={}))
    db.commit()


def test_a_team_member_cannot_list_or_delete(client, db, client_a, team_user):
    h = auth_header(team_user.email)
    assert client.get("/v2/admin/clients", headers=h).status_code == 403
    assert client.request("DELETE", f"/v2/admin/clients/{client_a.id}", json={"confirm_name": client_a.client_name}, headers=h).status_code == 403


def test_the_list_shows_what_is_set_up_for_each_client(client, db, client_a, client_b, admin_user):
    seed(db, client_a)
    rows = {r["name"]: r for r in client.get("/v2/admin/clients", headers=auth_header(admin_user.email)).json()}
    a, b = rows[client_a.client_name], rows[client_b.client_name]
    assert a["watchlist_keywords"] == 1 and a["integrations"] >= 1 and a["id"] == str(client_a.id)
    assert b["watchlist_keywords"] == 0 and b["has_baseline"] is False and b["gsc_through"] is None


def test_the_preview_says_what_would_go(client, db, client_a, admin_user):
    seed(db, client_a)
    p = client.get(f"/v2/admin/clients/{client_a.id}/delete-preview", headers=auth_header(admin_user.email)).json()
    assert p["name"] == client_a.client_name and p["synced_rows"] == 1 and p["setup_rows"] >= 4
    assert p["setup"]["engine_tasks"] == 1 and p["annotations"] == 1 and p["integrations"] >= 1


def test_deleting_needs_the_exact_name_and_leaves_the_client_in_place_otherwise(client, db, client_a, admin_user):
    h = auth_header(admin_user.email)
    wrong = client.request("DELETE", f"/v2/admin/clients/{client_a.id}", json={"confirm_name": "nope"}, headers=h)
    assert wrong.status_code == 400 and db.get(Client, client_a.id) is not None


def test_deleting_removes_the_client_and_all_of_its_data_and_no_one_elses(client, db, client_a, client_b, admin_user, team_user):
    seed(db, client_a)
    seed(db, client_b)
    a_id, a_name, b_id = client_a.id, client_a.client_name, client_b.id
    out = client.request("DELETE", f"/v2/admin/clients/{a_id}", json={"confirm_name": a_name}, headers=auth_header(admin_user.email))
    assert out.status_code == 200 and out.json()["deleted"] == a_name and out.json()["rows"] > 5
    db.expire_all()
    assert db.get(Client, a_id) is None
    for model in (FactGscQueryPage, EngineTask, WatchlistKeyword, ClientLlmPrompt, LlmRun, Annotation, Integration, UserClient):
        assert db.query(model).filter(model.client_id == a_id).count() == 0, model.__name__
    # The other client is whole.
    assert db.get(Client, b_id) is not None
    for model in (FactGscQueryPage, EngineTask, WatchlistKeyword, ClientLlmPrompt, LlmRun, Annotation):
        assert db.query(model).filter(model.client_id == b_id).count() == 1, model.__name__


def test_a_client_that_does_not_exist_is_a_404(client, admin_user):
    import uuid

    h = auth_header(admin_user.email)
    assert client.get(f"/v2/admin/clients/{uuid.uuid4()}/delete-preview", headers=h).status_code == 404
    assert client.request("DELETE", f"/v2/admin/clients/{uuid.uuid4()}", json={"confirm_name": "x"}, headers=h).status_code == 404


def test_the_original_delete_route_now_works_for_a_client_with_v2_data(client, db, client_a, admin_user):
    seed(db, client_a)
    a_id = client_a.id
    assert client.delete(f"/clients/{a_id}", headers=auth_header(admin_user.email)).status_code == 204
    db.expire_all()
    assert db.get(Client, a_id) is None
