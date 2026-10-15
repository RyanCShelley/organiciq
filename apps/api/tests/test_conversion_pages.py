"""Declaring which pages are the offer.

The model and the engine's use of it were both written. Nothing could
write to it: no route, no schema, no screen, and the table was empty for
every client. So every conversion action fell back to guessing from URL
fragments, and ACCTek — whose offer is /contact-us — was told for months
to add links to /contact, which does not exist.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routers.admin import list_conversion_pages, replace_conversion_pages
from app.schemas import ConversionPageIn


def _save(db, client, entries):
    return replace_conversion_pages(payload=entries, client=client, _=None, db=db)


def test_a_declared_page_is_stored(db, client_a):
    out = _save(
        db,
        client_a,
        [ConversionPageIn(normalized_url="https://acctek.com/contact-us", label="Contact", is_primary=True)],
    )
    assert [(r.normalized_url, r.label, r.is_primary) for r in out] == [
        ("https://acctek.com/contact-us", "Contact", True)
    ]


def test_saving_again_replaces_rather_than_appends(db, client_a):
    """The screen edits the whole list, so the save has to mean the whole
    list — otherwise removing a page is impossible."""
    _save(db, client_a, [ConversionPageIn(normalized_url="https://x.test/a", label="A")])
    out = _save(db, client_a, [ConversionPageIn(normalized_url="https://x.test/b", label="B")])
    assert [r.normalized_url for r in out] == ["https://x.test/b"]


def test_an_empty_list_clears_them(db, client_a):
    _save(db, client_a, [ConversionPageIn(normalized_url="https://x.test/a", label="A")])
    assert _save(db, client_a, []) == []


def test_two_primaries_are_refused(db, client_a):
    """The engine falls back to the primary offer when a page's stage
    matches nothing, so two of them is a silent coin toss."""
    with pytest.raises(HTTPException) as caught:
        _save(
            db,
            client_a,
            [
                ConversionPageIn(normalized_url="https://x.test/a", label="A", is_primary=True),
                ConversionPageIn(normalized_url="https://x.test/b", label="B", is_primary=True),
            ],
        )
    assert caught.value.status_code == 400


def test_the_same_url_twice_is_refused(db, client_a):
    with pytest.raises(HTTPException) as caught:
        _save(
            db,
            client_a,
            [
                ConversionPageIn(normalized_url="https://x.test/a", label="A"),
                ConversionPageIn(normalized_url="https://x.test/a", label="Again"),
            ],
        )
    assert caught.value.status_code == 400


def test_one_clients_offers_are_not_another_s(db, client_a, client_b):
    _save(db, client_a, [ConversionPageIn(normalized_url="https://a.test/c", label="A")])
    _save(db, client_b, [ConversionPageIn(normalized_url="https://b.test/c", label="B")])
    assert [r.normalized_url for r in list_conversion_pages(client=client_a, _=None, db=db)] == [
        "https://a.test/c"
    ]
    assert [r.normalized_url for r in list_conversion_pages(client=client_b, _=None, db=db)] == [
        "https://b.test/c"
    ]


def test_the_primary_sorts_first(db, client_a):
    out = _save(
        db,
        client_a,
        [
            ConversionPageIn(normalized_url="https://x.test/z", label="Zeta"),
            ConversionPageIn(normalized_url="https://x.test/a", label="Alpha", is_primary=True),
        ],
    )
    assert [r.label for r in out] == ["Alpha", "Zeta"]


# ── What the engine does with them ──




