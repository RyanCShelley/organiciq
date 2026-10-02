"""Per-URL backlink counts from SE Ranking.

Three rules need to know whether a page has link equity — whether a 404 is
worth reclaiming, which donor can lend authority, whether a page with no
traffic is still worth checking — and nothing stored it.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from app.ingestion.seranking import pipeline_backlinks
from app.ingestion.seranking.pipeline_backlinks import collapse_rows
from app.models.job import SyncJob, SyncJobStatus, ValidationStatus
from app.models.seranking import FactSerBacklinkPage


def test_the_scheme_variants_of_one_page_are_merged():
    """SE Ranking reports these separately: on smamarketing.com, 39 and 37
    referring domains for the same homepage. Stored as-is they double count,
    and read back by normalized URL only one would ever be found."""
    rows = [
        {
            "url": "http://example.com/",
            "backlinks": 72,
            "refdomains": 39,
            "dofollow_backlinks": 72,
            "nofollow_backlinks": 0,
            "first_seen": "2026-09-07",
            "last_visited": "2026-09-26",
        },
        {
            "url": "https://example.com/",
            "backlinks": 274,
            "refdomains": 37,
            "dofollow_backlinks": 233,
            "nofollow_backlinks": 41,
            "first_seen": "2025-03-28",
            "last_visited": "2026-10-02",
        },
    ]

    merged = collapse_rows(rows)

    assert list(merged) == ["https://example.com/"]
    row = merged["https://example.com/"]
    assert row["backlinks"] == 346
    assert row["refdomains"] == 76
    # The earliest sighting wins: that is when the page was first linked,
    # whichever scheme carried it.
    assert row["first_seen"] == date(2025, 3, 28)
    # And the latest visit, because that is the freshest confirmation.
    assert row["last_visited"] == date(2026, 10, 2)


def test_www_and_trailing_slashes_collapse_too():
    rows = [
        {"url": "https://www.example.com/guide/", "refdomains": 2, "backlinks": 2},
        {"url": "https://example.com/guide", "refdomains": 3, "backlinks": 5},
    ]

    merged = collapse_rows(rows)

    assert list(merged) == ["https://example.com/guide"]
    assert merged["https://example.com/guide"]["refdomains"] == 5


def test_query_strings_are_dropped_so_tracking_urls_do_not_split_a_page():
    """The live data carries rows like /?pg=...&hsic= — the same page."""
    rows = [
        {"url": "https://example.com/", "refdomains": 10, "backlinks": 20},
        {"url": "https://example.com/?pg=abc&ecid=&hsic=", "refdomains": 1, "backlinks": 1},
    ]

    merged = collapse_rows(rows)

    assert list(merged) == ["https://example.com/"]
    assert merged["https://example.com/"]["refdomains"] == 11


def test_a_missing_first_seen_does_not_erase_a_known_one():
    rows = [
        {"url": "https://example.com/a", "refdomains": 1, "first_seen": "2026-01-01"},
        {"url": "http://example.com/a", "refdomains": 1, "first_seen": None},
    ]

    merged = collapse_rows(rows)

    assert merged["https://example.com/a"]["first_seen"] == date(2026, 1, 1)


def test_rows_without_a_url_are_dropped():
    assert collapse_rows([{"url": "", "refdomains": 5}, {"refdomains": 3}]) == {}


def test_junk_counts_do_not_crash_the_merge():
    rows = [{"url": "https://example.com/a", "refdomains": None, "backlinks": "x"}]

    merged = collapse_rows(rows)

    assert merged["https://example.com/a"]["refdomains"] == 0
    assert merged["https://example.com/a"]["backlinks"] == 0


# --- The rule it exists for -------------------------------------------------


def _backlink_page(db, client_id, url, *, refdomains, first_seen):
    from uuid import uuid4

    from app.models.seranking import FactSerBacklinkPage

    db.add(
        FactSerBacklinkPage(
            id=uuid4(),
            client_id=client_id,
            normalized_url=url,
            raw_url=url,
            backlinks=refdomains * 2,
            refdomains=refdomains,
            dofollow_backlinks=refdomains * 2,
            nofollow_backlinks=0,
            first_seen=first_seen,
            last_visited=date.today(),
            snapshot_date=date.today(),
        )
    )


def _site():
    from app.services.decision_impact import SiteBusinessContext

    return SiteBusinessContext(
        site_lead_rate_pct=2.0,
        period_sessions=5000.0,
        period_leads=40,
        period_lead_goal=50,
        p90_page_sessions=400.0,
    )


def _demand(url, position, impressions=800.0):
    from app.services.lever_engine import PageDemand

    return PageDemand(
        normalized_url=url,
        impressions=impressions,
        clicks=10.0,
        average_position=position,
        ctr_percent=1.2,
    )


def test_a_page_that_earned_links_and_still_does_not_rank_is_flagged(db, client_a):
    """Fresh authority that is not being converted. Cheaper to fix than to earn
    the links again."""
    from datetime import timedelta

    from app.services.lever_engine import _pr_push_findings

    url = "https://example.com/guides/metal-roofing"
    end = date.today()
    _backlink_page(db, client_a.id, url, refdomains=4, first_seen=end - timedelta(days=10))
    db.commit()

    findings = _pr_push_findings(
        db, client_a, [_demand(url, 28.0)], period=(end - timedelta(days=29), end), site=_site()
    )

    assert len(findings) == 1
    assert findings[0].evidence_json["refdomains"] == 4
    assert "fresh authority" in findings[0].recommended_action


def test_links_that_did_their_job_are_not_reported(db, client_a):
    """The win shows up in the traffic; saying "this worked" is the report's job."""
    from datetime import timedelta

    from app.services.lever_engine import _pr_push_findings

    url = "https://example.com/guides/metal-roofing"
    end = date.today()
    _backlink_page(db, client_a.id, url, refdomains=4, first_seen=end - timedelta(days=10))
    db.commit()

    findings = _pr_push_findings(
        db, client_a, [_demand(url, 4.0)], period=(end - timedelta(days=29), end), site=_site()
    )

    assert findings == []


def test_a_single_link_is_not_a_push(db, client_a):
    from datetime import timedelta

    from app.services.lever_engine import _pr_push_findings

    url = "https://example.com/blog/post"
    end = date.today()
    _backlink_page(db, client_a.id, url, refdomains=1, first_seen=end - timedelta(days=5))
    db.commit()

    assert (
        _pr_push_findings(
            db, client_a, [_demand(url, 30.0)], period=(end - timedelta(days=29), end), site=_site()
        )
        == []
    )


def test_old_links_are_not_a_recent_push(db, client_a):
    """A link from two years ago is the status quo, not an event."""
    from datetime import timedelta

    from app.services.lever_engine import _pr_push_findings

    url = "https://example.com/blog/post"
    end = date.today()
    _backlink_page(db, client_a.id, url, refdomains=9, first_seen=end - timedelta(days=700))
    db.commit()

    assert (
        _pr_push_findings(
            db, client_a, [_demand(url, 30.0)], period=(end - timedelta(days=29), end), site=_site()
        )
        == []
    )


def test_a_linked_page_with_no_search_data_at_all_is_still_flagged(db, client_a):
    """Links arrived and the page draws nothing — the clearest version of this."""
    from datetime import timedelta

    from app.services.lever_engine import _pr_push_findings

    url = "https://example.com/new-campaign"
    end = date.today()
    _backlink_page(db, client_a.id, url, refdomains=6, first_seen=end - timedelta(days=3))
    db.commit()

    findings = _pr_push_findings(
        db, client_a, [], period=(end - timedelta(days=29), end), site=_site()
    )

    assert len(findings) == 1
    assert "drawing no search traffic" in findings[0].diagnosis


# ── The job itself ──
# Everything above tests `collapse_rows` and the rules that read the rows.
# Nothing ran the job, so three bugs in its success path shipped: a status
# enum member that does not exist, a write to an unmapped column, and no
# `completed_at`. A blanket `except Exception` turned the first into a job
# marked failed with an AttributeError in `error_message` rather than a crash
# anyone would notice. These run it.


def _backlinks_job(db, client_id):
    job = SyncJob(
        id=uuid4(),
        client_id=client_id,
        source="se_ranking_backlinks",
        start_date=date(2026, 10, 2),
        end_date=date(2026, 10, 2),
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()
    return job


def test_a_finished_job_is_marked_successful(db, client_a, monkeypatch):
    monkeypatch.setattr(
        pipeline_backlinks, "get_settings", lambda: SimpleNamespace(se_ranking_api_key="k")
    )
    monkeypatch.setattr(
        pipeline_backlinks,
        "list_backlink_pages",
        lambda *args, **kwargs: [
            {
                "url": "https://example.com/pricing",
                "backlinks": 12,
                "refdomains": 4,
                "dofollow_backlinks": 9,
                "nofollow_backlinks": 3,
                "first_seen": "2026-09-01",
                "last_visited": "2026-10-01",
            },
            {
                "url": "http://www.example.com/pricing/",
                "backlinks": 3,
                "refdomains": 1,
                "dofollow_backlinks": 3,
                "nofollow_backlinks": 0,
                "first_seen": "2026-08-15",
                "last_visited": "2026-10-01",
            },
        ],
    )

    job = pipeline_backlinks.run_seranking_backlinks_job(db, _backlinks_job(db, client_a.id))

    assert job.status is SyncJobStatus.SUCCESSFUL
    assert job.validation_status is ValidationStatus.PASSED
    assert job.completed_at is not None
    assert job.records_fetched == 2
    # One page, not two: the scheme and www variants are the same page.
    assert job.records_written == 1
    # A success summary in error_message reads as a failure in the UI.
    assert job.error_message is None

    rows = db.query(FactSerBacklinkPage).filter(
        FactSerBacklinkPage.client_id == client_a.id
    ).all()
    assert len(rows) == 1
    assert rows[0].refdomains == 5
    assert rows[0].first_seen == date(2026, 8, 15)


def test_a_rerun_keeps_the_date_a_link_first_appeared(db, client_a, monkeypatch):
    """first_seen is what makes a PR push an event rather than a number."""
    monkeypatch.setattr(
        pipeline_backlinks, "get_settings", lambda: SimpleNamespace(se_ranking_api_key="k")
    )
    rows = [
        {
            "url": "https://example.com/pricing",
            "backlinks": 12,
            "refdomains": 4,
            "first_seen": "2026-09-01",
            "last_visited": "2026-10-01",
        }
    ]
    monkeypatch.setattr(pipeline_backlinks, "list_backlink_pages", lambda *a, **k: rows)
    pipeline_backlinks.run_seranking_backlinks_job(db, _backlinks_job(db, client_a.id))

    rows[0]["first_seen"] = "2026-10-02"
    rows[0]["refdomains"] = 6
    pipeline_backlinks.run_seranking_backlinks_job(db, _backlinks_job(db, client_a.id))

    stored = db.query(FactSerBacklinkPage).filter(
        FactSerBacklinkPage.client_id == client_a.id
    ).one()
    assert stored.refdomains == 6
    assert stored.first_seen == date(2026, 9, 1)


def test_a_failed_fetch_records_why(db, client_a, monkeypatch):
    monkeypatch.setattr(
        pipeline_backlinks, "get_settings", lambda: SimpleNamespace(se_ranking_api_key="k")
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("SE Ranking said no")

    monkeypatch.setattr(pipeline_backlinks, "list_backlink_pages", _boom)

    job = pipeline_backlinks.run_seranking_backlinks_job(db, _backlinks_job(db, client_a.id))

    assert job.status is SyncJobStatus.FAILED
    assert job.validation_status is ValidationStatus.FAILED
    assert job.completed_at is not None
    assert "SE Ranking said no" in job.error_message
