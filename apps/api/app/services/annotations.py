"""Annotation CRUD, CSV import, and light causal impact measurement."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.annotation import Annotation, AnnotationResult, AnnotationType
from app.models.client import Client
from app.models.config import ConversionDefinition
from app.models.decision import GrowthAction
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage
from app.schemas import AnnotationCreate, AnnotationUpdate

MEANINGFUL_CHANGE_PCT = 5.0


def list_annotations(db: Session, client_id: UUID, *, limit: int = 500) -> list[Annotation]:
    return (
        db.query(Annotation)
        .filter(Annotation.client_id == client_id)
        .order_by(Annotation.date.desc(), Annotation.created_at.desc())
        .limit(limit)
        .all()
    )


def get_annotation(db: Session, client_id: UUID, annotation_id: UUID) -> Annotation | None:
    return (
        db.query(Annotation)
        .filter(Annotation.id == annotation_id, Annotation.client_id == client_id)
        .one_or_none()
    )


def _coerce_create(payload: AnnotationCreate) -> dict[str, Any]:
    data = payload.model_dump()
    data["annotation_type"] = AnnotationType(payload.annotation_type)
    data["growth_action"] = (
        GrowthAction(payload.growth_action) if payload.growth_action else None
    )
    data["result"] = AnnotationResult(payload.result)
    return data


def _coerce_update(payload: AnnotationUpdate) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    if "annotation_type" in data and data["annotation_type"] is not None:
        data["annotation_type"] = AnnotationType(data["annotation_type"])
    if "growth_action" in data:
        data["growth_action"] = (
            GrowthAction(data["growth_action"]) if data["growth_action"] else None
        )
    if "result" in data and data["result"] is not None:
        data["result"] = AnnotationResult(data["result"])
    return data


def create_annotation(db: Session, client: Client, payload: AnnotationCreate) -> Annotation:
    data = _coerce_create(payload)
    row = Annotation(client_id=client.id, **data)
    db.add(row)
    db.flush()
    measure_annotation_impact(db, client, row, persist=False)
    db.commit()
    db.refresh(row)
    return row


def update_annotation(
    db: Session,
    client: Client,
    annotation_id: UUID,
    payload: AnnotationUpdate,
) -> Annotation | None:
    row = get_annotation(db, client.id, annotation_id)
    if row is None:
        return None
    for key, value in _coerce_update(payload).items():
        setattr(row, key, value)
    measure_annotation_impact(db, client, row, persist=False)
    db.commit()
    db.refresh(row)
    return row


def delete_annotation(db: Session, client_id: UUID, annotation_id: UUID) -> bool:
    row = get_annotation(db, client_id, annotation_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def _parse_enum(enum_cls, value: str | None, default=None):
    if value is None or not str(value).strip():
        return default
    normalized = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return enum_cls(normalized)
    except ValueError:
        aliases = {
            AnnotationType: {
                "growth": AnnotationType.GROWTH_ACTION,
                "content": AnnotationType.CONTENT_UPDATED,
                "tech": AnnotationType.TECHNICAL_CHANGE,
                "note": AnnotationType.MANUAL_NOTE,
            },
            AnnotationResult: {
                "improved": AnnotationResult.IMPROVED,
                "declined": AnnotationResult.DECLINED,
                "flat": AnnotationResult.NO_MEANINGFUL_CHANGE,
                "none": AnnotationResult.NO_MEANINGFUL_CHANGE,
                "pending": AnnotationResult.NOT_YET_MEASURED,
            },
        }
        mapped = aliases.get(enum_cls, {}).get(normalized)
        if mapped is not None:
            return mapped
        if default is not None:
            return default
        raise


def import_annotations_csv(db: Session, client: Client, csv_text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    created = 0
    errors: list[dict[str, Any]] = []
    rows: list[Annotation] = []

    for index, raw in enumerate(reader, start=2):
        try:
            ann_date = _parse_date(raw.get("date") or raw.get("annotation_date"))
            if ann_date is None:
                raise ValueError("date is required (YYYY-MM-DD)")
            ann_type = _parse_enum(
                AnnotationType,
                raw.get("annotation_type") or raw.get("type"),
                AnnotationType.MANUAL_NOTE,
            )
            growth = None
            if raw.get("growth_action"):
                growth = _parse_enum(GrowthAction, raw.get("growth_action"))
            description = (raw.get("description") or raw.get("notes") or "").strip()
            if not description:
                raise ValueError("description is required")

            baseline = {
                k.replace("baseline_", ""): _maybe_number(raw.get(k))
                for k in (
                    "baseline_sessions",
                    "baseline_leads",
                    "baseline_impressions",
                    "baseline_clicks",
                    "baseline_lead_rate",
                )
                if raw.get(k)
            }
            post = {
                k.replace("post_", "").replace("post_action_", ""): _maybe_number(raw.get(k))
                for k in (
                    "post_sessions",
                    "post_leads",
                    "post_impressions",
                    "post_clicks",
                    "post_lead_rate",
                    "post_action_sessions",
                    "post_action_leads",
                )
                if raw.get(k)
            }
            # normalize keys
            baseline_metrics = {k: v for k, v in baseline.items() if v is not None}
            post_metrics = {}
            for k, v in post.items():
                if v is None:
                    continue
                key = k.replace("action_", "")
                post_metrics[key] = v

            result = _parse_enum(
                AnnotationResult,
                raw.get("result"),
                AnnotationResult.NOT_YET_MEASURED,
            )
            if result is None:
                result = AnnotationResult.NOT_YET_MEASURED

            row = Annotation(
                client_id=client.id,
                date=ann_date,
                annotation_type=ann_type,
                growth_action=growth,
                description=description,
                page_url=(raw.get("page_url") or raw.get("url") or "").strip() or None,
                success_metric=(raw.get("success_metric") or "").strip() or None,
                teamwork_task_id=(raw.get("teamwork_task_id") or "").strip() or None,
                completed_at=_parse_date(raw.get("completed_at")),
                measurement_start_date=_parse_date(raw.get("measurement_start_date")),
                measurement_end_date=_parse_date(raw.get("measurement_end_date")),
                baseline_metrics_json=baseline_metrics,
                post_action_metrics_json=post_metrics,
                result=result,
                notes=(raw.get("notes") or "").strip() or None,
            )
            db.add(row)
            rows.append(row)
            created += 1
        except Exception as exc:  # noqa: BLE001 - collect row errors for upload UX
            errors.append({"row": index, "error": str(exc)})

    db.flush()
    for row in rows:
        measure_annotation_impact(db, client, row, persist=False)
    db.commit()
    return {"created": created, "errors": errors}


def _maybe_number(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    if not text:
        return None
    return float(text)


def _lead_event_names(db: Session, client_id: UUID) -> list[str]:
    rows = (
        db.query(ConversionDefinition.event_name)
        .filter(
            ConversionDefinition.client_id == client_id,
            ConversionDefinition.active.is_(True),
            ConversionDefinition.conversion_type == "lead",
        )
        .all()
    )
    return [row[0] for row in rows]


def _window_metrics(
    db: Session,
    client_id: UUID,
    *,
    start: date,
    end: date,
    page_url: str | None,
    lead_events: list[str],
) -> dict[str, float | None]:
    traffic_q = db.query(
        func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
    ).filter(
        FactGa4Traffic.client_id == client_id,
        FactGa4Traffic.date >= start,
        FactGa4Traffic.date <= end,
    )
    if page_url:
        traffic_q = traffic_q.filter(FactGa4Traffic.landing_page.contains(_path_hint(page_url)))
    sessions = float(traffic_q.scalar() or 0)

    leads: float | None = None
    if lead_events:
        leads_q = db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0)).filter(
            FactGa4Event.client_id == client_id,
            FactGa4Event.date >= start,
            FactGa4Event.date <= end,
            FactGa4Event.event_name.in_(lead_events),
        )
        if page_url:
            leads_q = leads_q.filter(FactGa4Event.landing_page.contains(_path_hint(page_url)))
        leads = float(leads_q.scalar() or 0)

    gsc_q = db.query(
        func.coalesce(func.sum(FactGscPage.impressions), 0),
        func.coalesce(func.sum(FactGscPage.clicks), 0),
    ).filter(
        FactGscPage.client_id == client_id,
        FactGscPage.date >= start,
        FactGscPage.date <= end,
    )
    if page_url:
        gsc_q = gsc_q.filter(FactGscPage.normalized_url.contains(_path_hint(page_url)))
    impressions, clicks = gsc_q.one()
    lead_rate = (leads / sessions * 100) if leads is not None and sessions else None

    return {
        "sessions": sessions,
        "leads": leads,
        "lead_rate": lead_rate,
        "impressions": float(impressions or 0),
        "clicks": float(clicks or 0),
    }


def _path_hint(page_url: str) -> str:
    text = page_url.strip()
    if "://" in text:
        text = text.split("://", 1)[1]
        text = text.split("/", 1)[1] if "/" in text else text
    return text[:120] or page_url[:120]


def _pct_change(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before == 0:
        return None
    return ((after - before) / before) * 100


def _classify_result(deltas: dict[str, float | None]) -> AnnotationResult:
    primary = deltas.get("leads_change_pct")
    if primary is None:
        primary = deltas.get("sessions_change_pct")
    if primary is None:
        primary = deltas.get("clicks_change_pct")
    if primary is None:
        return AnnotationResult.NOT_ENOUGH_DATA
    if primary >= MEANINGFUL_CHANGE_PCT:
        return AnnotationResult.IMPROVED
    if primary <= -MEANINGFUL_CHANGE_PCT:
        return AnnotationResult.DECLINED
    return AnnotationResult.NO_MEANINGFUL_CHANGE


def measure_annotation_impact(
    db: Session,
    client: Client,
    row: Annotation,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Light causal frame: compare baseline vs post-action windows from facts or stored metrics."""
    lead_events = _lead_event_names(db, client.id)
    baseline = dict(row.baseline_metrics_json or {})
    post = dict(row.post_action_metrics_json or {})

    completed = row.completed_at or row.date
    measure_start = row.measurement_start_date
    measure_end = row.measurement_end_date

    if measure_start and measure_end and measure_end >= measure_start:
        days = (measure_end - measure_start).days + 1
        pre_end = completed - timedelta(days=1)
        pre_start = pre_end - timedelta(days=days - 1)
        if not baseline:
            baseline = _window_metrics(
                db,
                client.id,
                start=pre_start,
                end=pre_end,
                page_url=row.page_url,
                lead_events=lead_events,
            )
            row.baseline_metrics_json = {k: v for k, v in baseline.items() if v is not None}
        if not post:
            post = _window_metrics(
                db,
                client.id,
                start=measure_start,
                end=measure_end,
                page_url=row.page_url,
                lead_events=lead_events,
            )
            row.post_action_metrics_json = {k: v for k, v in post.items() if v is not None}

    deltas = {
        "sessions_change_pct": _pct_change(
            _as_float(baseline.get("sessions")), _as_float(post.get("sessions"))
        ),
        "leads_change_pct": _pct_change(_as_float(baseline.get("leads")), _as_float(post.get("leads"))),
        "lead_rate_change_pct": _pct_change(
            _as_float(baseline.get("lead_rate")), _as_float(post.get("lead_rate"))
        ),
        "impressions_change_pct": _pct_change(
            _as_float(baseline.get("impressions")), _as_float(post.get("impressions"))
        ),
        "clicks_change_pct": _pct_change(
            _as_float(baseline.get("clicks")), _as_float(post.get("clicks"))
        ),
    }

    suggested = _classify_result(deltas)
    if row.result in (AnnotationResult.NOT_YET_MEASURED, AnnotationResult.NOT_ENOUGH_DATA) or not row.result:
        if baseline and post:
            row.result = suggested

    summary = {
        "baseline": baseline,
        "post": post,
        "deltas": deltas,
        "suggested_result": suggested.value,
        "meaningful_change_pct": MEANINGFUL_CHANGE_PCT,
        "frame": "pre_vs_post_window",
    }
    row.impact_summary_json = summary
    if persist:
        db.commit()
        db.refresh(row)
    return summary


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def remeasure_all(db: Session, client: Client) -> int:
    rows = list_annotations(db, client.id)
    for row in rows:
        measure_annotation_impact(db, client, row, persist=False)
    db.commit()
    return len(rows)
