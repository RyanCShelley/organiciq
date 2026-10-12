"""The results loop: what became of last month's actions.

`engine_actions` has had `before_value`, `after_value` and `result` since the
table was created and nothing ever wrote them, so "Last month's results" was
empty by construction.

Two properties carry the weight. Every metric is read **as-of a date**, which
is what makes a `before` recoverable for an action prescribed before this
code existed. And an action with no `before` is never judged, because a
verdict made against nothing is worse than an empty row.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.decision import EngineAction, MonthlyRecord
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.seranking import FactSerRanking
from app.services.results import (
    capture_before,
    check_due,
    measure,
    previous_results,
    verdict,
)

SEPT = "2026-09"
PRESCRIBED = date(2026, 9, 30)
CHECK_ON = date(2026, 10, 28)


def _record(db: Session, client: Client, **over) -> MonthlyRecord:
    action = {
        "action_uid": f"{client.slug}-{SEPT}-s1",
        "slot": 1,
        "id": "V-1",
        "title": "Put the term in the title",
        "target_url": "https://x.test/seo",
        "term": "seo agency",
        "metric": "Term position",
        "metric_key": "term_position",
        "check_on": CHECK_ON.isoformat(),
    }
    action.update(over)
    row = MonthlyRecord(
        client_id=client.id,
        month=SEPT,
        run_saved_at=datetime.now(timezone.utc),
        data_through=PRESCRIBED,
        constraint_name="visibility",
        held_since=SEPT,
        confidence="medium",
        record={"actions": [action], "incidents": []},
    )
    db.add(row)
    db.commit()
    return row


def _rank(db: Session, client: Client, when: date, position: float):
    """The tracked position on a day, replacing any already stored for it."""
    row = (
        db.query(FactSerRanking)
        .filter(
            FactSerRanking.client_id == client.id,
            FactSerRanking.date == when,
            FactSerRanking.keyword_id == f"k-{when}",
        )
        .one_or_none()
    )
    if row is None:
        row = FactSerRanking(
            client_id=client.id,
            date=when,
            site_engine_id="1",
            keyword_id=f"k-{when}",
            keyword="seo agency",
        )
        db.add(row)
    row.position = Decimal(str(position))
    db.commit()


# ── Measuring as-of a date ──────────────────────────────────────────────────


def test_a_metric_reads_as_it_stood_not_as_it_stands(db: Session, client_a: Client):
    _rank(db, client_a, PRESCRIBED, 18.0)
    _rank(db, client_a, CHECK_ON, 6.0)

    # This is the property that makes September recoverable in November.
    assert measure(db, client_a, "term_position", term="seo agency", as_of=PRESCRIBED).value == 18.0
    assert measure(db, client_a, "term_position", term="seo agency", as_of=CHECK_ON).value == 6.0


def test_a_missing_reading_says_why(db: Session, client_a: Client):
    found = measure(db, client_a, "term_position", term="seo agency", as_of=PRESCRIBED)
    assert found.value is None
    assert "no tracked position" in (found.missing or "")


def test_a_decision_action_is_not_measured(db: Session, client_a: Client):
    found = measure(db, client_a, "decision", as_of=PRESCRIBED)
    assert found.value is None
    assert "settles a decision" in (found.missing or "")


def test_the_page_lead_rate_needs_a_declared_lead_event(db: Session, client_a: Client):
    found = measure(
        db, client_a, "page_lead_rate", url="https://x.test/seo", as_of=CHECK_ON
    )
    assert found.value is None
    assert "counted as a lead" in (found.missing or "")


def test_the_page_lead_rate_is_leads_over_managed_sessions(db: Session, client_a: Client):
    db.add(
        ConversionDefinition(
            client_id=client_a.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            active=True,
        )
    )
    for day in range(3):
        when = CHECK_ON - timedelta(days=day)
        db.add(
            FactGa4Traffic(
                client_id=client_a.id,
                date=when,
                raw_url="https://x.test/seo",
                normalized_url="https://x.test/seo",
                channel=OrganicChannel.ORGANIC_SEARCH,
                sessions=100,
            )
        )
        db.add(
            FactGa4Event(
                client_id=client_a.id,
                date=when,
                raw_url="https://x.test/seo",
                normalized_url="https://x.test/seo",
                channel=OrganicChannel.ORGANIC_SEARCH,
                event_name="generate_lead",
                event_count=2,
            )
        )
    db.commit()
    found = measure(db, client_a, "page_lead_rate", url="https://x.test/seo", as_of=CHECK_ON)
    assert found.value == pytest.approx(2.0)


# ── Verdicts ────────────────────────────────────────────────────────────────


def test_position_improves_by_going_down():
    assert verdict("term_position", 18.0, 6.0) == "improved"
    assert verdict("term_position", 6.0, 18.0) == "worse"
    # Every other metric reads the other way.
    assert verdict("page_clicks", 100.0, 400.0) == "improved"
    assert verdict("page_clicks", 400.0, 100.0) == "worse"


def test_a_move_too_small_to_mean_anything_is_no_change():
    assert verdict("term_position", 4.0, 3.95) == "no_change"


def test_nothing_to_compare_is_waiting():
    assert verdict("term_position", None, 4.0) == "waiting"
    assert verdict("term_position", 4.0, None) == "waiting"


# ── The loop ────────────────────────────────────────────────────────────────


def test_a_before_can_be_captured_after_the_fact(db: Session, client_a: Client):
    """The reason September's five actions are not already lost."""
    record = _record(db, client_a)
    _rank(db, client_a, PRESCRIBED, 18.0)

    assert capture_before(db, client_a, record) == 1
    row = db.query(EngineAction).one()
    assert float(row.before_value) == 18.0


def test_capturing_twice_does_not_rewrite_the_first_reading(
    db: Session, client_a: Client
):
    record = _record(db, client_a)
    _rank(db, client_a, PRESCRIBED, 18.0)
    capture_before(db, client_a, record)
    _rank(db, client_a, PRESCRIBED, 11.0)

    assert capture_before(db, client_a, record) == 0
    assert float(db.query(EngineAction).one().before_value) == 18.0


def test_an_action_is_not_judged_before_its_check_date(db: Session, client_a: Client):
    record = _record(db, client_a)
    _rank(db, client_a, PRESCRIBED, 18.0)
    capture_before(db, client_a, record)
    _rank(db, client_a, CHECK_ON, 6.0)

    assert check_due(db, client_a, today=CHECK_ON - timedelta(days=1)) == []
    assert db.query(EngineAction).one().after_value is None


def test_an_action_with_no_before_is_left_alone(db: Session, client_a: Client):
    _record(db, client_a)
    # No ranking on the prescribed date, so nothing to compare against.
    _rank(db, client_a, CHECK_ON, 6.0)
    assert check_due(db, client_a, today=CHECK_ON) == []


def test_the_check_writes_a_verdict(db: Session, client_a: Client):
    record = _record(db, client_a)
    _rank(db, client_a, PRESCRIBED, 18.0)
    capture_before(db, client_a, record)
    _rank(db, client_a, CHECK_ON, 6.0)

    judged = check_due(db, client_a, today=CHECK_ON)
    assert len(judged) == 1
    row = db.query(EngineAction).one()
    assert float(row.before_value) == 18.0
    assert float(row.after_value) == 6.0
    assert row.result == "improved"


def test_a_judged_action_is_not_judged_twice(db: Session, client_a: Client):
    record = _record(db, client_a)
    _rank(db, client_a, PRESCRIBED, 18.0)
    capture_before(db, client_a, record)
    _rank(db, client_a, CHECK_ON, 6.0)
    check_due(db, client_a, today=CHECK_ON)

    _rank(db, client_a, CHECK_ON + timedelta(days=5), 2.0)
    assert check_due(db, client_a, today=CHECK_ON + timedelta(days=5)) == []
    assert float(db.query(EngineAction).one().after_value) == 6.0


def test_previous_results_say_when_nobody_recorded_shipping_it(
    db: Session, client_a: Client
):
    record = _record(db, client_a)
    _rank(db, client_a, PRESCRIBED, 18.0)
    capture_before(db, client_a, record)
    _rank(db, client_a, CHECK_ON, 6.0)
    check_due(db, client_a, today=CHECK_ON)

    rows = previous_results(db, client_a, "2026-10", previous=SEPT)
    assert len(rows) == 1
    assert rows[0]["before"] == 18.0 and rows[0]["after"] == 6.0
    assert rows[0]["result"] == "improved"
    # A verdict on work nobody recorded doing is an accusation, not a
    # measurement — so the row says what is not known about it.
    assert rows[0]["shipped"] is False

    db.query(EngineAction).one().shipped_on = date(2026, 10, 1)
    db.commit()
    assert previous_results(db, client_a, "2026-10", previous=SEPT)[0]["shipped"] is True


def test_an_unjudged_action_still_appears_as_waiting(db: Session, client_a: Client):
    _record(db, client_a)
    rows = previous_results(db, client_a, "2026-10", previous=SEPT)
    assert rows[0]["result"] == "waiting"
    assert rows[0]["before"] is None


def test_a_record_written_before_metric_key_existed_is_still_measurable(
    db: Session, client_a: Client
):
    """September's record has no `metric_key` on its actions.

    Falling back to "decision" made every one of them unmeasurable, which
    defeats the whole point of being able to measure backwards. The action's
    own id says what it is judged on.
    """
    from app.services.results import metric_key_for

    assert metric_key_for({"id": "V-1"}) == "term_position"
    assert metric_key_for({"id": "T-3"}) == "engagement_rate"
    assert metric_key_for({"id": "L-1"}) == "page_lead_rate"
    assert metric_key_for({"id": "V-6"}) == "decision"
    # A stored key always wins, so a check months later uses the key the
    # action was actually prescribed with.
    assert metric_key_for({"id": "V-1", "metric_key": "page_clicks"}) == "page_clicks"

    record = _record(db, client_a)
    for action in record.record["actions"]:
        del action["metric_key"]
    record.record = dict(record.record)
    db.commit()

    _rank(db, client_a, PRESCRIBED, 18.0)
    assert capture_before(db, client_a, record) == 1
    assert float(db.query(EngineAction).one().before_value) == 18.0


# ── What production found ───────────────────────────────────────────────────


def test_position_zero_is_not_a_position(db: Session, client_a: Client):
    """SE Ranking writes 0 for "not in the results we checked".

    `_rank` in triage_signals has always known this and the results reader
    did not, so every before value came out as position zero — and 2,810 of
    SMA's 2,934 ranking rows are zeroes.
    """
    _rank(db, client_a, PRESCRIBED, 0.0)
    found = measure(db, client_a, "term_position", term="seo agency", as_of=PRESCRIBED)
    assert found.value is None
    assert found.unranked is True
    assert "outside the top 100" in (found.missing or "")

    _rank(db, client_a, PRESCRIBED, 101.0)
    assert measure(db, client_a, "term_position", term="seo agency", as_of=PRESCRIBED).unranked


def test_no_reading_is_different_from_not_ranking(db: Session, client_a: Client):
    found = measure(db, client_a, "term_position", term="seo agency", as_of=PRESCRIBED)
    assert found.value is None
    # Nothing was measured at all, which is not the same as measured-and-absent.
    assert found.unranked is False


def test_nothing_measurable_leaves_no_row_behind(db: Session, client_a: Client):
    """The row used to be created before the metric was read."""
    record = _record(db, client_a)
    assert capture_before(db, client_a, record) == 0
    assert db.query(EngineAction).count() == 0


def test_entering_the_rankings_counts_as_improved(db: Session, client_a: Client):
    """Where almost every visibility action starts.

    The term was off the rankings when it was prescribed, so there is no
    before to compare. That is a real starting state, not a gap, and the
    measurement being as-of a date is what lets the check establish it.
    """
    record = _record(db, client_a)
    _rank(db, client_a, PRESCRIBED, 0.0)
    assert capture_before(db, client_a, record) == 0

    _rank(db, client_a, CHECK_ON, 34.0)
    judged = check_due(db, client_a, today=CHECK_ON)
    assert len(judged) == 1
    assert judged[0].result == "improved"
    assert judged[0].before_value is None
    assert float(judged[0].after_value) == 34.0


def test_still_unranked_at_the_check_is_not_an_improvement(
    db: Session, client_a: Client
):
    _record(db, client_a)
    _rank(db, client_a, PRESCRIBED, 0.0)
    _rank(db, client_a, CHECK_ON, 0.0)
    assert check_due(db, client_a, today=CHECK_ON) == []
