"""Moving a client's stored URLs to a new host.

The risk is not the rewrite, it is the collision: a page can already exist under
both hosts at the same grain, and merging must not invent numbers.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.gsc import FactGscPage
from app.rehost_client_urls import rehost_client_urls

OLD = "smamarketing.net"
NEW = "smamarketing.com"


def _gsc(client_id, url, *, impressions, clicks, position, on=None, country="usa"):
    return FactGscPage(
        id=uuid4(),
        client_id=client_id,
        date=on or date(2026, 9, 1),
        raw_url=url,
        normalized_url=url,
        country=country,
        device="DESKTOP",
        impressions=Decimal(impressions),
        clicks=Decimal(clicks),
        ctr=Decimal(clicks) / Decimal(impressions) if impressions else Decimal(0),
        average_position=Decimal(position),
    )


def test_urls_move_to_the_new_host(db, client_a):
    db.add(_gsc(client_a.id, f"https://{OLD}/pricing", impressions=100, clicks=5, position=8))
    db.commit()

    counts = rehost_client_urls(
        db, client_id=str(client_a.id), old_host=OLD, new_host=NEW, apply=True
    )
    db.commit()

    row = db.query(FactGscPage).filter(FactGscPage.client_id == client_a.id).one()
    assert row.normalized_url == f"https://{NEW}/pricing"
    assert counts["rewritten"] == 1
    # raw_url records what the source reported, and that is still true.
    assert row.raw_url == f"https://{OLD}/pricing"


def test_a_dry_run_writes_nothing(db, client_a):
    db.add(_gsc(client_a.id, f"https://{OLD}/pricing", impressions=100, clicks=5, position=8))
    db.commit()

    counts = rehost_client_urls(db, client_id=str(client_a.id), old_host=OLD, new_host=NEW)
    db.rollback()

    row = db.query(FactGscPage).filter(FactGscPage.client_id == client_a.id).one()
    assert row.normalized_url == f"https://{OLD}/pricing"
    assert counts["rewritten"] == 1


def test_colliding_rows_merge_with_weighted_metrics(db, client_a):
    """
    Impressions and clicks add. Position and CTR are derived — adding them would
    invent a number, so they are recomputed against the combined impressions.
    """
    db.add(_gsc(client_a.id, f"https://{OLD}/guide", impressions=100, clicks=10, position=20))
    db.add(_gsc(client_a.id, f"https://{NEW}/guide", impressions=300, clicks=30, position=4))
    db.commit()

    counts = rehost_client_urls(
        db, client_id=str(client_a.id), old_host=OLD, new_host=NEW, apply=True
    )
    db.commit()

    rows = db.query(FactGscPage).filter(FactGscPage.client_id == client_a.id).all()
    assert len(rows) == 1, "the old-host row folds into its twin"
    merged = rows[0]
    assert merged.normalized_url == f"https://{NEW}/guide"
    assert int(merged.impressions) == 400
    assert int(merged.clicks) == 40
    # (4*300 + 20*100) / 400 = 8
    assert float(merged.average_position) == 8.0
    assert float(merged.ctr) == 0.1
    assert counts["merged"] == 1


def test_rows_at_a_different_grain_do_not_merge(db, client_a):
    """Same URL, different day: two facts, not one."""
    db.add(
        _gsc(
            client_a.id,
            f"https://{OLD}/guide",
            impressions=100,
            clicks=1,
            position=9,
            on=date(2026, 9, 1),
        )
    )
    db.add(
        _gsc(
            client_a.id,
            f"https://{NEW}/guide",
            impressions=100,
            clicks=1,
            position=9,
            on=date(2026, 9, 2),
        )
    )
    db.commit()

    rehost_client_urls(db, client_id=str(client_a.id), old_host=OLD, new_host=NEW, apply=True)
    db.commit()

    rows = db.query(FactGscPage).filter(FactGscPage.client_id == client_a.id).all()
    assert len(rows) == 2
    assert {row.normalized_url for row in rows} == {f"https://{NEW}/guide"}


def test_the_client_domain_is_updated(db, client_a):
    client_a.domain = OLD
    db.commit()

    rehost_client_urls(db, client_id=str(client_a.id), old_host=OLD, new_host=NEW, apply=True)
    db.commit()
    db.refresh(client_a)

    assert client_a.domain == NEW


def test_another_clients_rows_are_untouched(db, client_a, client_b):
    db.add(_gsc(client_a.id, f"https://{OLD}/x", impressions=10, clicks=1, position=5))
    db.add(_gsc(client_b.id, f"https://{OLD}/x", impressions=10, clicks=1, position=5))
    db.commit()

    rehost_client_urls(db, client_id=str(client_a.id), old_host=OLD, new_host=NEW, apply=True)
    db.commit()

    other = db.query(FactGscPage).filter(FactGscPage.client_id == client_b.id).one()
    assert other.normalized_url == f"https://{OLD}/x"


def test_running_it_twice_changes_nothing_the_second_time(db, client_a):
    db.add(_gsc(client_a.id, f"https://{OLD}/x", impressions=10, clicks=1, position=5))
    db.commit()

    rehost_client_urls(db, client_id=str(client_a.id), old_host=OLD, new_host=NEW, apply=True)
    db.commit()
    again = rehost_client_urls(
        db, client_id=str(client_a.id), old_host=OLD, new_host=NEW, apply=True
    )
    db.commit()

    assert again["rewritten"] == 0
    assert again["merged"] == 0
