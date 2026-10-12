"""Which pages carry a structured-data type, and which do not.

The coverage tab counted blocks per type and stopped, so "we have Article
markup" could not be checked against "on which pages" — the question
somebody validating or troubleshooting it actually has.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from tests.conftest import client_header

TODAY = date(2026, 10, 12)


def _page(db: Session, client: Client, url: str, *, indexable: bool = True, types=()):
    db.add(
        FactCrawlPageSnapshot(
            client_id=client.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=TODAY,
            raw_url=url,
            normalized_url=url,
            indexable=indexable,
            title=f"Title for {url}",
            word_count=500,
        )
    )
    for schema_type in types:
        db.add(
            FactCrawlPageSchema(
                client_id=client.id,
                snapshot_date=TODAY,
                normalized_url=url,
                syntax="json-ld",
                schema_type=schema_type,
                raw={"@type": schema_type},
            )
        )


def _get(client, client_a, admin_user, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(
        f"/site-crawl/schema/pages?{qs}",
        headers=client_header(client_a.id, admin_user.email),
    )


def test_it_lists_the_pages_that_carry_a_type(client, db: Session, client_a: Client, admin_user):
    _page(db, client_a, "https://x.test/a", types=("Article",))
    _page(db, client_a, "https://x.test/b", types=("Article", "FAQPage"))
    _page(db, client_a, "https://x.test/c", types=("WebSite",))
    db.commit()

    body = _get(client, client_a, admin_user, type="Article").json()
    assert body["total"] == 2
    assert [p["url"] for p in body["pages"]] == [
        "https://x.test/a",
        "https://x.test/b",
    ]
    assert body["pages"][0]["title"] == "Title for https://x.test/a"


def test_it_lists_the_pages_missing_a_type(client, db: Session, client_a: Client, admin_user):
    _page(db, client_a, "https://x.test/a", types=("Article",))
    _page(db, client_a, "https://x.test/c", types=("WebSite",))
    db.commit()

    body = _get(client, client_a, admin_user, type="Article", has="no").json()
    assert [p["url"] for p in body["pages"]] == ["https://x.test/c"]


def test_a_noindex_page_is_on_neither_list(client, db: Session, client_a: Client, admin_user):
    # A page search engines are told to ignore is not a structured-data gap.
    _page(db, client_a, "https://x.test/hidden", indexable=False, types=())
    _page(db, client_a, "https://x.test/a", types=("Article",))
    db.commit()

    has = _get(client, client_a, admin_user, type="Article").json()
    missing = _get(client, client_a, admin_user, type="Article", has="no").json()
    urls = {p["url"] for p in has["pages"]} | {p["url"] for p in missing["pages"]}
    assert "https://x.test/hidden" not in urls


def test_the_type_match_ignores_case(client, db: Session, client_a: Client, admin_user):
    _page(db, client_a, "https://x.test/a", types=("Article",))
    db.commit()
    assert _get(client, client_a, admin_user, type="article").json()["total"] == 1


def test_a_type_nothing_carries_comes_back_empty_not_missing(
    client, db: Session, client_a: Client, admin_user
):
    _page(db, client_a, "https://x.test/a", types=("Article",))
    db.commit()
    body = _get(client, client_a, admin_user, type="Recipe").json()
    assert body["total"] == 0 and body["pages"] == []
