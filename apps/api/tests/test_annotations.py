"""Annotations CSV import + light causal impact."""

from datetime import date

from app.models.annotation import AnnotationResult
from app.models.client import Client
from app.schemas import AnnotationCreate
from app.services import annotations as annotation_service
from app.services.annotations import import_annotations_csv, measure_annotation_impact


CSV = """date,annotation_type,growth_action,description,page_url,success_metric,completed_at,measurement_start_date,measurement_end_date,result,notes,baseline_sessions,baseline_leads,baseline_impressions,baseline_clicks,post_sessions,post_leads,post_impressions,post_clicks
2025-06-01,growth_action,serp_ctr,Rewrote title tags,https://example.com/services,CTR,2025-06-05,2025-06-06,2025-07-05,not_yet_measured,hist,1000,10,40000,800,1200,14,48000,1000
2025-03-01,manual_note,,Kickoff note,,,,,,,
"""


def test_import_annotations_csv_computes_impact(db, client_a: Client):
    result = import_annotations_csv(db, client_a, CSV)
    assert result["errors"] == [], result["errors"]
    assert result["created"] == 2

    rows = annotation_service.list_annotations(db, client_a.id)
    assert len(rows) == 2
    improved = next(r for r in rows if "Rewrote" in r.description)
    assert improved.result == AnnotationResult.IMPROVED
    assert improved.impact_summary_json["deltas"]["leads_change_pct"] == 40.0
    assert improved.impact_summary_json["frame"] == "pre_vs_post_window"


def test_create_annotation_with_stored_metrics(db, client_a: Client):
    row = annotation_service.create_annotation(
        db,
        client_a,
        AnnotationCreate(
            date=date(2025, 7, 1),
            annotation_type="technical_change",
            description="Fixed crawl errors",
            baseline_metrics_json={"sessions": 500, "leads": 5},
            post_action_metrics_json={"sessions": 480, "leads": 4},
            measurement_start_date=date(2025, 7, 2),
            measurement_end_date=date(2025, 8, 1),
            completed_at=date(2025, 7, 1),
        ),
    )
    summary = measure_annotation_impact(db, client_a, row)
    assert summary["deltas"]["leads_change_pct"] == -20.0
    assert summary["suggested_result"] == AnnotationResult.DECLINED.value
    assert row.result == AnnotationResult.DECLINED
