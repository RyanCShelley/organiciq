"""What a page used to draw, and what it draws now.

The Traffic and Leads candidates described one window. An update is
prescribed for a page that is losing something, and one window cannot say
that — so `PageCandidate` carries the 28 days before as well, and these
are the readings taken from the pair.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.decisions.page_targets import PageCandidate
from app.models.gsc import FactGscPage, FactGscQueryPage
from app.services.page_signals import WINDOW_DAYS, load_page_candidates


def _page(**kwargs) -> PageCandidate:
    return PageCandidate(url=kwargs.pop("url", "https://example.com/a"), **kwargs)


# ── The readings ──


def test_a_page_with_no_earlier_figures_has_lost_nothing():
    """A page published last month is not a decaying one."""
    page = _page(impressions=50.0)
    assert page.has_prior is False
    assert page.impressions_lost == 0.0
    assert page.impressions_change is None


def test_impressions_lost_is_what_it_used_to_draw_and_does_not():
    page = _page(impressions=300.0, prior_impressions=1200.0)
    assert page.impressions_lost == 900.0
    assert page.impressions_change == -0.75


def test_a_page_that_grew_has_lost_nothing():
    page = _page(impressions=1200.0, prior_impressions=300.0)
    assert page.impressions_lost == 0.0
    assert page.impressions_change == 3.0


def test_position_change_is_positive_when_it_slipped_down():
    assert _page(position=11.0, prior_position=4.0).position_change == 7.0
    assert _page(position=4.0, prior_position=11.0).position_change == -7.0
    assert _page(position=4.0).position_change is None


def test_a_page_whose_ranking_improved_is_never_decaying():
    """ACCTek's /managed-it-services-syracuse-ny, from production.

    It lost 7,524 → 4,707 impressions over the same weeks its position
    improved from 32.7 to 21.5. Impressions alone call that decay. It is a
    SERP that changed shape, and prescribing a refresh for it would spend
    a month's allowance on a page that is winning.
    """
    page = _page(
        impressions=4707.0,
        prior_impressions=7524.0,
        position=21.5,
        prior_position=32.7,
    )
    assert page.impressions_lost == 2817.0
    assert page.held_or_improved_position is True


def test_a_page_that_lost_both_is_decaying():
    page = _page(
        impressions=5111.0, prior_impressions=43531.0, position=43.1, prior_position=40.4
    )
    assert page.held_or_improved_position is False


def test_an_unranked_page_cannot_be_said_to_have_held_its_position():
    """No position in either window is not the same as holding one."""
    assert _page(impressions=10.0, prior_impressions=20.0).held_or_improved_position is False


# ── Reading them out of the warehouse ──


def _gsc(db, client_id, url, day, *, impressions, clicks, position, query=None):
    """One page's figures for one day. The grain is one row per page per day."""
    db.add(
        FactGscPage(
            client_id=client_id,
            date=day,
            raw_url=url,
            normalized_url=url,
            country="",
            device="",
            impressions=impressions,
            clicks=clicks,
            ctr=0,
            average_position=position,
        )
    )
    if query:
        _query(db, client_id, url, day, query, impressions=impressions, position=position)


def _query(db, client_id, url, day, query, *, impressions, position, clicks=0):
    db.add(
        FactGscQueryPage(
            client_id=client_id,
            date=day,
            query=query,
            raw_url=url,
            normalized_url=url,
            country="",
            device="",
            impressions=impressions,
            clicks=clicks,
            ctr=0,
            average_position=position,
        )
    )


def test_the_loader_reads_both_windows(db, client_a):
    today = date(2026, 10, 13)
    now = today - timedelta(days=1)
    before = today - timedelta(days=WINDOW_DAYS + 1)
    url = "https://example.com/guide"
    _gsc(db, client_a.id, url, now, impressions=100, clicks=2, position=12.0)
    _gsc(db, client_a.id, url, before, impressions=400, clicks=20, position=5.0)
    db.commit()

    page = next(
        p for p in load_page_candidates(db, client_a, today=today) if p.url == url
    )
    assert page.impressions == 100
    assert page.prior_impressions == 400
    assert page.prior_clicks == 20
    assert page.prior_position == 5.0
    assert page.impressions_lost == 300


def test_a_page_that_drew_nothing_this_period_is_still_a_candidate(db, client_a):
    """Total collapse is the strongest decay signal there is.

    Reading only the current window drops exactly the pages that lost
    everything, which are the ones worth looking at first.
    """
    today = date(2026, 10, 13)
    url = "https://example.com/gone-quiet"
    _gsc(
        db,
        client_a.id,
        url,
        today - timedelta(days=WINDOW_DAYS + 1),
        impressions=900,
        clicks=40,
        position=6.0,
    )
    db.commit()

    page = next(
        p for p in load_page_candidates(db, client_a, today=today) if p.url == url
    )
    assert page.impressions == 0
    assert page.impressions_lost == 900


def test_the_loader_names_the_query_that_lost_the_most(db, client_a):
    """"The page is down" is not a brief; naming the term is."""
    today = date(2026, 10, 13)
    now = today - timedelta(days=1)
    before = today - timedelta(days=WINDOW_DAYS + 1)
    url = "https://example.com/guide"
    # The page fact is one row per page per day, so it is written once.
    _gsc(db, client_a.id, url, before, impressions=1000, clicks=45, position=4.0)
    _gsc(db, client_a.id, url, now, impressions=250, clicks=6, position=10.0)
    # The big loser, and a smaller one that must not win the comparison.
    _query(db, client_a.id, url, before, "seo audit", impressions=800, position=3.0)
    _query(db, client_a.id, url, now, "seo audit", impressions=100, position=11.0)
    _query(db, client_a.id, url, before, "seo check", impressions=200, position=8.0)
    _query(db, client_a.id, url, now, "seo check", impressions=150, position=8.0)
    db.commit()

    page = next(
        p for p in load_page_candidates(db, client_a, today=today) if p.url == url
    )
    assert page.top_lost_query == "seo audit"
    assert page.top_lost_query_prior_position == 3.0
    assert page.top_lost_query_position == 11.0


def test_a_query_that_only_appeared_this_period_is_not_a_loss(db, client_a):
    today = date(2026, 10, 13)
    url = "https://example.com/guide"
    _gsc(
        db, client_a.id, url, today - timedelta(days=1),
        impressions=500, clicks=10, position=7.0, query="brand new term",
    )
    db.commit()

    page = next(
        p for p in load_page_candidates(db, client_a, today=today) if p.url == url
    )
    assert page.top_lost_query is None


def test_the_loader_names_the_donors_for_an_under_linked_page(db, client_a):
    from uuid import uuid4

    from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot

    today = date(2026, 10, 13)
    day = today - timedelta(days=3)
    page, pillar = "https://example.com/orphan", "https://example.com/pillar"
    _gsc(db, client_a.id, page, day, impressions=400, clicks=5, position=9.0)
    _query(db, client_a.id, page, day, "metal roof cost", impressions=400, position=9.0, clicks=5)
    _query(db, client_a.id, pillar, day, "metal roof cost", impressions=2000, position=2.0, clicks=300)
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(),
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=day,
            raw_url=page,
            normalized_url=page,
            status_code=200,
            indexable=True,
            word_count=900,
            inbound_internal_links=40,
            inbound_editorial_links=1,
            redirect_count=0,
        )
    )
    db.commit()

    found = next(p for p in load_page_candidates(db, client_a, today=today) if p.url == page)
    assert [d.url for d in found.link_donors] == [pillar]
    assert found.link_donors[0].anchor == "metal roof cost"


def test_a_donor_found_only_through_the_brand_name_is_dropped(db, client_a):
    from uuid import uuid4

    from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
    from app.services.page_signals import brand_terms

    today = date(2026, 10, 13)
    day = today - timedelta(days=3)
    page, home = "https://example.com/contact", "https://example.com/"
    name = sorted(brand_terms(client_a))[0]
    _gsc(db, client_a.id, page, day, impressions=400, clicks=5, position=9.0)
    _query(db, client_a.id, page, day, name, impressions=400, position=9.0, clicks=5)
    _query(db, client_a.id, home, day, name, impressions=2000, position=1.0, clicks=300)
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(), client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=day, raw_url=page, normalized_url=page, status_code=200,
            indexable=True, word_count=900, inbound_internal_links=40,
            inbound_editorial_links=0, redirect_count=0,
        )
    )
    db.commit()

    found = next(p for p in load_page_candidates(db, client_a, today=today) if p.url == page)
    assert found.link_donors == ()


def test_a_brand_alias_makes_its_query_navigation(db, client_a):
    """ACCTek is searched as "acc technical services"; its name and domain say "acctek"."""
    from uuid import uuid4

    from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot

    today = date(2026, 10, 13)
    day = today - timedelta(days=3)
    page, home = "https://example.com/contact", "https://example.com/"

    def donors(aliases):
        client_a.brand_aliases = aliases
        db.commit()
        return next(
            p for p in load_page_candidates(db, client_a, today=today) if p.url == page
        ).link_donors

    _gsc(db, client_a.id, page, day, impressions=400, clicks=5, position=9.0)
    _query(db, client_a.id, page, day, "long form company name", impressions=400, position=9.0, clicks=5)
    _query(db, client_a.id, home, day, "long form company name", impressions=2000, position=1.0, clicks=300)
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(), client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=day, raw_url=page, normalized_url=page, status_code=200,
            indexable=True, word_count=900, inbound_internal_links=40,
            inbound_editorial_links=0, redirect_count=0,
        )
    )
    db.commit()

    # Without the alias it reads as a topic — the fault this field exists for.
    assert [d.url for d in donors([])] == [home]
    assert donors(["long form company name"]) == ()


def test_aliases_are_cleaned_before_they_are_stored():
    from app.services.clients import clean_brand_aliases

    assert clean_brand_aliases(["  ACC  Technical Services ", "acc technical services", "ab", ""]) == [
        "acc technical services"
    ]
    assert clean_brand_aliases(None) == []
