"""A client whose site is a folder of a larger domain.

Robinson Unmanned lives at robinsonheli.com/unmanned. Before this, the only
place to put that was `domain` — which is read as a host everywhere, so the
path was silently joined onto GA4 and GSC paths that already contained it and
produced /unmanned/unmanned/page. The scope now has its own field, and each
pipeline has to honour it.
"""

from __future__ import annotations

import pytest

from app.core.urls import normalize_landing_page, normalize_path_prefix, url_in_scope
from app.ingestion.crawler.fetch import _start_url


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("unmanned", "/unmanned"),
        ("/unmanned", "/unmanned"),
        ("/Unmanned/", "/unmanned"),
        ("https://robinsonheli.com/unmanned/", "/unmanned"),
        ("https://robinsonheli.com/unmanned?x=1", "/unmanned"),
        ("/a/b/", "/a/b"),
        ("/", None),
        ("", None),
        (None, None),
    ],
)
def test_a_scope_is_normalized_to_match_how_urls_are_stored(raw, expected):
    assert normalize_path_prefix(raw) == expected


@pytest.mark.parametrize(
    "url,inside",
    [
        ("https://robinsonheli.com/unmanned", True),
        ("https://robinsonheli.com/unmanned/", True),
        ("https://robinsonheli.com/unmanned/products", True),
        ("https://robinsonheli.com/unmanned/a/b/c", True),
        # A sibling that merely starts with the same letters is not inside it.
        ("https://robinsonheli.com/unmanned-sales", False),
        ("https://robinsonheli.com/unmannedx", False),
        ("https://robinsonheli.com/helicopters", False),
        ("https://robinsonheli.com/", False),
        ("", False),
    ],
)
def test_scope_matches_on_a_path_boundary(url, inside):
    assert url_in_scope(url, "/unmanned") is inside


def test_no_scope_admits_everything():
    assert url_in_scope("https://example.com/anything", None) is True


def test_a_path_left_in_the_domain_can_no_longer_double():
    """The bug this feature exists to prevent."""
    assert (
        normalize_landing_page("/unmanned/products", "robinsonheli.com/unmanned")
        == "https://robinsonheli.com/unmanned/products"
    )


def test_the_crawl_starts_inside_the_folder():
    """Starting at the parent homepage would find nothing the scope accepts."""
    assert _start_url("robinsonheli.com", "/unmanned") == "https://robinsonheli.com/unmanned"
    assert _start_url("robinsonheli.com", None) == "https://robinsonheli.com/"


# --- The pipelines ----------------------------------------------------------

from datetime import date, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from uuid import uuid4  # noqa: E402

from app.ingestion.ga4.publish import publish_ga4  # noqa: E402
from app.ingestion.gsc.publish import publish_gsc_pages  # noqa: E402
from app.models.config import ChannelRule, OrganicChannel  # noqa: E402
from app.models.ga4 import FactGa4Traffic, StagingGa4Traffic  # noqa: E402
from app.models.gsc import FactGscPage, StagingGscPage  # noqa: E402
from app.models.job import SyncJob, SyncJobStatus  # noqa: E402

TODAY = date.today()


def _scoped(db, client, prefix="/unmanned", domain="robinsonheli.com"):
    client.domain = domain
    client.path_prefix = prefix
    db.commit()
    return client


def _job(db, client_id, source):
    job = SyncJob(
        id=uuid4(),
        client_id=client_id,
        source=source,
        start_date=TODAY - timedelta(days=1),
        end_date=TODAY,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    db.flush()
    return job


def test_ga4_keeps_only_the_client_s_own_folder(db, client_a):
    """The GA4 property is the parent brand's, so most rows are not this client."""
    _scoped(db, client_a)
    db.add(
        ChannelRule(
            match_source="google",
            match_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            priority=20,
            active=True,
        )
    )
    job = _job(db, client_a.id, "ga4")
    for path in ("/unmanned", "/unmanned/products", "/unmanned-sales", "/helicopters", "/"):
        db.add(
            StagingGa4Traffic(
                job_id=job.id,
                client_id=client_a.id,
                raw={},
                date=TODAY,
                landing_page=path,
                session_source="google",
                session_medium="organic",
                sessions=Decimal("5"),
                active_users=Decimal("5"),
                views=Decimal("5"),
            )
        )
    db.commit()

    publish_ga4(db, job)

    kept = sorted(
        row.normalized_url
        for row in db.query(FactGa4Traffic).filter(FactGa4Traffic.client_id == client_a.id).all()
    )
    assert kept == [
        "https://robinsonheli.com/unmanned",
        "https://robinsonheli.com/unmanned/products",
    ]


def test_gsc_keeps_only_the_client_s_own_folder(db, client_a):
    """A domain property reports every sibling brand's pages too."""
    _scoped(db, client_a)
    job = _job(db, client_a.id, "gsc")
    for path in ("/unmanned/", "/unmanned/drones", "/unmanned-sales", "/helicopters/r44"):
        url = f"https://robinsonheli.com{path}"
        db.add(
            StagingGscPage(
                job_id=job.id,
                client_id=client_a.id,
                raw={},
                date=TODAY,
                page=url,
                country="usa",
                device="DESKTOP",
                impressions=Decimal("10"),
                clicks=Decimal("1"),
                ctr=Decimal("0.1"),
                average_position=Decimal("4.2"),
            )
        )
    db.commit()

    publish_gsc_pages(db, job)

    kept = sorted(
        row.normalized_url
        for row in db.query(FactGscPage).filter(FactGscPage.client_id == client_a.id).all()
    )
    assert kept == [
        "https://robinsonheli.com/unmanned",
        "https://robinsonheli.com/unmanned/drones",
    ]


def test_an_unscoped_client_still_keeps_everything(db, client_a):
    """The scope is rare; every other client must be unaffected by it."""
    client_a.domain = "example.com"
    client_a.path_prefix = None
    db.commit()
    job = _job(db, client_a.id, "gsc")
    for path in ("/a", "/b/c"):
        db.add(
            StagingGscPage(
                job_id=job.id,
                client_id=client_a.id,
                raw={},
                date=TODAY,
                page=f"https://example.com{path}",
                country="usa",
                device="DESKTOP",
                impressions=Decimal("1"),
                clicks=Decimal("0"),
                ctr=Decimal("0"),
                average_position=Decimal("9"),
            )
        )
    db.commit()

    publish_gsc_pages(db, job)

    assert db.query(FactGscPage).filter(FactGscPage.client_id == client_a.id).count() == 2
