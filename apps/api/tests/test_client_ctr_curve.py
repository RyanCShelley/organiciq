"""A click-through curve built from one client's own data.

The shared curve is an aggregate across the whole web. A local service company
and a B2B manufacturer do not earn the same share at position three, so
judging either against the average mis-states the gap in both directions.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.decisions.client_ctr_curve import (
    MIN_IMPRESSIONS_FOR_OWN_CURVE,
    build_client_ctr_curve,
    ctr_at,
)
from app.decisions.ctr_curve import expected_ctr_percent
from app.models.gsc import FactGscPage

END = date.today()
PERIOD = (END - timedelta(days=29), END)


def _row(db, client_id, position, impressions, clicks, url="https://example.com/a"):
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_id,
            date=END,
            raw_url=f"{url}-{uuid4().hex[:6]}",
            normalized_url=f"{url}-{uuid4().hex[:6]}",
            country="",
            device="",
            impressions=Decimal(impressions),
            clicks=Decimal(clicks),
            ctr=Decimal(clicks) / Decimal(impressions),
            average_position=Decimal(position),
        )
    )


def test_a_client_with_history_gets_its_own_curve(db, client_a):
    _row(db, client_a.id, 3, 2000, 400)  # 20% at position 3
    db.commit()

    curve, source = build_client_ctr_curve(db, client_a.id, PERIOD)

    assert source == "client"
    assert round(curve[3], 1) == 20.0
    # Which is nothing like the shared curve for that position.
    assert round(expected_ctr_percent(3), 1) != 20.0


def test_too_little_history_falls_back_to_the_shared_curve(db, client_a):
    """A curve fitted to two hundred impressions is noise wearing a name."""
    _row(db, client_a.id, 3, 200, 100)
    db.commit()

    curve, source = build_client_ctr_curve(db, client_a.id, PERIOD)

    assert (curve, source) == ({}, "default")
    assert 200 < MIN_IMPRESSIONS_FOR_OWN_CURVE


def test_a_thin_position_is_not_taken_from_the_client(db, client_a):
    """One busy position must not define the whole shape."""
    _row(db, client_a.id, 2, 5000, 1000)
    _row(db, client_a.id, 9, 20, 15)  # absurd 75%, far too thin to trust
    db.commit()

    curve, source = build_client_ctr_curve(db, client_a.id, PERIOD)

    assert source == "client"
    assert 2 in curve
    assert 9 not in curve


def test_an_unknown_position_falls_through_to_the_shared_curve():
    curve = {3: 20.0}

    assert ctr_at(3, curve) == 20.0
    assert ctr_at(7, curve) == expected_ctr_percent(7)


def test_no_period_means_the_shared_curve(db, client_a):
    assert build_client_ctr_curve(db, client_a.id, None) == ({}, "default")
