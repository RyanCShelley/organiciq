"""
A redirecting URL variant must not be reported as a page defect.

`/guide` 301s to `/guide/` on a normal WordPress site. URL normalization strips
trailing slashes, so both collapse to one key — and SE Ranking's audit crawled
only the redirecting variant for Element Six, so GSC demand for the served page
lands on a row that says "non-indexable". Reported naively, a site doing the
correct thing is told its best page is broken.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.ingestion.seranking.publish_audit import _pick_better_row
from app.models.crawl import FactCrawlPageSnapshot, StagingSerAuditPage
from app.services.lever_engine import detect_technical_signal

PAGE = "https://element6composites.com/the-ultimate-guide-to-carbon-fiber-design-and-application"


def _snapshot(client_id, *, raw_url, indexable, status, canonical=None, redirect_url=None):
    return FactCrawlPageSnapshot(
        id=uuid4(),
        client_id=client_id,
        snapshot_date=date.today(),
        raw_url=raw_url,
        # Normalization strips the trailing slash, so both variants share this.
        normalized_url=PAGE,
        indexable=indexable,
        status_code=status,
        canonical_url=canonical,
        redirect_url=redirect_url,
        redirect_count=0,
        inbound_internal_links=1,
        word_count=0,
        in_sitemap=False,
        title="",
        description="",
    )


def test_a_redirecting_variant_is_not_a_non_indexable_finding(client_a):
    """This is the Element Six case: the only crawled row is the 301."""
    redirecting = _snapshot(
        client_a.id,
        raw_url=PAGE,
        indexable=False,
        status=301,
        redirect_url=f"{PAGE}/",
    )

    signal = detect_technical_signal(PAGE, redirecting)

    assert signal is None or signal.audit_signal != "non_indexable"


def test_a_genuinely_noindexed_page_is_still_reported(client_a):
    """The real defect must survive the fix: 200 and deliberately not indexable."""
    noindexed = _snapshot(client_a.id, raw_url=f"{PAGE}/", indexable=False, status=200)

    signal = detect_technical_signal(PAGE, noindexed)

    assert signal is not None
    assert signal.audit_signal == "non_indexable"


def test_a_broken_redirect_is_still_reported(client_a):
    """A 3xx pointing at a 4xx is a real problem and keeps its own signal."""
    dead_url = "https://element6composites.com/gone"
    broken = _snapshot(
        client_a.id, raw_url=PAGE, indexable=False, status=301, redirect_url=dead_url
    )
    dead = _snapshot(client_a.id, raw_url=dead_url, indexable=False, status=404)
    dead.normalized_url = dead_url

    signal = detect_technical_signal(PAGE, broken, crawl_by_url={dead_url: dead})

    assert signal is not None
    assert signal.audit_signal == "broken_redirect"


def test_a_redirect_chain_is_still_reported(client_a):
    chained = _snapshot(client_a.id, raw_url=PAGE, indexable=False, status=301)
    chained.redirect_count = 4

    signal = detect_technical_signal(PAGE, chained)

    assert signal is not None
    assert signal.audit_signal == "redirect_chain"


def test_publish_keeps_the_served_page_when_both_variants_are_crawled(client_a):
    """
    The fact table holds one row per normalized URL, so when the audit returns
    both variants the served page has to be the one that survives.
    """
    def staging(url, status, words):
        return StagingSerAuditPage(
            id=uuid4(),
            client_id=client_a.id,
            raw_url=url,
            normalized_url=PAGE,
            indexable=status == 200,
            status_code=status,
            word_count=words,
            inbound_internal_links=1,
        )

    redirecting = staging(PAGE, 301, 0)
    served = staging(f"{PAGE}/", 200, 2400)

    assert _pick_better_row(redirecting, served) is served
    assert _pick_better_row(served, redirecting) is served


def test_a_page_canonicalised_to_another_url_reports_as_such(client_a):
    """
    Real case from SMA: /blog/schema.org-vs-... is a 200 that permits indexing
    and canonicalises to /blog/schema-org-vs-... (dot versus hyphen).

    SE Ranking folds this into "not indexable". Keeping the two apart is more
    useful — the page is not broken, it is a duplicate pointing at its original,
    and "canonicalised elsewhere" is the finding someone can act on.
    """
    url = "https://smamarketing.com/blog/schema.org-vs-google-structured-data-rich-results"
    canonical = "https://smamarketing.com/blog/schema-org-vs-google-structured-data-rich-results"

    row = _snapshot(client_a.id, raw_url=url, indexable=True, status=200, canonical=canonical)
    row.normalized_url = url

    signal = detect_technical_signal(url, row)

    assert signal is not None
    assert signal.audit_signal == "canonical_elsewhere"
