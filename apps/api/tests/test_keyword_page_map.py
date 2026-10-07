"""Recording which page owns each term.

This upsert had no test while it ran one SELECT per entry — a bulk save of
a hundred keywords was a hundred round trips. Collapsing that to a single
query introduced a case the per-entry version got right by accident: the
same keyword twice in one payload used to find the row it had just added,
because each lookup went back to the database.
"""

from __future__ import annotations

from app.models.decision import KeywordPageMap
from app.schemas import KeywordPageMapEntry
from app.services.decisions import upsert_keyword_page_map


def _rows(db, client_id) -> list[KeywordPageMap]:
    return (
        db.query(KeywordPageMap)
        .filter(KeywordPageMap.client_id == client_id)
        .order_by(KeywordPageMap.keyword)
        .all()
    )


def test_a_mapping_is_recorded(db, client_a):
    upsert_keyword_page_map(
        db,
        client_a.id,
        [KeywordPageMapEntry(keyword="leak detection", page_url="https://x.test/leaks")],
    )
    rows = _rows(db, client_a.id)
    assert [(r.keyword, r.page_url) for r in rows] == [
        ("leak detection", "https://x.test/leaks")
    ]


def test_saving_again_updates_rather_than_duplicates(db, client_a):
    upsert_keyword_page_map(
        db, client_a.id, [KeywordPageMapEntry(keyword="slab leak", page_url="https://x.test/a")]
    )
    upsert_keyword_page_map(
        db, client_a.id, [KeywordPageMapEntry(keyword="slab leak", page_url="https://x.test/b")]
    )
    rows = _rows(db, client_a.id)
    assert len(rows) == 1
    assert rows[0].page_url == "https://x.test/b"


def test_case_is_not_a_difference(db, client_a):
    """A watchlist entry and a Search Console query differ in case far more
    often than in substance."""
    upsert_keyword_page_map(
        db, client_a.id, [KeywordPageMapEntry(keyword="Pool Leak", page_url="https://x.test/a")]
    )
    upsert_keyword_page_map(
        db, client_a.id, [KeywordPageMapEntry(keyword="pool leak", page_url="https://x.test/b")]
    )
    rows = _rows(db, client_a.id)
    assert [r.keyword for r in rows] == ["pool leak"]
    assert rows[0].page_url == "https://x.test/b"


def test_the_same_keyword_twice_in_one_payload_is_one_row(db, client_a):
    """The batched lookup only sees what was in the table when it ran, so a
    repeat within the payload has to be matched against what this call has
    already added."""
    upsert_keyword_page_map(
        db,
        client_a.id,
        [
            KeywordPageMapEntry(keyword="hydrostatic test", page_url="https://x.test/a"),
            KeywordPageMapEntry(keyword="hydrostatic test", page_url="https://x.test/b"),
        ],
    )
    rows = _rows(db, client_a.id)
    assert len(rows) == 1, "a repeated keyword must not insert twice"
    assert rows[0].page_url == "https://x.test/b", "the last one wins"


def test_a_blank_keyword_is_skipped(db, client_a):
    upsert_keyword_page_map(
        db,
        client_a.id,
        [
            KeywordPageMapEntry(keyword="   ", page_url="https://x.test/a"),
            KeywordPageMapEntry(keyword="real", page_url="https://x.test/b"),
        ],
    )
    assert [r.keyword for r in _rows(db, client_a.id)] == ["real"]


def test_no_page_yet_is_recorded_as_a_decision(db, client_a):
    """Null means nobody owns this term, which is a thing someone decided —
    not a row that failed to save."""
    upsert_keyword_page_map(
        db, client_a.id, [KeywordPageMapEntry(keyword="unowned", page_url=None, note="to write")]
    )
    rows = _rows(db, client_a.id)
    assert rows[0].page_url is None
    assert rows[0].note == "to write"


def test_one_clients_map_is_not_another_s(db, client_a, client_b):
    upsert_keyword_page_map(
        db, client_a.id, [KeywordPageMapEntry(keyword="shared term", page_url="https://a.test/")]
    )
    upsert_keyword_page_map(
        db, client_b.id, [KeywordPageMapEntry(keyword="shared term", page_url="https://b.test/")]
    )
    assert [r.page_url for r in _rows(db, client_a.id)] == ["https://a.test/"]
    assert [r.page_url for r in _rows(db, client_b.id)] == ["https://b.test/"]
