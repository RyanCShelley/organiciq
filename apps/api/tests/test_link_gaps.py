"""Which page should link to which, rather than how many links are missing.

"This page has fewer than five inbound links" is a symptom. It tells a
strategist something is wrong and leaves them to work out what to do, which on
a four-hundred-page site is most of the job.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink
from app.models.gsc import FactGscQueryPage
from app.services.lever_engine import LINK_GAP_MIN_IMPRESSIONS, _link_gaps

END = date(2026, 8, 31)
START = END - timedelta(days=29)
PERIOD = (START, END)

PILLAR = "https://example.com/guides/metal-roofing"
ORPHAN = "https://example.com/blog/metal-roof-cost"
UNRELATED = "https://example.com/about"


def _rank(db, client_id, url, query, impressions, clicks):
    db.add(
        FactGscQueryPage(
            id=uuid4(),
            client_id=client_id,
            date=END,
            query=query,
            raw_url=url,
            normalized_url=url,
            country="",
            device="",
            impressions=Decimal(impressions),
            clicks=Decimal(clicks),
            ctr=Decimal("0.05"),
            average_position=Decimal("5"),
        )
    )


def _link(db, client_id, from_url, to_url, *, template=False):
    db.add(
        FactCrawlInternalLink(
            id=uuid4(),
            client_id=client_id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=END,
            from_url=from_url,
            to_url=to_url,
            anchor_text="see also",
            is_template=template,
            in_content=not template,
            occurrences=1,
        )
    )


def test_the_stronger_page_on_a_shared_query_is_named(db, client_a):
    _rank(db, client_a.id, PILLAR, "metal roofing cost", 2000, 300)
    _rank(db, client_a.id, ORPHAN, "metal roofing cost", 400, 5)
    db.commit()

    gaps = _link_gaps(db, client_a.id, period=PERIOD, targets={ORPHAN})

    assert ORPHAN in gaps
    assert gaps[ORPHAN].source_url == PILLAR
    assert gaps[ORPHAN].shared_query == "metal roofing cost"
    assert gaps[ORPHAN].source_clicks == 300


def test_the_link_is_never_asked_for_from_the_weaker_page(db, client_a):
    """Pointing it the other way asks the page with nothing to give to give it."""
    _rank(db, client_a.id, PILLAR, "metal roofing cost", 2000, 300)
    _rank(db, client_a.id, ORPHAN, "metal roofing cost", 400, 5)
    db.commit()

    gaps = _link_gaps(db, client_a.id, period=PERIOD, targets={PILLAR})

    assert gaps == {}


def test_an_existing_editorial_link_is_not_a_gap(db, client_a):
    _rank(db, client_a.id, PILLAR, "metal roofing cost", 2000, 300)
    _rank(db, client_a.id, ORPHAN, "metal roofing cost", 400, 5)
    _link(db, client_a.id, PILLAR, ORPHAN)
    db.commit()

    assert _link_gaps(db, client_a.id, period=PERIOD, targets={ORPHAN}) == {}


def test_a_navigation_link_does_not_close_the_gap(db, client_a):
    """The floor counts editorial links, so the gap must too."""
    _rank(db, client_a.id, PILLAR, "metal roofing cost", 2000, 300)
    _rank(db, client_a.id, ORPHAN, "metal roofing cost", 400, 5)
    _link(db, client_a.id, PILLAR, ORPHAN, template=True)
    db.commit()

    gaps = _link_gaps(db, client_a.id, period=PERIOD, targets={ORPHAN})

    assert gaps[ORPHAN].source_url == PILLAR


def test_pages_with_no_shared_query_are_not_paired(db, client_a):
    _rank(db, client_a.id, UNRELATED, "who we are", 3000, 500)
    _rank(db, client_a.id, ORPHAN, "metal roofing cost", 400, 5)
    db.commit()

    assert _link_gaps(db, client_a.id, period=PERIOD, targets={ORPHAN}) == {}


def test_a_thin_query_is_not_evidence_of_a_shared_subject(db, client_a):
    _rank(db, client_a.id, PILLAR, "odd phrase", 10, 5)
    _rank(db, client_a.id, ORPHAN, "odd phrase", 5, 0)
    db.commit()

    assert _link_gaps(db, client_a.id, period=PERIOD, targets={ORPHAN}) == {}
    assert 10 < LINK_GAP_MIN_IMPRESSIONS


def test_a_source_barely_stronger_is_not_worth_the_link(db, client_a):
    """Twice the clicks, or the source has no authority to lend."""
    _rank(db, client_a.id, PILLAR, "metal roofing cost", 2000, 11)
    _rank(db, client_a.id, ORPHAN, "metal roofing cost", 400, 10)
    db.commit()

    assert _link_gaps(db, client_a.id, period=PERIOD, targets={ORPHAN}) == {}


def test_the_strongest_candidate_wins(db, client_a):
    other = "https://example.com/blog/roof-materials"
    _rank(db, client_a.id, PILLAR, "metal roofing cost", 2000, 300)
    _rank(db, client_a.id, other, "metal roofing cost", 900, 80)
    _rank(db, client_a.id, ORPHAN, "metal roofing cost", 400, 5)
    db.commit()

    gaps = _link_gaps(db, client_a.id, period=PERIOD, targets={ORPHAN})

    assert gaps[ORPHAN].source_url == PILLAR


def test_no_period_or_no_targets_does_no_work(db, client_a):
    assert _link_gaps(db, client_a.id, period=None, targets={ORPHAN}) == {}
    assert _link_gaps(db, client_a.id, period=PERIOD, targets=set()) == {}


def test_the_finding_names_the_page_to_link_from(db, client_a):
    """The point of the whole thing: the action is the work, not a diagnosis."""
    from app.models.crawl import FactCrawlPageSnapshot
    from app.services.decision_impact import SiteBusinessContext
    from app.services.lever_engine import LinkGap, PageDemand, _internal_linking_finding

    crawl = FactCrawlPageSnapshot(
        id=uuid4(),
        client_id=client_a.id,
        source=CRAWL_SOURCE_FIRST_PARTY,
        snapshot_date=END,
        raw_url=ORPHAN,
        normalized_url=ORPHAN,
        status_code=200,
        indexable=True,
        word_count=900,
        inbound_internal_links=40,
        inbound_editorial_links=1,
        redirect_count=0,
    )
    page = PageDemand(
        normalized_url=ORPHAN,
        impressions=800.0,
        clicks=10.0,
        average_position=9.0,
        ctr_percent=1.2,
    )
    site = SiteBusinessContext(
        site_lead_rate_pct=2.0,
        period_sessions=5000.0,
        period_leads=100,
        period_lead_goal=120,
        p90_page_sessions=500.0,
    )

    finding = _internal_linking_finding(
        page,
        crawl,
        page_ctx=None,
        site=site,
        link_gap=LinkGap(source_url=PILLAR, shared_query="metal roofing cost", source_clicks=300),
    )

    assert finding is not None
    assert PILLAR in finding.recommended_action
    assert "metal roofing cost" in finding.recommended_action
    assert finding.evidence_json["link_from"] == PILLAR


def test_without_a_candidate_the_finding_still_stands(db, client_a):
    """No page both shares the subject and has authority to lend — say less."""
    from app.models.crawl import FactCrawlPageSnapshot
    from app.services.decision_impact import SiteBusinessContext
    from app.services.lever_engine import PageDemand, _internal_linking_finding

    crawl = FactCrawlPageSnapshot(
        id=uuid4(),
        client_id=client_a.id,
        source=CRAWL_SOURCE_FIRST_PARTY,
        snapshot_date=END,
        raw_url=ORPHAN,
        normalized_url=ORPHAN,
        status_code=200,
        indexable=True,
        word_count=900,
        inbound_internal_links=40,
        inbound_editorial_links=1,
        redirect_count=0,
    )
    finding = _internal_linking_finding(
        PageDemand(
            normalized_url=ORPHAN,
            impressions=800.0,
            clicks=10.0,
            average_position=9.0,
            ctr_percent=1.2,
        ),
        crawl,
        page_ctx=None,
        site=SiteBusinessContext(
            site_lead_rate_pct=2.0,
            period_sessions=5000.0,
            period_leads=100,
            period_lead_goal=120,
            p90_page_sessions=500.0,
        ),
    )

    assert finding is not None
    assert finding.evidence_json["link_from"] is None
    assert "mapped authoritative pages" in finding.recommended_action
