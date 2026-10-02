"""Subjects the site draws demand for and has no page ranking on.

The link-gap rule asks which existing page should point at another. This asks
the question underneath it: is there a subject here with no page at all?
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.gsc import FactGscQueryPage
from app.services.decision_impact import SiteBusinessContext
from app.services.lever_engine import (
    CLUSTER_MIN_IMPRESSIONS,
    _brand_tokens,
    _cluster_tokens,
    _content_cluster_findings,
)

def _site(rate=2.0, leads=40, goal=50):
    """A site that converts, so impact can be expressed in leads."""
    return SiteBusinessContext(
        site_lead_rate_pct=rate,
        period_sessions=2000.0,
        period_leads=leads,
        period_lead_goal=goal,
        p90_page_sessions=500.0,
    )


END = date(2026, 8, 31)
PERIOD = (END - timedelta(days=29), END)


def _q(db, client_id, query, impressions, position, url="https://example.com/x"):
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
            clicks=Decimal("0"),
            ctr=Decimal("0"),
            average_position=Decimal(position),
        )
    )


def test_a_subject_with_demand_and_no_ranking_page_is_found(db, client_a):
    for query, impressions in (
        ("schema markup for local business", 600),
        ("schema markup generator", 500),
        ("what is schema markup", 400),
    ):
        _q(db, client_a.id, query, impressions, 32)
    db.commit()

    findings = _content_cluster_findings(db, client_a, period=PERIOD, site=_site())

    assert len(findings) == 1
    evidence = findings[0].evidence_json
    # Both words cover the same queries, so they are one subject with a
    # two-word name rather than two clusters saying the same thing.
    assert evidence["cluster_token"] == "schema markup"
    assert evidence["query_count"] == 3
    assert evidence["impressions"] == 1500
    assert len(evidence["example_queries"]) == 3
    assert "Write or rework a page" in findings[0].recommended_action


def test_a_subject_that_already_has_an_owner_is_not_a_gap(db, client_a):
    """Something ranking page one is a page to strengthen, not a cluster to start."""
    for query, impressions, position in (
        ("schema markup for local business", 600, 4),
        ("schema markup generator", 500, 30),
        ("what is schema markup", 400, 28),
    ):
        _q(db, client_a.id, query, impressions, position)
    db.commit()

    assert _content_cluster_findings(db, client_a, period=PERIOD, site=_site()) == []


def test_one_or_two_queries_is_a_coincidence_not_a_subject(db, client_a):
    _q(db, client_a.id, "schema markup generator", 900, 40)
    _q(db, client_a.id, "schema markup guide", 900, 40)
    db.commit()

    assert _content_cluster_findings(db, client_a, period=PERIOD, site=_site()) == []


def test_a_subject_with_little_demand_is_not_worth_a_page(db, client_a):
    for query in ("widget colour", "widget colour chart", "widget colour guide"):
        _q(db, client_a.id, query, 20, 40)
    db.commit()

    assert _content_cluster_findings(db, client_a, period=PERIOD, site=_site()) == []
    assert 60 < CLUSTER_MIN_IMPRESSIONS


def test_the_brand_is_not_a_content_gap(db, client_a):
    """Brand demand is owned by existing, and would form the biggest cluster."""
    client_a.client_name = "Acme Roofing"
    client_a.domain = "acmeroofing.com"
    db.commit()
    for query in ("acme roofing reviews", "acme roofing careers", "acme roofing phone"):
        _q(db, client_a.id, query, 800, 40)
    db.commit()

    tokens = {
        row.evidence_json["cluster_token"]
        for row in _content_cluster_findings(db, client_a, period=PERIOD, site=_site())
    }
    assert "acme" not in tokens
    assert "acmeroofing" not in tokens


def test_joining_words_do_not_form_subjects():
    brand = frozenset()
    assert _cluster_tokens("what is the best roofing cost near me", brand) == ["roofing"]
    assert _cluster_tokens("how do i install metal roofing", brand) == ["install", "metal", "roofing"]


def test_brand_tokens_cover_name_and_domain(db, client_a):
    client_a.client_name = "Dragon Plate"
    client_a.domain = "dragonplate.com"
    db.commit()

    tokens = _brand_tokens(client_a)

    assert "dragon" in tokens
    assert "plate" in tokens
    assert "dragonplate" in tokens


def test_only_the_strongest_clusters_are_reported(db, client_a):
    """Clusters overlap by construction, so the list has to be capped."""
    # Two shared words each, so each forms a real cluster.
    for topic in ("alpha roofing", "bravo siding", "charlie decking", "delta fencing",
                  "echo guttering", "foxtrot cladding", "golf paving"):
        for suffix in ("guide", "cost", "example"):
            _q(db, client_a.id, f"{topic} {suffix}", 500, 40)
    db.commit()

    findings = _content_cluster_findings(db, client_a, period=PERIOD, site=_site())

    assert len(findings) == 5


def test_no_period_means_no_findings(db, client_a):
    assert _content_cluster_findings(db, client_a, period=None, site=_site()) == []


def test_two_words_over_the_same_queries_are_one_cluster(db, client_a):
    """Reporting "schema" and "markup" separately is the duplication to avoid."""
    for query, impressions in (
        ("local seo checklist", 700),
        ("local seo checklist for dentists", 600),
        ("free local seo checklist", 500),
    ):
        _q(db, client_a.id, query, impressions, 35)
    db.commit()

    findings = _content_cluster_findings(db, client_a, period=PERIOD, site=_site())

    assert len(findings) == 1
    # Ordered as a person says it, from the busiest query, not alphabetically.
    assert findings[0].evidence_json["cluster_token"] == "local seo checklist"


def test_a_narrower_subject_inside_a_broader_one_stays_separate(db, client_a):
    """Different query sets are different subjects, even sharing a word."""
    for query in ("metal roofing cost", "metal roofing install", "metal roofing colours"):
        _q(db, client_a.id, query, 500, 35)
    for query in ("tile roofing cost", "tile roofing weight"):
        _q(db, client_a.id, query, 500, 35)
    db.commit()

    tokens = {
        row.evidence_json["cluster_token"]
        for row in _content_cluster_findings(db, client_a, period=PERIOD, site=_site())
    }

    assert "metal roofing" in tokens
    # "roofing" alone spans all five queries but is one word — a coincidence of
    # vocabulary, not a subject, and no longer a cluster. T5.
    assert "roofing" not in tokens


# --- T5: phrases, generics and exclusions -----------------------------------


def test_a_single_shared_word_is_not_a_subject(db, client_a):
    """"guide" joins a hundred unrelated queries."""
    for query in ("roofing guide", "plumbing guide", "fencing guide", "decking guide"):
        _q(db, client_a.id, query, 800, 40)
    db.commit()

    assert _content_cluster_findings(db, client_a, period=PERIOD, site=_site()) == []


def test_a_client_can_strike_out_generic_terms(db, client_a):
    """Words that join this client's queries without describing them."""
    for query in ("roofing quick reliable", "siding quick reliable", "decking quick reliable"):
        _q(db, client_a.id, query, 800, 40)
    db.commit()

    # "quick reliable" joins three unrelated services and describes none.
    without = {
        row.evidence_json["cluster_token"]
        for row in _content_cluster_findings(db, client_a, period=PERIOD, site=_site())
    }
    assert "quick reliable" in without

    with_list = _content_cluster_findings(
        db,
        client_a,
        period=PERIOD,
        site=_site(),
        thresholds={"cluster_generic_terms": ["quick", "reliable"]},
    )
    assert with_list == []


def test_a_client_can_exclude_a_topic_outright(db, client_a):
    for query in ("asbestos removal cost", "asbestos removal near", "asbestos removal law"):
        _q(db, client_a.id, query, 900, 40)
    db.commit()

    assert (
        _content_cluster_findings(
            db,
            client_a,
            period=PERIOD,
            site=_site(),
            thresholds={"cluster_excluded_topics": ["asbestos"]},
        )
        == []
    )
