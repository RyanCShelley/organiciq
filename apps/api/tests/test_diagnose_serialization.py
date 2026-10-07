"""What the engine computes has to reach the wire.

The engine is thoroughly tested and the response was not tested at all, so
a field could be added to `DiagnoseResult`, used by a CLI that reads the
dataclass directly, and never serialised — leaving the screen with nothing
while every test passed and the command-line check looked right.

That is exactly what happened. `growth_actions`, `below_floor_actions`,
`unvalued_actions` and `source_freshness` were all computed and all
dropped by `serialize_diagnose`, which names its fields one by one.
"""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta

from app.schemas import DiagnoseResponse
from app.services.decision_serialization import serialize_diagnose
from app.models.decision import DiagnosticLayer
from app.services.decision_types import DiagnoseResult, LeverFinding
from app.services.lever_engine import diagnose

#: Carried on the dataclass for callers that read it in-process, and
#: deliberately not sent: `coverage` is a diagnostic for the CLIs.
NOT_SERVED = {"coverage"}


def test_every_field_the_engine_computes_is_sent():
    """A hand-written serialiser forgets. This notices."""
    computed = {f.name for f in dataclasses.fields(DiagnoseResult)} - NOT_SERVED
    sent = set(DiagnoseResponse.model_fields)
    missing = sorted(computed - sent)
    assert missing == [], (
        "DiagnoseResult carries these and the response cannot express them: "
        + ", ".join(missing)
    )


def _finding(rule_id: str, **evidence) -> LeverFinding:
    return LeverFinding(
        rule_key=f"k-{rule_id}-{len(evidence)}-{sorted(evidence)}",
        lever="conversion_path",
        stage=DiagnosticLayer.CONVERSION,
        diagnosis="d",
        recommended_action="a",
        success_metric="m",
        evidence_json={"rule_id": rule_id, **evidence},
        baseline_metrics_json={},
        impact=10.0,
        confidence=50.0,
        urgency=50.0,
        effort=50.0,
        priority_score=10.0,
    )


def test_the_serialiser_actually_populates_them():
    """Declaring the field is half of it: `serialize_diagnose` names every
    field by hand, so one can be declared and still never assigned.

    The lists are built here rather than taken from a run, because on a
    client with no data every one of them is empty and the comparison
    passes against itself. The first version of this test did exactly that
    and went green with the assignment deleted.
    """
    result = DiagnoseResult(
        ready=True,
        message=None,
        readiness={"search_console": True},
        formula="",
        source_freshness={"search_console": "2026-09-22"},
        growth_actions=[_finding("1b", expected_leads_monthly=2.04, estimated_minutes=15)],
        below_floor_actions=[_finding("1b", expected_leads_monthly=0.01, below_floor=True)],
        unvalued_actions=[_finding("1b", value_error="no raw lead estimate")],
    )
    response = serialize_diagnose(result)

    for name in ("growth_actions", "below_floor_actions", "unvalued_actions"):
        served = getattr(response, name)
        assert len(served) == 1, f"{name} was computed but did not reach the response"
        assert served[0].evidence_json["rule_id"] == "1b"

    assert response.source_freshness == {"search_console": "2026-09-22"}


def test_a_growth_action_arrives_with_what_the_screen_prints(db, client_a):
    """Every row shows leads a month and minutes. A row carrying neither
    renders as two em dashes, which is how this was spotted."""
    end = date.today()
    result = diagnose(db, client_a, from_date=end - timedelta(days=29), to_date=end)
    for action in serialize_diagnose(result).growth_actions:
        assert action.evidence_json.get("expected_leads_monthly") is not None
        assert action.evidence_json.get("estimated_minutes") is not None


def test_growth_actions_are_not_the_legacy_promotion(db, client_a):
    """They were read as if they were. `recommended_actions` is the older
    impact-and-confidence list and carries report-only work."""
    end = date.today()
    response = serialize_diagnose(
        diagnose(db, client_a, from_date=end - timedelta(days=29), to_date=end)
    )
    assert "growth_actions" in DiagnoseResponse.model_fields
    unvalued_in_legacy = [
        row
        for row in response.recommended_actions
        if row.evidence_json.get("expected_leads_monthly") is None
    ]
    valued_only = [
        row
        for row in response.growth_actions
        if row.evidence_json.get("expected_leads_monthly") is None
    ]
    assert valued_only == [], (
        "a growth action without a lead estimate reached the response; "
        f"the legacy list has {len(unvalued_in_legacy)} such rows, which is why "
        "the two are separate"
    )


def test_freshness_is_read_from_the_rows_not_the_watermark(db, client_a):
    """A watermark is a claim; a fact is an observation, and here they
    disagree. ACC Tek's Search Console sync returns no rows and still
    advances its watermark, so the watermark said 7 Oct while the newest
    row was 24 Sep. Reporting the claim made the engine's own narrowing of
    the window look arbitrary."""
    from datetime import date as date_cls
    from decimal import Decimal
    from uuid import uuid4

    from app.models.gsc import FactGscPage
    from app.models.job import DataWatermark, ValidationStatus

    newest_fact = date_cls(2026, 9, 24)
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=newest_fact,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            country="",
            device="",
            impressions=Decimal("10"),
            clicks=Decimal("1"),
            ctr=Decimal("0.1"),
            average_position=Decimal("5"),
        )
    )
    db.add(
        DataWatermark(
            id=uuid4(),
            client_id=client_a.id,
            source="gsc_pages",
            fact_through_date=date_cls(2026, 10, 7),
            validation_status=ValidationStatus.PASSED,
        )
    )
    db.commit()

    result = diagnose(
        db, client_a, from_date=date_cls(2026, 9, 1), to_date=date_cls(2026, 10, 7)
    )
    assert result.source_freshness["search_console"] == newest_fact.isoformat(), (
        "freshness must come from the newest row, not the watermark's claim"
    )
