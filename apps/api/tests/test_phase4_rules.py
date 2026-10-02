"""Phase 4: the new rules that have a data source.

N3 (intent mismatch) is not here. It needs the top five SERP results with a
page-type classification for each, and nothing stores SERP results at all —
the prompt said to skip and report it in that case.

Most of N4 is not here either, for the same reason: no page body is stored,
so "no CTA on the page" cannot be checked; GA4 facts carry no device
dimension, so mobile cannot be compared to desktop; and no Core Web Vitals
are stored, so LCP cannot be read. The one part with data — AI referrals as
their own segment — is tested below.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.crawl import FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage
from app.models.job import DataWatermark, ValidationStatus
from app.models.seranking import FactSerAiTrackerStats, FactSerBacklinkPage
from app.services.lever_engine import active_crawl_source, diagnose
from tests.conftest import seed_required_sources

END = date(2026, 8, 31)
START = END - timedelta(days=29)
PAGE = "https://example.com/guide"


def _watermarks(db, client_id):
    for source in ("ga4", "gsc_pages", "se_ranking_ai"):
        db.add(
            DataWatermark(
                id=uuid4(),
                client_id=client_id,
                source=source,
                fact_through_date=END,
                validation_status=ValidationStatus.PASSED,
            )
        )


def _minimal_site(db, client_a, url=PAGE, impressions=400):
    _watermarks(db, client_a.id)
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=END,
            raw_url=url,
            normalized_url=url,
            country="",
            device="",
            impressions=Decimal(str(impressions)),
            clicks=Decimal("12"),
            ctr=Decimal("0.03"),
            average_position=Decimal("9"),
        )
    )
    db.add(
        ConversionDefinition(
            id=uuid4(),
            client_id=client_a.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            is_primary=True,
            active=True,
        )
    )
    for offset in range(30):
        day = END - timedelta(days=offset)
        db.add(
            FactGa4Traffic(
                id=uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url=url,
                normalized_url=url,
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                sessions=Decimal("40"),
                active_users=Decimal("40"),
                views=Decimal("40"),
            )
        )
        db.add(
            FactGa4Event(
                id=uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url=url,
                normalized_url=url,
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                event_name="generate_lead",
                event_count=2,
            )
        )


def _sov(db, client_id, day, pct):
    db.add(
        FactSerAiTrackerStats(
            id=uuid4(),
            client_id=client_id,
            metric_date=day,
            prompts_count=25,
            mention_presence_pct=Decimal(str(pct)),
        )
    )


# ── N1: AI share of voice falling ──


def _run(db, client_a, thresholds=None):
    db.commit()
    seed_required_sources(db, client_a.id, END)
    if thresholds:
        from app.models.decision import DecisionThreshold

        db.add(
            DecisionThreshold(
                id=uuid4(), client_id=client_a.id, thresholds=thresholds
            )
        )
        db.commit()
    return diagnose(db, client_a, from_date=START, to_date=END)


def test_a_falling_share_of_voice_is_a_finding(db, client_a):
    _minimal_site(db, client_a)
    _sov(db, client_a.id, END - timedelta(days=28), 40.0)
    _sov(db, client_a.id, END, 20.0)

    result = _run(db, client_a)
    sov = [
        row for row in result.findings
        if row.evidence_json.get("audit_signal") == "ai_sov_falling"
    ]
    assert len(sov) == 1
    assert sov[0].evidence_json["relative_drop_pct"] == 50.0


def test_a_steady_share_of_voice_is_not(db, client_a):
    _minimal_site(db, client_a)
    _sov(db, client_a.id, END - timedelta(days=28), 40.0)
    _sov(db, client_a.id, END, 38.0)

    result = _run(db, client_a)
    assert not [
        row for row in result.findings
        if row.evidence_json.get("audit_signal") == "ai_sov_falling"
    ]


def test_a_relative_fall_from_almost_nothing_is_not_a_finding(db, client_a):
    """20% off a 2% share is one prompt changing its mind."""
    _minimal_site(db, client_a)
    _sov(db, client_a.id, END - timedelta(days=28), 2.0)
    _sov(db, client_a.id, END, 1.0)

    result = _run(db, client_a)
    assert not [
        row for row in result.findings
        if row.evidence_json.get("audit_signal") == "ai_sov_falling"
    ]


def test_the_flag_turns_the_rule_off(db, client_a):
    _minimal_site(db, client_a)
    _sov(db, client_a.id, END - timedelta(days=28), 40.0)
    _sov(db, client_a.id, END, 20.0)

    result = _run(db, client_a, {"rule_ai_sov_falling_enabled": 0})
    assert not [
        row for row in result.findings
        if row.evidence_json.get("audit_signal") == "ai_sov_falling"
    ]


# ── N2: link reclamation ──


def _crawled(db, client_id, url, *, status, redirect_url=None, inbound=3):
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(),
            client_id=client_id,
            source=active_crawl_source(),
            snapshot_date=END,
            raw_url=url,
            normalized_url=url,
            indexable=status < 300,
            status_code=status,
            inbound_internal_links=inbound,
            word_count=600,
            in_sitemap=True,
            inbound_editorial_links=1,
            title="T",
            description="D",
            redirect_url=redirect_url,
            redirect_count=1 if redirect_url else 0,
        )
    )


def _linked(db, client_id, url, refdomains):
    db.add(
        FactSerBacklinkPage(
            id=uuid4(),
            client_id=client_id,
            normalized_url=url,
            raw_url=url,
            backlinks=refdomains * 3,
            refdomains=refdomains,
            dofollow_backlinks=refdomains * 2,
            nofollow_backlinks=refdomains,
            first_seen=date(2025, 1, 1),
            last_visited=END,
            snapshot_date=END,
        )
    )


DEAD = "https://example.com/old-study"


def test_a_404_other_sites_link_to_is_worth_reclaiming(db, client_a):
    _minimal_site(db, client_a)
    _crawled(db, client_a.id, DEAD, status=404)
    _linked(db, client_a.id, DEAD, 8)

    result = _run(db, client_a)
    reclaim = [
        row for row in result.findings
        if row.evidence_json.get("audit_signal") == "link_reclamation"
    ]
    assert len(reclaim) == 1
    assert reclaim[0].page_url == DEAD
    assert reclaim[0].evidence_json["refdomains"] == 8


def test_a_404_nobody_links_to_is_housekeeping(db, client_a):
    _minimal_site(db, client_a)
    _crawled(db, client_a.id, DEAD, status=404)

    result = _run(db, client_a)
    assert not [
        row for row in result.findings
        if row.evidence_json.get("audit_signal") == "link_reclamation"
    ]


def test_links_dumped_on_the_homepage_are_reported(db, client_a):
    """The link survives the redirect; what it was about does not."""
    _minimal_site(db, client_a)
    _crawled(db, client_a.id, DEAD, status=301, redirect_url="https://example.com/")
    _linked(db, client_a.id, DEAD, 5)

    result = _run(db, client_a)
    reclaim = [
        row for row in result.findings
        if row.evidence_json.get("audit_signal") == "link_reclamation"
    ]
    assert len(reclaim) == 1
    assert "homepage" in reclaim[0].diagnosis


def test_a_redirect_to_a_relevant_page_is_fine(db, client_a):
    _minimal_site(db, client_a)
    _crawled(
        db, client_a.id, DEAD, status=301, redirect_url="https://example.com/research/study"
    )
    _linked(db, client_a.id, DEAD, 5)

    result = _run(db, client_a)
    assert not [
        row for row in result.findings
        if row.evidence_json.get("audit_signal") == "link_reclamation"
    ]


def test_the_reclamation_flag_turns_the_rule_off(db, client_a):
    _minimal_site(db, client_a)
    _crawled(db, client_a.id, DEAD, status=404)
    _linked(db, client_a.id, DEAD, 8)

    result = _run(db, client_a, {"rule_link_reclamation_enabled": 0})
    assert not [
        row for row in result.findings
        if row.evidence_json.get("audit_signal") == "link_reclamation"
    ]


# ── N4: AI referrals as their own segment ──


def test_ai_referrals_are_reported_on_a_page_finding(db, client_a):
    """AI assistants report no impressions, so the organic numbers on a page
    cannot say whether that surface is earning anything."""
    _minimal_site(db, client_a)
    for offset in range(30):
        day = END - timedelta(days=offset)
        db.add(
            FactGa4Traffic(
                id=uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url=PAGE,
                normalized_url=PAGE,
                session_source="chatgpt.com",
                session_medium="referral",
                channel=OrganicChannel.AI_REFERRAL,
                sessions=Decimal("5"),
                active_users=Decimal("5"),
                views=Decimal("5"),
            )
        )
        db.add(
            FactGa4Event(
                id=uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url=PAGE,
                normalized_url=PAGE,
                session_source="chatgpt.com",
                session_medium="referral",
                channel=OrganicChannel.AI_REFERRAL,
                event_name="generate_lead",
                event_count=1,
            )
        )

    # An orphan finding, so there is a page finding to carry the segment.
    _crawled(db, client_a.id, PAGE, status=200, inbound=0)

    result = _run(db, client_a)
    page_findings = [row for row in result.findings if row.page_url == PAGE]
    assert page_findings
    assert all(
        row.evidence_json.get("ai_referral_sessions") == 150.0 for row in page_findings
    )
    assert all(
        row.evidence_json.get("ai_referral_leads") == 30.0 for row in page_findings
    )
