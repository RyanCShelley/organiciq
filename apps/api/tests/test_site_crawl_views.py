"""The Site crawl views: pages, page detail, and structured data."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    CRAWL_SOURCE_SE_RANKING,
    FactCrawlInternalLink,
    FactCrawlPageIssue,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from tests.conftest import client_header

PAGE = "https://example.com/services"
OTHER = "https://example.com/blog/post"


def _snapshot(client_id, url, *, source=CRAWL_SOURCE_FIRST_PARTY, in_sitemap=True, indexable=True):
    return FactCrawlPageSnapshot(
        id=uuid4(),
        client_id=client_id,
        source=source,
        snapshot_date=date.today(),
        raw_url=url,
        normalized_url=url,
        indexable=indexable,
        status_code=200,
        canonical_url=url,
        inbound_internal_links=3,
        inbound_editorial_links=1,
        word_count=800,
        in_sitemap=in_sitemap,
        title="Services",
        description="What we do.",
        redirect_count=0,
    )


def _link(client_id, from_url, to_url, *, anchor="see our services", template=False):
    return FactCrawlInternalLink(
        id=uuid4(),
        client_id=client_id,
        source=CRAWL_SOURCE_FIRST_PARTY,
        snapshot_date=date.today(),
        from_url=from_url,
        to_url=to_url,
        anchor_text=anchor,
        in_content=not template,
        is_template=template,
        occurrences=1,
    )


def _schema(client_id, url, schema_type, *, raw=None, error=None):
    return FactCrawlPageSchema(
        id=uuid4(),
        client_id=client_id,
        snapshot_date=date.today(),
        normalized_url=url,
        syntax="json_ld",
        schema_type=schema_type,
        raw=raw,
        parse_error=error,
    )


# --- Pages ------------------------------------------------------------------


def test_pages_only_reports_the_first_party_crawl(client, db, client_a, admin_user):
    db.add(_snapshot(client_a.id, PAGE))
    db.add(_snapshot(client_a.id, OTHER, source=CRAWL_SOURCE_SE_RANKING))
    db.commit()

    body = client.get(
        "/site-crawl/pages", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["total_pages"] == 1
    assert [row["url"] for row in body["items"]] == [PAGE]


def test_sitemap_state_is_only_claimed_when_a_sitemap_was_found(client, db, client_a, admin_user):
    """
    Without a sitemap every page would read "missing from it", when the real
    finding is the site-level one the crawl already records.
    """
    db.add(_snapshot(client_a.id, PAGE, in_sitemap=False))
    db.add(
        FactCrawlPageIssue(
            id=uuid4(),
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=date.today(),
            issue_code="sitemap_missing",
            raw={},
        )
    )
    db.commit()

    body = client.get(
        "/site-crawl/pages", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["sitemap_found"] is False
    assert body["pages_in_sitemap"] == 0


def test_sitemap_coverage_is_reported_when_one_exists(client, db, client_a, admin_user):
    db.add(_snapshot(client_a.id, PAGE, in_sitemap=True))
    db.add(_snapshot(client_a.id, OTHER, in_sitemap=False))
    db.commit()

    body = client.get(
        "/site-crawl/pages", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["sitemap_found"] is True
    assert body["pages_in_sitemap"] == 1


def test_orphaned_counts_only_indexable_pages(client, db, client_a, admin_user):
    orphan = _snapshot(client_a.id, OTHER)
    orphan.inbound_editorial_links = 0
    blocked = _snapshot(client_a.id, "https://example.com/gone", indexable=False)
    blocked.inbound_editorial_links = 0
    db.add(_snapshot(client_a.id, PAGE))
    db.add(orphan)
    db.add(blocked)
    db.commit()

    body = client.get(
        "/site-crawl/pages", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["orphaned_pages"] == 1


# --- Page detail ------------------------------------------------------------


def test_page_detail_lists_editorial_links_and_counts_template_ones(client, db, client_a, admin_user):
    """A nav link is the same on every page: the count is the whole signal."""
    db.add(_snapshot(client_a.id, PAGE))
    db.add(_link(client_a.id, OTHER, PAGE))
    db.add(_link(client_a.id, "https://example.com/", PAGE, anchor="Services", template=True))
    db.add(_link(client_a.id, PAGE, OTHER, anchor="read the post"))
    db.commit()

    body = client.get(
        f"/site-crawl/page?url={PAGE}", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["found"] is True
    assert [row["url"] for row in body["inbound"]] == [OTHER]
    assert body["inbound"][0]["anchor_text"] == "see our services"
    assert body["inbound_template_links"] == 1
    assert [row["url"] for row in body["outbound"]] == [OTHER]
    assert body["outbound_template_links"] == 0


def test_template_links_are_counted_by_occurrence(client, db, client_a, admin_user):
    """A nav repeated twice on a page is two links, and the total should say so."""
    db.add(_snapshot(client_a.id, PAGE))
    db.add(
        _link(client_a.id, "https://example.com/", PAGE, anchor="Services", template=True)
    )
    db.commit()
    link = db.query(FactCrawlInternalLink).one()
    link.occurrences = 3
    db.commit()

    body = client.get(
        f"/site-crawl/page?url={PAGE}", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["inbound"] == []
    assert body["inbound_template_links"] == 3


def test_page_detail_includes_the_raw_schema(client, db, client_a, admin_user):
    """Seeing the markup is the point — a type list does not let you check it."""
    payload = {"@type": "Service", "name": "Carbon fibre design"}
    db.add(_snapshot(client_a.id, PAGE))
    db.add(_schema(client_a.id, PAGE, "Service", raw=payload))
    db.add(_schema(client_a.id, PAGE, None, error="invalid JSON: bad token"))
    db.commit()

    body = client.get(
        f"/site-crawl/page?url={PAGE}", headers=client_header(client_a.id, admin_user.email)
    ).json()

    blocks = body["schema_blocks"]
    assert len(blocks) == 2
    # Broken markup first.
    assert blocks[0]["parse_error"] is not None
    assert any(b["raw"] == payload for b in blocks)


def test_page_detail_for_an_uncrawled_url_is_not_an_error(client, db, client_a, admin_user):
    body = client.get(
        "/site-crawl/page?url=https://example.com/nope",
        headers=client_header(client_a.id, admin_user.email),
    ).json()

    assert body["found"] is False


# --- Structured data --------------------------------------------------------


def test_schema_view_separates_the_three_kinds_of_gap(client, db, client_a, admin_user):
    boilerplate = "https://example.com/boilerplate"
    broken = "https://example.com/broken"
    db.add(_snapshot(client_a.id, PAGE))
    db.add(_snapshot(client_a.id, boilerplate))
    db.add(_snapshot(client_a.id, broken))
    db.add(_schema(client_a.id, PAGE, "Service", raw={"@type": "Service"}))
    db.add(_schema(client_a.id, boilerplate, "WebPage", raw={"@type": "WebPage"}))
    db.add(_schema(client_a.id, broken, None, error="invalid JSON"))
    db.commit()

    body = client.get(
        "/site-crawl/schema", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert body["pages_with_descriptive_schema"] == 1
    issues = {row["url"]: row["issue"] for row in body["gaps"]}
    assert issues[broken] == "invalid"
    assert issues[boilerplate] == "boilerplate_only"
    # Unparseable markup sorts first — it reads as done and nothing can use it.
    assert body["gaps"][0]["url"] == broken


# --- Pagination and filters -------------------------------------------------


def test_pagination_urls_are_recognised():
    """
    Real examples from aquamanleakdetection.com, which had 21 of 143 pages like
    this. A slug that merely contains the word "page" is not pagination.
    """
    from app.api.routers.site_crawl import is_pagination_url

    assert is_pagination_url("https://x.com/blog/page/2")
    assert is_pagination_url("https://x.com/author/someone/page/9")
    assert is_pagination_url("https://x.com/blog/category/news/page/2/")
    assert is_pagination_url("https://x.com/?paged=3")
    assert is_pagination_url("https://x.com/p/12")

    assert not is_pagination_url("https://x.com/blog")
    assert not is_pagination_url("https://x.com/blog/creating-a-better-landing-page")
    assert not is_pagination_url("https://x.com/2026/")


def test_pagination_is_hidden_by_default(client, db, client_a, admin_user):
    db.add(_snapshot(client_a.id, PAGE))
    db.add(_snapshot(client_a.id, "https://example.com/blog/page/2"))
    db.commit()
    headers = client_header(client_a.id, admin_user.email)

    default = client.get("/site-crawl/pages", headers=headers).json()
    shown = client.get("/site-crawl/pages?pagination=show", headers=headers).json()
    only = client.get("/site-crawl/pages?pagination=only", headers=headers).json()

    assert [row["url"] for row in default["items"]] == [PAGE]
    assert default["pagination_pages"] == 1
    assert len(shown["items"]) == 2
    assert [row["url"] for row in only["items"]] == ["https://example.com/blog/page/2"]


def test_filters_narrow_the_list_and_report_the_match_count(client, db, client_a, admin_user):
    orphan = _snapshot(client_a.id, OTHER)
    orphan.inbound_editorial_links = 0
    orphan.word_count = 120
    broken = _snapshot(client_a.id, "https://example.com/gone", indexable=False)
    broken.status_code = 404
    db.add(_snapshot(client_a.id, PAGE))
    db.add(orphan)
    db.add(broken)
    db.commit()
    headers = client_header(client_a.id, admin_user.email)

    def urls(qs: str) -> list[str]:
        body = client.get(f"/site-crawl/pages?{qs}", headers=headers).json()
        assert body["matched_pages"] == len(body["items"])
        return [row["url"] for row in body["items"]]

    assert urls("links=orphan") == [OTHER]
    assert urls("words=thin") == [OTHER]
    assert urls("status=error") == ["https://example.com/gone"]
    assert urls("indexable=no") == ["https://example.com/gone"]
    assert sorted(urls("indexable=yes")) == sorted([PAGE, OTHER])


def test_filters_combine(client, db, client_a, admin_user):
    thin_orphan = _snapshot(client_a.id, OTHER)
    thin_orphan.inbound_editorial_links = 0
    thin_orphan.word_count = 100
    linked_thin = _snapshot(client_a.id, "https://example.com/short")
    linked_thin.word_count = 100
    db.add(thin_orphan)
    db.add(linked_thin)
    db.commit()

    body = client.get(
        "/site-crawl/pages?words=thin&links=orphan",
        headers=client_header(client_a.id, admin_user.email),
    ).json()

    assert [row["url"] for row in body["items"]] == [OTHER]


def test_the_view_carries_the_last_crawl_note(client, db, client_a, admin_user):
    """
    "Not found" with nothing to explain it is what made the sitemap stat
    impossible to act on. The crawl's own summary now travels with the numbers.
    """
    from datetime import date as date_cls

    from app.models.job import SyncJob, SyncJobStatus

    db.add(_snapshot(client_a.id, PAGE))
    db.add(
        SyncJob(
            id=uuid4(),
            client_id=client_a.id,
            source="site_crawl",
            start_date=date_cls.today(),
            end_date=date_cls.today(),
            status=SyncJobStatus.SUCCESSFUL,
            error_message="Crawled 20 pages, sitemap 80 URLs via https://x.com/sitemap_index.xml",
        )
    )
    db.commit()

    body = client.get(
        "/site-crawl/pages", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert "sitemap 80 URLs" in body["last_crawl_note"]


def test_pages_are_listed_in_url_order(client, db, client_a, admin_user):
    """Severity ordering scattered related pages and led with deliberate redirects."""
    for path in ("/services/roofing", "/about", "/services/siding", "/blog/post"):
        db.add(_snapshot(client_a.id, f"https://example.com{path}"))
    db.commit()

    body = client.get(
        "/site-crawl/pages", headers=client_header(client_a.id, admin_user.email)
    ).json()

    assert [row["url"] for row in body["items"]] == [
        "https://example.com/about",
        "https://example.com/blog/post",
        "https://example.com/services/roofing",
        "https://example.com/services/siding",
    ]
