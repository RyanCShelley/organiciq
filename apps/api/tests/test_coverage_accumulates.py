"""A rule that runs per page runs on some pages and skips others.

3a evaluated 78 of SMA's 80 pages and the coverage report said
`page_not_crawled`, because the last two pages it looked at had no crawl
row and each call overwrote the one before. "A rule that cannot run must
never look like a rule that found nothing" cuts both ways, and this was
the other way round.
"""

from __future__ import annotations

from app.decisions.triggers.coverage import Coverage, SkipReason


def test_a_rule_that_ran_anywhere_reads_as_having_run():
    coverage = Coverage()
    coverage.ran("3a")
    coverage.skipped("3a", SkipReason.PAGE_NOT_CRAWLED)
    row = coverage.rules["3a"]
    assert row.ran is True
    assert row.skips == {"page_not_crawled": 1}


def test_skips_are_counted_not_replaced():
    coverage = Coverage()
    for _ in range(3):
        coverage.skipped("3b", SkipReason.PAGE_NOT_CRAWLED)
    coverage.skipped("3b", SkipReason.NO_LEAD_RATE)
    assert coverage.rules["3b"].skips == {"page_not_crawled": 3, "no_lead_rate": 1}


def test_findings_accumulate_across_pages():
    coverage = Coverage()
    coverage.ran("3a", findings=1)
    coverage.ran("3a", findings=1)
    coverage.ran("3a")
    assert coverage.rules["3a"].findings == 2


def test_a_rule_that_only_skipped_still_reads_as_skipped():
    coverage = Coverage()
    coverage.skipped("1c", SkipReason.NO_DEPTH_DATA)
    row = coverage.rules["1c"]
    assert row.ran is False
    assert row.as_dict()["status"] == "skipped:no_depth_data"


def test_the_report_carries_both():
    coverage = Coverage()
    coverage.ran("3a", findings=2)
    coverage.skipped("3a", SkipReason.PAGE_NOT_CRAWLED)
    entry = coverage.as_list()[0]
    assert entry["status"] == "ran"
    assert entry["findings"] == 2
    assert entry["skipped_on"] == {"page_not_crawled": 1}
