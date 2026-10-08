"""What the engine computes has to reach the wire.

The engine is thoroughly tested and the response was not tested at all, so
a field could be added to `DiagnoseResult`, used by a CLI that reads the
dataclass directly, and never serialised — leaving the screen with nothing
while every test passed and the command-line check looked right.

That is exactly what happened. `growth_actions`, `constraint`,
`blocking_findings` and `source_freshness` were all computed and all
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
        growth_actions=[
            _finding(
                "1b", demand=402.0, demand_unit="sessions / mo", estimated_minutes=15,
            )
        ],
        blocking_findings=[_finding("1b", gate="tracking")],
    )
    response = serialize_diagnose(result)

    for name in ("growth_actions", "blocking_findings"):
        served = getattr(response, name)
        assert len(served) == 1, f"{name} was computed but did not reach the response"
        assert served[0].evidence_json["rule_id"] == "1b"

    assert response.source_freshness == {"search_console": "2026-09-22"}


def test_a_growth_action_arrives_with_what_the_screen_prints(db, client_a):
    """Every row shows a count, its unit and the minutes. A row carrying
    none of them renders as em dashes, which is how this was spotted."""
    end = date.today()
    result = diagnose(db, client_a, from_date=end - timedelta(days=29), to_date=end)
    for action in serialize_diagnose(result).growth_actions:
        evidence = action.evidence_json
        assert evidence.get("estimated_minutes") is not None
        if evidence.get("precondition"):
            continue
        assert evidence.get("demand") is not None
        assert evidence.get("demand_unit")


def test_only_valued_work_reaches_the_growth_actions(db, client_a):
    """The legacy `recommended_actions` list is gone. What it used to carry
    — report-only findings with nothing counted — must not reappear here."""
    end = date.today()
    response = serialize_diagnose(
        diagnose(db, client_a, from_date=end - timedelta(days=29), to_date=end)
    )
    assert "recommended_actions" not in DiagnoseResponse.model_fields
    unvalued = [
        row
        for row in response.growth_actions
        if row.evidence_json.get("expected_leads_monthly") is None
    ]
    assert unvalued == [], "a growth action without a lead estimate reached the response"
