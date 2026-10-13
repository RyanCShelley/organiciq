"""A page the site does not have.

The hard part is being sure it is missing. A tracked term with no map entry
and no suggestion looked like a gap on ACCTek, and four of its six were pages
the site already has.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.decisions.content_gaps import (
    MIN_VOLUME,
    NearPage,
    TermGap,
    c1_write_the_page,
    content_words,
    fold_variants,
    rank_for_content,
)
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.decision import KeywordTarget
from app.models.seranking import FactSerKeyword, FactSerKeywordMetric
from app.services.content_gap_signals import MIN_CRAWLED_PAGES, scan_term_gaps


def _gap(**overrides) -> TermGap:
    fields = {"term": "aeo agency", "volume": 480.0, "difficulty": 12.0, "pages_searched": 300}
    fields.update(overrides)
    return TermGap(**fields)


# ── The brief ──


def test_c1_fires_on_a_term_with_volume_and_a_known_difficulty():
    found = c1_write_the_page(_gap())
    assert found is not None
    assert found.action_id == "C-1"
    assert found.term == "aeo agency"
    assert found.metric_key == "term_position"
    assert found.target_url == ""  # there is no page yet
    assert found.check_after_days == 90


def test_c1_states_what_its_claim_of_absence_rests_on():
    assert "None of the 300 indexable pages" in c1_write_the_page(_gap()).why
    recorded = c1_write_the_page(_gap(recorded_no_page=True))
    assert "recorded in the keyword map as having no page" in recorded.why


def test_c1_does_not_fire_below_the_volume_floor():
    assert c1_write_the_page(_gap(volume=MIN_VOLUME - 1)) is None


def test_c1_will_not_score_a_term_whose_difficulty_is_unknown():
    """Ranking by volume alone would put the term nobody can win first."""
    assert c1_write_the_page(_gap(difficulty=None)) is None


def test_difficulty_discounts_volume():
    hard = _gap(term="a", volume=9900.0, difficulty=63.0)
    easy = _gap(term="b", volume=480.0, difficulty=12.0)
    assert hard.opportunity == 9900 * 0.37
    assert easy.opportunity == 480 * 0.88
    assert [g.term for g in rank_for_content([easy, hard])] == ["a", "b"]


def test_the_brief_names_variants_the_page_has_to_cover_and_where_to_link_from():
    found = c1_write_the_page(
        _gap(
            also_covers=(("seo consultancy", 120.0),),
            nearest=(NearPage(url="https://x.test/seo", title="SEO", shared=("seo",)),),
        )
    )
    text = " ".join(found.steps)
    assert "“seo consultancy” (120)" in text
    assert "https://x.test/seo (shares seo)" in text
    assert "keyword map" in found.steps[-1]


def test_variants_of_one_subject_share_a_page():
    folded = fold_variants(
        [
            _gap(term="pressure washing", volume=9000.0),
            _gap(term="commercial pressure washing", volume=9900.0),
            _gap(term="paver sealing", volume=300.0),
        ]
    )
    assert [g.term for g in folded] == ["commercial pressure washing", "paver sealing"]
    assert folded[0].also_covers == (("pressure washing", 9000.0),)


def test_words_are_compared_without_filler_or_plurals():
    assert content_words("plumbers near me") == content_words("Plumber")
    assert content_words("the best SEO services") == frozenset({"seo"})


# ── The scan ──

DAY = date(2026, 10, 1)


def _page(db, client_id, slug, title=None, headings=()):
    url = f"https://example.com/{slug}"
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(), client_id=client_id, source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=DAY, raw_url=url, normalized_url=url, status_code=200,
            indexable=True, word_count=800, inbound_internal_links=5,
            inbound_editorial_links=3, redirect_count=0, title=title,
            sections=[{"heading": h} for h in headings],
        )
    )


def _filler(db, client_id, n=MIN_CRAWLED_PAGES):
    for i in range(n):
        _page(db, client_id, f"filler-{i}", title=f"Filler {i}")


def _term(db, client_id, keyword, *, volume=500, difficulty=20, mapped_to=None, no_page=False,
          position=None, ranking_url=None):
    db.add(
        FactSerKeyword(
            id=uuid4(), client_id=client_id, site_engine_id="1",
            keyword_id=str(uuid4())[:8], keyword=keyword, volume=volume,
            current_position=position, ranking_url=ranking_url,
        )
    )
    db.add(
        FactSerKeywordMetric(
            id=uuid4(), client_id=client_id, keyword=keyword, source="us",
            volume=volume, difficulty=difficulty, data_found=True, fetched_at=DAY,
        )
    )
    if mapped_to is not None or no_page:
        db.add(
            KeywordTarget(
                id=uuid4(), client_id=client_id, keyword=keyword,
                target_url=mapped_to, source="confirmed",
            )
        )


def test_a_term_no_page_carries_is_a_gap(db, client_a):
    _filler(db, client_a.id)
    _term(db, client_a.id, "aeo agency")
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["aeo agency"]
    assert scan.gaps[0].pages_searched == MIN_CRAWLED_PAGES


def test_a_term_a_page_already_carries_is_not(db, client_a):
    """ACCTek's /vciso and /structured-cabling, which an unmapped-term test called gaps."""
    _filler(db, client_a.id)
    _page(db, client_a.id, "structured-cabling", title="Structured Cabling - Acme")
    _page(db, client_a.id, "guides", title="Guides", headings=["What is a vCISO?"])
    _term(db, client_a.id, "structured cabling")
    _term(db, client_a.id, "vciso")
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert scan.gaps == []
    assert scan.summary["covered"] == 2


def test_a_term_mapped_to_a_page_is_somebodys_decision(db, client_a):
    _filler(db, client_a.id)
    _term(db, client_a.id, "aeo agency", mapped_to="https://example.com/filler-1")
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert scan.gaps == [] and scan.summary["mapped"] == 1


def test_a_term_recorded_as_having_no_page_is_a_gap_even_if_words_match(db, client_a):
    _filler(db, client_a.id)
    _page(db, client_a.id, "seo", title="SEO consulting agency")
    _term(db, client_a.id, "seo consulting agency", no_page=True)
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert [g.term for g in scan.gaps] == ["seo consulting agency"]
    assert scan.gaps[0].recorded_no_page is True


def test_a_term_already_ranking_has_a_page(db, client_a):
    _filler(db, client_a.id)
    _term(db, client_a.id, "aeo agency", position=14, ranking_url="https://example.com/x")
    db.commit()
    assert scan_term_gaps(db, client_a).gaps == []


def test_a_term_without_volume_and_difficulty_is_set_aside_and_counted(db, client_a):
    _filler(db, client_a.id)
    _term(db, client_a.id, "aeo agency", difficulty=None)
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert scan.gaps == [] and scan.summary["no_metrics"] == 1


def test_a_crawl_too_small_to_prove_absence_blocks_the_scan(db, client_a):
    """Fourteen clients have a crawl of zero or one page."""
    _page(db, client_a.id, "home", title="Home")
    _term(db, client_a.id, "aeo agency")
    db.commit()
    scan = scan_term_gaps(db, client_a)
    assert scan.gaps == []
    assert "too few to say a term has no page" in scan.explain_empty()


def test_an_empty_scan_says_what_it_checked(db, client_a):
    _filler(db, client_a.id)
    _page(db, client_a.id, "vciso", title="vCISO")
    _term(db, client_a.id, "vciso")
    db.commit()
    assert "1 already covered" in scan_term_gaps(db, client_a).explain_empty()


def test_an_inflected_form_still_meets_the_page_that_covers_it():
    """Aquaman's "leaking hot tub" beside /blog/find-a-hot-tub-leak-quickly."""
    assert content_words("leaking hot tub") <= content_words(
        "Find A Hot Tub Leak Quickly https://x.test/blog/find-a-hot-tub-leak-quickly"
    )
    assert content_words("washing") == content_words("washer")


def test_intent_codes_are_spelled_out():
    assert "local / commercial" in c1_write_the_page(_gap(intents=("L", "C"))).steps[0]
