"""Which queries carry an AI Overview, and why it matters.

An AI Overview depresses clicks for everyone on the page, so this decides
which CTR curve `expected_ctr_at` reads. Reading the wrong one makes every
expected-clicks number on that query too high, which reaches the traffic
branch, the 2a listing rule and the engine's idea of what a ranking is worth.

It read only `facts_ser_domain_keywords` — keyword research data, six rows
across all twenty-four clients — while a hundred and five of the seven
hundred and sixty-nine tracked keywords carry `sge`.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.decisions.ctr_curve import expected_ctr_at, expected_ctr_percent, has_ai_overview
from app.models.seranking import FactSerDomainKeyword, FactSerKeyword
from app.services.lever_engine import _ai_overview_queries


_seq = iter(range(1, 10_000))


def _tracked(client_id, keyword, features):
    n = next(_seq)
    return FactSerKeyword(
        id=uuid4(),
        client_id=client_id,
        site_engine_id=f"engine-{n}",
        keyword_id=f"kw-{n}",
        keyword=keyword,
        checked_at=date.today(),
        earned_serp_features=features,
    )


def test_sge_is_an_ai_overview():
    """SE Ranking's name for it. The curve hangs off this word."""
    assert has_ai_overview(["sge"])
    assert has_ai_overview(["ai_overview"])
    assert not has_ai_overview(["images", "reviews", "local_pack"])
    assert not has_ai_overview(None)


def test_a_tracked_keyword_counts(db, client_a):
    """The row that was being ignored."""
    db.add(_tracked(client_a.id, "ai seo company", ["sge", "images"]))
    db.add(_tracked(client_a.id, "plain term", ["images"]))
    db.commit()

    found = _ai_overview_queries(db, client_a.id)
    assert "ai seo company" in found
    assert "plain term" not in found


def test_research_data_still_counts(db, client_a):
    """It is the source with the right meaning; it just has almost no rows."""
    db.add(
        FactSerDomainKeyword(
            id=uuid4(),
            client_id=client_a.id,
            keyword="researched term",
            serp_features=["ai_overview"],
        )
    )
    db.commit()
    assert "researched term" in _ai_overview_queries(db, client_a.id)


def test_both_sources_are_merged(db, client_a):
    db.add(
        FactSerDomainKeyword(
            id=uuid4(),
            client_id=client_a.id,
            keyword="from research",
            serp_features=["sge"],
        )
    )
    db.add(_tracked(client_a.id, "from tracking", ["sge"]))
    db.commit()

    found = _ai_overview_queries(db, client_a.id)
    assert {"from research", "from tracking"} <= found


def test_matching_is_case_and_space_insensitive(db, client_a):
    """Search Console queries arrive lowercased; a watchlist entry may not."""
    db.add(_tracked(client_a.id, "  AI SEO Company  ", ["sge"]))
    db.commit()
    assert "ai seo company" in _ai_overview_queries(db, client_a.id)


def test_one_client_cannot_see_another(db, client_a, client_b):
    db.add(_tracked(client_b.id, "theirs", ["sge"]))
    db.commit()
    assert "theirs" not in _ai_overview_queries(db, client_a.id)


def test_the_top_positions_are_worth_much_less_with_an_ai_overview():
    """Why any of this matters, and only where it does.

    The measured curves are 12.82 against 20.02 at position 1, 5.16 against
    10.36 at 2 and 1.63 against 3.89 at 3 — roughly half, which is where
    nearly all the clicks are.
    """
    for position in (1, 2, 3):
        with_aio = expected_ctr_at(position, ai_overview=True)
        without = expected_ctr_percent(position)
        assert with_aio < without * 0.7, position


def test_further_down_the_ai_overview_curve_is_higher():
    """Not a bug in the data and not a reason to skip the check: the answer
    takes the clicks off the top and what is left redistributes. Asserting
    "an AI Overview is always worse" would have been wrong, which is how
    this test came to exist."""
    assert expected_ctr_at(5, ai_overview=True) > expected_ctr_percent(5)
