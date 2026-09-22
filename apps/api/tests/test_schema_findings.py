"""Structured data as a Decision Engine signal.

Schema comes only from the first-party crawl, so the hard part is not detecting
its absence — it is refusing to claim absence for a page nobody crawled.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    CRAWL_SOURCE_SE_RANKING,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.services.decision_impact import ADVISORY_AUDIT_SIGNALS
from app.services.lever_engine import (
    PageSchema,
    _load_page_schema,
    detect_technical_signal,
)

PAGE = "https://example.com/services"


def _healthy(url: str = PAGE) -> FactCrawlPageSnapshot:
    return FactCrawlPageSnapshot(
        id=uuid4(),
        client_id=uuid4(),
        snapshot_date=date.today(),
        raw_url=url,
        normalized_url=url,
        indexable=True,
        status_code=200,
        canonical_url=url,
        inbound_internal_links=8,
        word_count=900,
        in_sitemap=True,
        title="Services",
        description="What we do.",
        redirect_count=0,
    )


def test_a_crawled_page_with_no_schema_is_reported():
    signal = detect_technical_signal(
        PAGE,
        _healthy(),
        schema_by_url={},
        schema_crawled_urls=frozenset({PAGE}),
    )

    assert signal is not None
    assert signal.audit_signal == "missing_schema"


def test_a_page_the_crawler_never_reached_makes_no_schema_claim():
    """
    The one that matters. Without the covered-URL set, every page on every
    client that has not been crawled yet would report as missing schema.
    """
    assert detect_technical_signal(PAGE, _healthy(), schema_crawled_urls=frozenset()) is None
    assert detect_technical_signal(PAGE, _healthy()) is None
    # Covered set present, but not this page.
    assert (
        detect_technical_signal(
            PAGE, _healthy(), schema_crawled_urls=frozenset({"https://example.com/other"})
        )
        is None
    )


def test_unparseable_schema_outranks_missing_schema():
    """Markup that is present but broken reads as done, and no consumer can use it."""
    signal = detect_technical_signal(
        PAGE,
        _healthy(),
        schema_by_url={PAGE: PageSchema(blocks=1, invalid=1)},
        schema_crawled_urls=frozenset({PAGE}),
    )

    assert signal is not None
    assert signal.audit_signal == "invalid_schema"


def test_a_page_with_valid_schema_reports_nothing():
    """`Organization` alone is boilerplate, so the page needs a descriptive type."""
    signal = detect_technical_signal(
        PAGE,
        _healthy(),
        schema_by_url={
            PAGE: PageSchema(blocks=3, invalid=0, types=frozenset({"Organization", "Service"}))
        },
        schema_crawled_urls=frozenset({PAGE}),
    )

    assert signal is None


def test_schema_never_preempts_a_real_defect():
    """A page returning 404 has a bigger problem than its markup."""
    broken = _healthy()
    broken.status_code = 404
    broken.indexable = False

    signal = detect_technical_signal(
        PAGE,
        broken,
        schema_by_url={},
        schema_crawled_urls=frozenset({PAGE}),
    )

    assert signal is not None
    assert signal.audit_signal == "status_error"


def test_missing_schema_is_advisory_and_invalid_schema_is_not():
    """Absent schema is an enhancement; broken schema is a defect to fix."""
    assert "missing_schema" in ADVISORY_AUDIT_SIGNALS
    assert "invalid_schema" not in ADVISORY_AUDIT_SIGNALS


# --- Loading ---------------------------------------------------------------


def test_coverage_comes_from_the_first_party_crawl_only(db, client_a):
    """
    SE Ranking snapshots carry no schema, so counting them as covered would
    report every page it found as having none.
    """
    ser = _healthy("https://example.com/from-se-ranking")
    ser.client_id = client_a.id
    ser.source = CRAWL_SOURCE_SE_RANKING
    mine = _healthy()
    mine.client_id = client_a.id
    mine.source = CRAWL_SOURCE_FIRST_PARTY
    db.add(ser)
    db.add(mine)
    db.commit()

    by_url, covered = _load_page_schema(db, client_a.id)

    assert covered == frozenset({PAGE})
    assert by_url == {}


def test_blocks_are_counted_and_invalid_ones_flagged(db, client_a):
    snapshot = _healthy()
    snapshot.client_id = client_a.id
    snapshot.source = CRAWL_SOURCE_FIRST_PARTY
    db.add(snapshot)
    for schema_type, error in (("Organization", None), ("WebSite", None), (None, "invalid JSON")):
        db.add(
            FactCrawlPageSchema(
                id=uuid4(),
                client_id=client_a.id,
                snapshot_date=date.today(),
                normalized_url=PAGE,
                syntax="json_ld",
                schema_type=schema_type,
                parse_error=error,
            )
        )
    db.commit()

    by_url, covered = _load_page_schema(db, client_a.id)

    assert PAGE in covered
    assert by_url[PAGE].blocks == 3
    assert by_url[PAGE].invalid == 1
    assert by_url[PAGE].types == frozenset({"Organization", "WebSite"})


def test_no_first_party_crawl_means_no_coverage_at_all(db, client_a):
    by_url, covered = _load_page_schema(db, client_a.id)
    assert by_url == {}
    assert covered == frozenset()


# --- Boilerplate-only schema -----------------------------------------------


def test_only_plugin_boilerplate_counts_as_no_structured_data():
    """
    Element Six's homepage: ImageObject, Organization, WebPage, WebSite and
    nothing saying what the company does. Markup is present, so a bare
    "has schema" check passes it; nothing here is about the page.
    """
    signal = detect_technical_signal(
        PAGE,
        _healthy(),
        schema_by_url={
            PAGE: PageSchema(
                blocks=4,
                invalid=0,
                types=frozenset({"ImageObject", "Organization", "WebPage", "WebSite"}),
            )
        },
        schema_crawled_urls=frozenset({PAGE}),
    )

    assert signal is not None
    assert signal.audit_signal == "missing_schema"
    assert signal.issue_code == "boilerplate_schema_only"
    assert "Organization" in signal.diagnosis


def test_author_markup_alone_does_not_describe_the_page():
    """Person describes the author, not the page, so it counts as boilerplate."""
    signal = detect_technical_signal(
        PAGE,
        _healthy(),
        schema_by_url={PAGE: PageSchema(blocks=3, invalid=0, types=frozenset({"WebPage", "Person"}))},
        schema_crawled_urls=frozenset({PAGE}),
    )

    assert signal is not None
    assert signal.issue_code == "boilerplate_schema_only"


def test_one_descriptive_type_is_enough():
    """No subtype map needed: BlogPosting passes without knowing it IS-A Article."""
    for descriptive in ("BlogPosting", "Service", "LocalBusiness", "FAQPage", "Product"):
        signal = detect_technical_signal(
            PAGE,
            _healthy(),
            schema_by_url={
                PAGE: PageSchema(
                    blocks=5,
                    invalid=0,
                    types=frozenset({"WebPage", "WebSite", "Person", descriptive}),
                )
            },
            schema_crawled_urls=frozenset({PAGE}),
        )
        assert signal is None, f"{descriptive} should satisfy the check"


def test_blocks_that_declare_no_type_read_as_boilerplate_not_broken():
    """
    A JSON-LD block that parses but declares no @type is not unparseable. It
    describes nothing, which "only boilerplate" reports more usefully than
    calling the markup broken.
    """
    signal = detect_technical_signal(
        PAGE,
        _healthy(),
        schema_by_url={PAGE: PageSchema(blocks=1, invalid=0, types=frozenset())},
        schema_crawled_urls=frozenset({PAGE}),
    )

    assert signal is not None
    assert signal.issue_code == "boilerplate_schema_only"
    assert "no recognisable types" in signal.diagnosis


# --- Schema must not crowd out work that pays -------------------------------


def test_schema_does_not_preempt_an_internal_linking_finding(db, client_a):
    """
    Found while cutting over: putting schema in the technical detector made an
    advisory "no structured data" note outrank an actionable internal-linking
    opportunity on the same page, because the technical pass runs first and
    wins. Schema is now the last resort across the whole cascade.
    """
    from decimal import Decimal

    from app.models.gsc import FactGscPage
    from app.services.lever_engine import active_crawl_source, diagnose
    from tests.conftest import date_window, seed_required_sources

    start, end = date_window(14)
    page = "https://clienta.example/blog/a-long-post-about-something"

    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url=page,
            normalized_url=page,
            country="usa",
            device="DESKTOP",
            impressions=Decimal("2911"),
            clicks=Decimal("2"),
            ctr=Decimal("0.0007"),
            average_position=Decimal("14.2"),
        )
    )
    snapshot = _healthy(page)
    snapshot.client_id = client_a.id
    snapshot.source = active_crawl_source()
    snapshot.inbound_internal_links = 6
    snapshot.word_count = 2500
    db.add(snapshot)
    db.commit()

    seed_required_sources(db, client_a.id, end)
    result = diagnose(db, client_a, from_date=start, to_date=end)

    levers = {f.lever for f in result.findings}
    assert "internal_linking" in levers, "schema should not have taken this page's slot"
