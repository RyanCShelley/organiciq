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


def test_page_work_measurement_does_not_include_sibling_pages_or_other_clients(db,client_a,client_b):
    from app.models.ga4 import FactGa4Traffic
    from app.models.config import OrganicChannel
    from app.services.annotations import _window_metrics
    day=date(2026,9,30)
    for c,url,sessions in [(client_a,'https://clienta.example/services/seo',10),(client_a,'https://clienta.example/services/seo-audit',500),(client_a,'https://clienta.example/',20),(client_b,'https://clienta.example/services/seo',900)]:
        db.add(FactGa4Traffic(client_id=c.id,date=day,raw_url=url,normalized_url=url,channel=OrganicChannel.ORGANIC_SEARCH,sessions=sessions))
    db.commit()
    for page,count in [('https://clienta.example/services/seo',10),('https://clienta.example/',20)]:
        assert _window_metrics(db,client_a.id,start=day,end=day,page_url=page,lead_events=[])['sessions']==count
    missing=_window_metrics(db,client_a.id,start=date(2026,1,1),end=date(2026,1,2),page_url=None,lead_events=[])
    assert missing['sessions'] is None and missing['clicks'] is None


def test_future_window_does_not_cache_partial_results(db,client_a):
    from app.models.annotation import Annotation,AnnotationType
    row=Annotation(client_id=client_a.id,date=date(2026,10,1),annotation_type=AnnotationType.GROWTH_ACTION,
        description='Verified page change',completed_at=date(2026,10,1),measurement_start_date=date(2026,10,2),
        measurement_end_date=date(2026,10,29),baseline_metrics_json={'sessions':100})
    db.add(row);db.flush()
    summary=measure_annotation_impact(db,client_a,row,today=date(2026,10,18))
    assert row.result==AnnotationResult.NOT_YET_MEASURED
    assert summary['post']=={} and not row.post_action_metrics_json
    assert summary['deltas']=={} and 'finish' in summary['measurement_note']


def test_past_window_requires_complete_source_coverage(db,client_a):
    from app.models.annotation import Annotation,AnnotationType
    row=Annotation(client_id=client_a.id,date=date(2026,8,1),annotation_type=AnnotationType.GROWTH_ACTION,
        description='Verified page change',completed_at=date(2026,8,1),measurement_start_date=date(2026,8,2),measurement_end_date=date(2026,8,29))
    db.add(row);db.flush()
    summary=measure_annotation_impact(db,client_a,row,today=date(2026,10,18))
    assert row.result==AnnotationResult.NOT_ENOUGH_DATA
    assert 'comparison-period' in summary['measurement_note']
    assert not row.post_action_metrics_json


def test_completed_window_is_measured_after_both_sources_finish(db,client_a):
    from app.models.annotation import Annotation,AnnotationType
    from app.models.job import SyncJob,SyncJobStatus
    from app.models.gsc import FactGscPage
    row=Annotation(client_id=client_a.id,date=date(2026,8,1),annotation_type=AnnotationType.GROWTH_ACTION,
        description='Verified page change',completed_at=date(2026,8,1),measurement_start_date=date(2026,8,2),measurement_end_date=date(2026,8,29))
    db.add(row)
    for day,clicks in [(date(2026,7,31),10),(date(2026,8,29),20)]:
        db.add(FactGscPage(client_id=client_a.id,date=day,raw_url='https://clienta.example/',normalized_url='https://clienta.example/',clicks=clicks,impressions=100))
    for source in ('ga4','gsc_pages'):
        db.add(SyncJob(client_id=client_a.id,source=source,start_date=date(2026,7,1),end_date=date(2026,8,29),fact_watermark=date(2026,8,29),status=SyncJobStatus.SUCCESSFUL))
    db.commit()
    summary=measure_annotation_impact(db,client_a,row,today=date(2026,10,18))
    assert summary['deltas']['clicks_change_pct']==100
    assert row.post_action_metrics_json['clicks']==20
