"""Resetting one client: what is cleared, what stays, and that nothing else is touched."""

from __future__ import annotations

from datetime import date

import pytest

from app import reset_client_data as rc
from app.models.annotation import Annotation, AnnotationType
from app.models.client_bing_site import ClientBingSite
from app.models.config import Topic
from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob
from app.models.watchlist import WatchlistBucket, WatchlistKeyword


def gsc(db, client, query="q"):
    db.add(FactGscQueryPage(client_id=client.id, date=date(2026, 9, 1), query=query, raw_url="https://x.example/", normalized_url="https://x.example/",
                            country="usa", device="DESKTOP", impressions=10, clicks=1, ctr=0, average_position=5))


def fill(db, client):
    gsc(db, client)
    db.add(EngineTask(client_id=client.id, month="2026-10", kind="growth_action", rule_id="GA", search="s", page_url="https://x.example/",
                      title="t", confirmed_by="a@b.co"))
    b = WatchlistBucket(client_id=client.id, name="B", name_key="b", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client.id, bucket_id=b.id, keyword="k", keyword_key="k"))
    topic = Topic(client_id=client.id, topic_name="T")
    db.add(topic)
    db.flush()
    db.add(Annotation(client_id=client.id, topic_id=topic.id, date=date(2026, 9, 1), annotation_type=AnnotationType.WEBSITE_CHANGE,
                      description="Site migrated", baseline_metrics_json={}))
    db.add(ClientBingSite(client_id=client.id, site_url="https://x.example/", status="connected"))
    db.commit()


def test_the_plan_counts_what_would_be_cleared_and_what_is_kept(db, client_a):
    fill(db, client_a)
    p = rc.plan(db, client_a)
    assert p["clear_synced"]["facts_gsc_query_pages"] == 1
    assert p["clear_setup"]["engine_tasks"] == 1 and p["clear_setup"]["watchlist_keywords"] == 1 and p["clear_setup"]["topics"] == 1
    assert p["kept"]["annotations"] == 1 and p["kept"]["client_bing_sites"] == 1 and p["kept"]["integrations"] >= 1


def test_a_dry_run_deletes_nothing(db, client_a):
    fill(db, client_a)
    rc.plan(db, client_a)
    assert rc.count(db, "facts_gsc_query_pages", client_a.id) == 1


def test_applying_clears_synced_and_set_up_data_and_keeps_the_rest(db, client_a):
    fill(db, client_a)
    before_integrations = db.query(Integration).filter(Integration.client_id == client_a.id).count()
    deleted = rc.apply(db, client_a)
    db.commit()
    assert deleted["facts_gsc_query_pages"] == 1 and deleted["engine_tasks"] == 1 and deleted["topics"] == 1
    after = rc.plan(db, client_a)
    assert sum(after["clear_synced"].values()) == 0 and sum(after["clear_setup"].values()) == 0
    # Kept: the connection, the Bing site, and the note, whose link to the deleted topic is gone.
    assert db.query(Integration).filter(Integration.client_id == client_a.id).count() == before_integrations
    assert after["kept"]["client_bing_sites"] == 1
    note = db.query(Annotation).filter(Annotation.client_id == client_a.id).one()
    assert note.description == "Site migrated" and note.topic_id is None and note.decision_id is None


def test_another_clients_data_is_never_touched(db, client_a, client_b):
    fill(db, client_a)
    fill(db, client_b)
    rc.apply(db, client_a)
    db.commit()
    assert rc.count(db, "facts_gsc_query_pages", client_b.id) == 1
    assert rc.count(db, "engine_tasks", client_b.id) == 1
    assert rc.count(db, "watchlist_keywords", client_b.id) == 1
    assert db.query(Topic).filter(Topic.client_id == client_b.id).count() == 1
    assert db.query(Annotation).filter(Annotation.client_id == client_b.id).one().topic_id is not None


def test_a_table_that_holds_client_data_but_is_not_classified_stops_the_run(db, client_a, monkeypatch):
    monkeypatch.setattr(rc, "SETUP", tuple(t for t in rc.SETUP if t != "engine_tasks"))
    with pytest.raises(rc.UnclassifiedTable, match="engine_tasks"):
        rc.plan(db, client_a)
    with pytest.raises(rc.UnclassifiedTable):
        rc.apply(db, client_a)


def test_the_backfill_queues_one_job_per_connected_source_with_long_windows(db, client_a):
    for row in db.query(Integration).filter(Integration.client_id == client_a.id):
        row.external_property_id = f"id-{row.provider.value}"
    client_a.domain = "example.com"
    db.commit()
    today = date(2026, 11, 2)
    queued = rc.enqueue_backfill(db, client_a, today=today)
    assert "ga4" in queued and "gsc_pages" in queued and "gsc_queries" in queued and "site_crawl" in queued
    jobs = {j.source: j for j in db.query(SyncJob).filter(SyncJob.client_id == client_a.id)}
    assert (jobs["ga4"].end_date - jobs["ga4"].start_date).days >= 700
    assert (jobs["gsc_queries"].end_date - jobs["gsc_queries"].start_date).days >= 350
    # Run again: a source that already has a job waiting is not queued twice.
    assert rc.enqueue_backfill(db, client_a, today=today) == []
