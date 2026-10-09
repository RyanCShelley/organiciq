"""Recording which page owns each term.

This upsert had no test while it ran one SELECT per entry — a bulk save of
a hundred keywords was a hundred round trips. Collapsing that to a single
query introduced a case the per-entry version got right by accident: the
same keyword twice in one payload used to find the row it had just added,
because each lookup went back to the database.
"""

from __future__ import annotations

from app.models.decision import KeywordTarget
from app.schemas import KeywordTargetEntry
from app.services.decisions import upsert_keyword_page_map


def _rows(db, client_id) -> list[KeywordTarget]:
    return (
        db.query(KeywordTarget)
        .filter(KeywordTarget.client_id == client_id)
        .order_by(KeywordTarget.keyword)
        .all()
    )


def test_a_mapping_is_recorded(db, client_a):
    upsert_keyword_page_map(
        db,
        client_a.id,
        [KeywordTargetEntry(keyword="leak detection", target_url="https://x.test/leaks")],
    )
    rows = _rows(db, client_a.id)
    assert [(r.keyword, r.target_url) for r in rows] == [
        ("leak detection", "https://x.test/leaks")
    ]


def test_saving_again_updates_rather_than_duplicates(db, client_a):
    upsert_keyword_page_map(
        db, client_a.id, [KeywordTargetEntry(keyword="slab leak", target_url="https://x.test/a")]
    )
    upsert_keyword_page_map(
        db, client_a.id, [KeywordTargetEntry(keyword="slab leak", target_url="https://x.test/b")]
    )
    rows = _rows(db, client_a.id)
    assert len(rows) == 1
    assert rows[0].target_url == "https://x.test/b"


def test_case_is_not_a_difference(db, client_a):
    """A watchlist entry and a Search Console query differ in case far more
    often than in substance."""
    upsert_keyword_page_map(
        db, client_a.id, [KeywordTargetEntry(keyword="Pool Leak", target_url="https://x.test/a")]
    )
    upsert_keyword_page_map(
        db, client_a.id, [KeywordTargetEntry(keyword="pool leak", target_url="https://x.test/b")]
    )
    rows = _rows(db, client_a.id)
    assert [r.keyword for r in rows] == ["pool leak"]
    assert rows[0].target_url == "https://x.test/b"


def test_the_same_keyword_twice_in_one_payload_is_one_row(db, client_a):
    """The batched lookup only sees what was in the table when it ran, so a
    repeat within the payload has to be matched against what this call has
    already added."""
    upsert_keyword_page_map(
        db,
        client_a.id,
        [
            KeywordTargetEntry(keyword="hydrostatic test", target_url="https://x.test/a"),
            KeywordTargetEntry(keyword="hydrostatic test", target_url="https://x.test/b"),
        ],
    )
    rows = _rows(db, client_a.id)
    assert len(rows) == 1, "a repeated keyword must not insert twice"
    assert rows[0].target_url == "https://x.test/b", "the last one wins"


def test_a_blank_keyword_is_skipped(db, client_a):
    upsert_keyword_page_map(
        db,
        client_a.id,
        [
            KeywordTargetEntry(keyword="   ", target_url="https://x.test/a"),
            KeywordTargetEntry(keyword="real", target_url="https://x.test/b"),
        ],
    )
    assert [r.keyword for r in _rows(db, client_a.id)] == ["real"]


def test_no_page_yet_is_recorded_as_a_decision(db, client_a):
    """Null means nobody owns this term, which is a thing someone decided —
    not a row that failed to save."""
    upsert_keyword_page_map(
        db, client_a.id, [KeywordTargetEntry(keyword="unowned", target_url=None, note="to write")]
    )
    rows = _rows(db, client_a.id)
    assert rows[0].target_url is None
    assert rows[0].note == "to write"


def test_one_clients_map_is_not_another_s(db, client_a, client_b):
    upsert_keyword_page_map(
        db, client_a.id, [KeywordTargetEntry(keyword="shared term", target_url="https://a.test/")]
    )
    upsert_keyword_page_map(
        db, client_b.id, [KeywordTargetEntry(keyword="shared term", target_url="https://b.test/")]
    )
    assert [r.target_url for r in _rows(db, client_a.id)] == ["https://a.test/"]
    assert [r.target_url for r in _rows(db, client_b.id)] == ["https://b.test/"]


def test_the_new_fields_survive_a_round_trip(db, client_a):
    """Decision 2 scores a keyword-page pair as a product, so a zero on any
    factor removes the candidate. Two of the five live on this row: `fit`
    needs the declared target, `w_group` needs to know which group is the
    priority one. A field that is written and not read back is the same as
    a field that was never there."""
    from app.schemas import KeywordTargetEntry
    from app.services.decisions import upsert_keyword_page_map

    upsert_keyword_page_map(
        db,
        client_a.id,
        [
            KeywordTargetEntry(
                keyword="ai seo agency",
                target_url="https://x/capabilities/geo",
                term_role="primary",
                group_name="GEO",
                priority=True,
            )
        ],
    )

    row = (
        db.query(KeywordTarget)
        .filter(KeywordTarget.client_id == client_a.id)
        .one()
    )
    assert row.target_url == "https://x/capabilities/geo"
    assert row.term_role == "primary"
    assert row.group_name == "GEO"
    assert row.priority is True
    # Written through the human path, so it is a decision rather than a
    # proposal — the engine reads confirmed rows only.
    assert row.source == "confirmed"


def test_a_role_nobody_set_stays_unset(db, client_a):
    """Null is not secondary. A rule that wants a primary term must be able
    to tell "nobody has said" from "somebody said no"."""
    from app.schemas import KeywordTargetEntry
    from app.services.decisions import upsert_keyword_page_map

    upsert_keyword_page_map(
        db,
        client_a.id,
        [KeywordTargetEntry(keyword="plain term", target_url="https://x/a")],
    )
    row = db.query(KeywordTarget).filter(KeywordTarget.client_id == client_a.id).one()
    assert row.term_role is None
    assert row.priority is False
