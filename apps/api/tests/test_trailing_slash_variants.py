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






