"""Gate 3: pages earning traffic and not turning it into anything.

The engine spent its attention on whether pages could be found. This asks what
the client is actually paying for — the traffic arrived, so what happened next?
"""

from __future__ import annotations

from app.services.decision_impact import PageBusinessContext, SiteBusinessContext
from app.services.lever_engine import (
    CONVERSION_PAGE_MIN_SHORTFALL,
    PageDemand,
    _conversion_page_findings,
)
from app.services.page_eligibility import PageClassification, PageType

URL = "https://example.com/services/roofing"


def _page(url=URL, impressions=2000.0):
    return PageDemand(
        normalized_url=url,
        impressions=impressions,
        clicks=200.0,
        average_position=5.0,
        ctr_percent=10.0,
    )


def _site(rate=2.0, leads=40, sessions=2000.0, goal=50):
    return SiteBusinessContext(
        site_lead_rate_pct=rate,
        period_sessions=sessions,
        period_leads=leads,
        period_lead_goal=goal,
        p90_page_sessions=500.0,
    )


def _ctx(sessions, leads, url=URL):
    return {url: PageBusinessContext(normalized_url=url, ga4_sessions=sessions, ga4_leads=leads)}


def _eligible(url=URL, eligible=True, page_type=PageType.COMMERCIAL):
    return {
        url: PageClassification(
            normalized_url=url,
            page_type=page_type,
            eligible_for_growth_action=eligible,
            strategic_priority=5,
            commercial_priority=5,
        )
    }


def test_traffic_with_no_conversions_is_found():
    """1,000 sessions at a 2% site rate should have produced about 20 leads."""
    findings = _conversion_page_findings(
        [_page()], page_contexts=_ctx(1000.0, 0), classifications=_eligible(), site=_site()
    )

    assert len(findings) == 1
    evidence = findings[0].evidence_json
    assert evidence["no_conversions_at_all"] is True
    assert evidence["shortfall_leads"] == 20.0
    assert "no conversions" in findings[0].diagnosis
    assert "CTA placement" in findings[0].recommended_action


def test_a_page_well_under_the_site_rate_is_found_even_with_some_leads():
    # 2,000 sessions, 10 leads = 0.5% against a 2% site: 30 leads short.
    findings = _conversion_page_findings(
        [_page()], page_contexts=_ctx(2000.0, 10), classifications=_eligible(), site=_site()
    )

    assert len(findings) == 1
    assert findings[0].evidence_json["shortfall_leads"] == 30.0
    assert "Converting at 0.50%" in findings[0].diagnosis


def test_a_page_merely_below_average_is_not_a_finding():
    """Half of every site's pages are below its average, by definition."""
    # 1.5% against 2% — under, but not halved.
    findings = _conversion_page_findings(
        [_page()], page_contexts=_ctx(2000.0, 30), classifications=_eligible(), site=_site()
    )

    assert findings == []


def test_a_small_page_with_no_conversions_is_not_surprising():
    """At a 2% site rate, 50 sessions expects one lead; zero means nothing."""
    findings = _conversion_page_findings(
        [_page()], page_contexts=_ctx(50.0, 0), classifications=_eligible(), site=_site()
    )

    assert findings == []
    assert 50.0 * 0.02 < CONVERSION_PAGE_MIN_SHORTFALL


def test_pages_that_are_not_meant_to_convert_are_skipped():
    findings = _conversion_page_findings(
        [_page()],
        page_contexts=_ctx(5000.0, 0),
        classifications=_eligible(eligible=False, page_type=PageType.UTILITY),
        site=_site(),
    )

    assert findings == []


def test_a_site_that_converts_nothing_is_gate_zero_s_problem():
    """With no site rate there is nothing to be below, and no page to blame."""
    findings = _conversion_page_findings(
        [_page()],
        page_contexts=_ctx(5000.0, 0),
        classifications=_eligible(),
        site=_site(rate=None, leads=0),
    )

    assert findings == []


def test_a_low_rate_site_still_gets_findings_at_higher_volume():
    """The comparison is the site's own rate, not an industry figure."""
    # 0.4% site rate: 1,000 sessions expects 4 leads, so zero is a finding.
    findings = _conversion_page_findings(
        [_page()],
        page_contexts=_ctx(1000.0, 0),
        classifications=_eligible(),
        site=_site(rate=0.4, leads=8, sessions=2000.0),
    )

    assert len(findings) == 1
    assert findings[0].evidence_json["shortfall_leads"] == 4.0


def test_the_bigger_loss_scores_higher():
    site = _site()
    small = _conversion_page_findings(
        [_page()], page_contexts=_ctx(500.0, 0), classifications=_eligible(), site=site
    )
    big = _conversion_page_findings(
        [_page()], page_contexts=_ctx(5000.0, 0), classifications=_eligible(), site=site
    )

    assert small and big
    assert big[0].impact > small[0].impact


# --- Through diagnose -------------------------------------------------------


def test_it_reaches_the_queue_end_to_end(db, client_a):
    """Unit coverage proves the maths; this proves it is wired in."""
    from datetime import date, timedelta
    from decimal import Decimal
    from uuid import uuid4

    from app.models.config import ConversionDefinition, OrganicChannel
    from app.models.ga4 import FactGa4Event, FactGa4Traffic
    from app.models.gsc import FactGscPage
    from app.services.lever_engine import diagnose
    from tests.conftest import seed_required_sources

    end = date(2026, 8, 31)
    start = end - timedelta(days=29)
    page = "https://example.com/services/roofing"
    other = "https://example.com/contact"

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
    for url, impressions in ((page, 3000), (other, 500)):
        db.add(
            FactGscPage(
                id=uuid4(),
                client_id=client_a.id,
                date=end,
                raw_url=url,
                normalized_url=url,
                country="",
                device="",
                impressions=Decimal(impressions),
                clicks=Decimal("100"),
                ctr=Decimal("0.03"),
                average_position=Decimal("6"),
            )
        )

    def traffic(url, sessions, on):
        db.add(
            FactGa4Traffic(
                id=uuid4(),
                client_id=client_a.id,
                date=on,
                raw_url=url,
                normalized_url=url,
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                sessions=Decimal(sessions),
                active_users=Decimal(sessions),
                views=Decimal(sessions),
            )
        )

    # The offender: lots of traffic, nothing to show for it.
    traffic(page, 2000, end)
    # The rest of the site converts, which is what gives us a site rate — and
    # keeps Gate 0 quiet so this finding is not suppressed.
    traffic(other, 1000, end)
    db.add(
        FactGa4Event(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url=other,
            normalized_url=other,
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="generate_lead",
            event_count=40,
        )
    )
    db.commit()
    seed_required_sources(db, client_a.id, end)

    result = diagnose(db, client_a, from_date=start, to_date=end)

    gate3 = [row for row in result.findings if row.evidence_json.get("gate") == "conversion_page"]
    assert [row.page_url for row in gate3] == [page]
    assert gate3[0].suppressed_by is None
    assert gate3[0].core_work is False
    assert gate3[0].evidence_json["leads"] == 0


# --- T3: judged against its own kind of page --------------------------------


def _support(**kwargs):
    return {key: value for key, value in kwargs.items()}


def test_a_blog_post_is_judged_against_blog_posts(db, client_a):
    """0.4% is a blog post doing its job and a service page failing. One
    sitewide number flags every blog on a site with good service pages."""
    from app.services.page_eligibility import PageType

    blog = "https://example.com/blog/guide"
    classifications = {
        blog: PageClassification(
            normalized_url=blog,
            page_type=PageType.INFORMATIONAL,
            eligible_for_growth_action=True,
            strategic_priority=2,
            commercial_priority=2,
        )
    }
    # Site converts at 2%, blogs at 0.5%. This post is at 0.4%.
    findings = _conversion_page_findings(
        [_page(url=blog)],
        page_contexts={
            blog: PageBusinessContext(normalized_url=blog, ga4_sessions=2000.0, ga4_leads=8)
        },
        classifications=classifications,
        site=_site(rate=2.0),
        page_type_rates={"informational": 0.5},
        page_type_support={"informational": (12, 40)},
    )

    assert findings == []


def test_the_same_page_against_the_sitewide_rate_would_have_fired(db, client_a):
    """Which is the behaviour being corrected."""
    from app.services.page_eligibility import PageType

    blog = "https://example.com/blog/guide"
    classifications = {
        blog: PageClassification(
            normalized_url=blog,
            page_type=PageType.INFORMATIONAL,
            eligible_for_growth_action=True,
            strategic_priority=2,
            commercial_priority=2,
        )
    }
    findings = _conversion_page_findings(
        [_page(url=blog)],
        page_contexts={
            blog: PageBusinessContext(normalized_url=blog, ga4_sessions=2000.0, ga4_leads=8)
        },
        classifications=classifications,
        site=_site(rate=2.0),
        page_type_rates={},
        page_type_support={},
    )

    assert len(findings) == 1
    assert findings[0].evidence_json["benchmark_source"] == "site"


def test_a_thin_page_type_falls_back_to_the_sitewide_rate(db, client_a):
    """Two pages and one lead produce a number, not a comparison."""
    from app.services.page_eligibility import PageType

    blog = "https://example.com/blog/guide"
    classifications = {
        blog: PageClassification(
            normalized_url=blog,
            page_type=PageType.INFORMATIONAL,
            eligible_for_growth_action=True,
            strategic_priority=2,
            commercial_priority=2,
        )
    }
    findings = _conversion_page_findings(
        [_page(url=blog)],
        page_contexts={
            blog: PageBusinessContext(normalized_url=blog, ga4_sessions=2000.0, ga4_leads=8)
        },
        classifications=classifications,
        site=_site(rate=2.0),
        page_type_rates={"informational": 0.5},
        page_type_support={"informational": (2, 1)},
    )

    assert len(findings) == 1
    assert findings[0].evidence_json["benchmark_source"] == "site"
