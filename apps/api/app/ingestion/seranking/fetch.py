from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.ingestion.seranking import client as ser_client
from app.ingestion.seranking.features import extract_features_by_keyword
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob
from app.models.seranking import StagingSerCompetitor, StagingSerKeyword, StagingSerPosition, StagingSerSiteSummary


def _api_key() -> str:
    key = get_settings().se_ranking_api_key.strip()
    if not key:
        raise RuntimeError("SE_RANKING_API_KEY not configured")
    return key


def _load_integration(db: Session, client_id: UUID) -> Integration:
    integration = (
        db.query(Integration)
        .filter(
            Integration.client_id == client_id,
            Integration.provider == IntegrationProvider.SE_RANKING,
        )
        .one_or_none()
    )
    if integration is None:
        raise RuntimeError("SE Ranking integration row missing")
    if not integration.external_property_id:
        raise RuntimeError("SE Ranking project is not selected")
    return integration


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _normalize_ser_domain(value: Any) -> str | None:
    text = _as_str(value)
    if not text:
        return None
    lowered = text.lower()
    if "://" in lowered:
        host = urlparse(lowered).netloc or lowered
    else:
        host = lowered.split("/")[0]
    host = host.removeprefix("www.")
    return host or None


def _index_metrics_by_domain(metrics_payload: Any) -> dict[str, dict[str, Any]]:
    """SE Ranking competitor_metrics returns rows keyed by domain, not competitor id."""
    by_domain: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    if isinstance(metrics_payload, list):
        rows = [item for item in metrics_payload if isinstance(item, dict)]
    elif isinstance(metrics_payload, dict):
        rows = [item for item in metrics_payload.values() if isinstance(item, dict)]
    for item in rows:
        domain = _normalize_ser_domain(item.get("domain") or item.get("url"))
        if domain:
            by_domain[domain] = item
    return by_domain


def _lookup_competitor_metric(
    comp: dict[str, Any],
    metrics_by_domain: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    for hint in (comp.get("url"), comp.get("domain"), comp.get("name")):
        domain = _normalize_ser_domain(hint)
        if domain and domain in metrics_by_domain:
            return metrics_by_domain[domain]
    comp_domain = _normalize_ser_domain(comp.get("url") or comp.get("domain") or comp.get("name"))
    if not comp_domain:
        return {}
    for metric_domain, metric in metrics_by_domain.items():
        if comp_domain == metric_domain or comp_domain in metric_domain or metric_domain in comp_domain:
            return metric
    return {}


def _engine_ids(engines: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for eng in engines:
        eid = _as_str(eng.get("site_engine_id") or eng.get("id"))
        if eid:
            ids.append(eid)
    return ids


def _flatten_positions(payload: Any, default_engine_id: str | None) -> list[dict[str, Any]]:
    """Normalize SE Ranking positions payloads into flat rows."""
    rows: list[dict[str, Any]] = []

    def add_row(item: dict[str, Any], engine_id: str | None, keyword_id: str | None, keyword: str | None) -> None:
        pos_date = _as_date(item.get("date") or item.get("check_date"))
        position = _as_decimal(item.get("pos") if "pos" in item else item.get("position"))
        rows.append(
            {
                "raw": item,
                "date": pos_date,
                "site_engine_id": engine_id,
                "keyword_id": keyword_id,
                "keyword": keyword,
                "position": position,
                "position_change": _as_decimal(item.get("change") if "change" in item else item.get("position_change")),
                "volume": _as_decimal(item.get("volume")),
                "ranking_url": _as_str(item.get("url") or item.get("landing_page") or item.get("ranking_url")),
                "visibility": _as_decimal(item.get("visibility") or item.get("search_visibility")),
            }
        )

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            engine_id = _as_str(item.get("site_engine_id")) or default_engine_id

            # Live API shape: [{ site_engine_id, keywords: [{ id, name, positions: [...] }] }]
            nested_keywords = item.get("keywords")
            if isinstance(nested_keywords, list):
                for kw in nested_keywords:
                    if not isinstance(kw, dict):
                        continue
                    keyword_id = _as_str(kw.get("id") or kw.get("keyword_id"))
                    keyword = _as_str(kw.get("name") or kw.get("keyword"))
                    keyword_volume = _as_decimal(kw.get("volume") or kw.get("search_volume"))
                    positions = kw.get("positions")
                    if isinstance(positions, list):
                        for p in positions:
                            if isinstance(p, dict):
                                add_row(p, engine_id, keyword_id, keyword or _as_str(p.get("name")))
                                if keyword_volume is not None and rows[-1]["volume"] is None:
                                    rows[-1]["volume"] = keyword_volume
                continue

            keyword_id = _as_str(item.get("keyword_id") or item.get("id"))
            keyword = _as_str(item.get("name") or item.get("keyword"))
            positions = item.get("positions")
            if isinstance(positions, list):
                for p in positions:
                    if isinstance(p, dict):
                        add_row(p, engine_id, keyword_id, keyword or _as_str(p.get("name")))
            else:
                add_row(item, engine_id, keyword_id, keyword)
        return rows

    if isinstance(payload, dict):
        # Common shape: { site_engine_id: { keyword_id: { dates... } } } or list under "keywords"
        if "keywords" in payload and isinstance(payload["keywords"], list):
            return _flatten_positions(payload["keywords"], default_engine_id)
        for key, value in payload.items():
            if key in {"site_id", "date_from", "date_to"}:
                continue
            if isinstance(value, list):
                rows.extend(_flatten_positions(value, _as_str(key) or default_engine_id))
            elif isinstance(value, dict):
                # engine -> keywords map
                engine_id = _as_str(key) if key.isdigit() or key.startswith("site") else default_engine_id
                for kid, kpayload in value.items():
                    if isinstance(kpayload, list):
                        for p in kpayload:
                            if isinstance(p, dict):
                                add_row(
                                    p,
                                    engine_id,
                                    _as_str(kid),
                                    _as_str(p.get("name") or p.get("keyword")),
                                )
                    elif isinstance(kpayload, dict):
                        positions = kpayload.get("positions")
                        keyword = _as_str(kpayload.get("name") or kpayload.get("keyword"))
                        keyword_id = _as_str(kpayload.get("keyword_id") or kid)
                        eng = _as_str(kpayload.get("site_engine_id")) or engine_id
                        if isinstance(positions, list):
                            for p in positions:
                                if isinstance(p, dict):
                                    add_row(p, eng, keyword_id, keyword)
                        else:
                            add_row(kpayload, eng, keyword_id, keyword)
    return rows


def fetch_seranking_search(db: Session, job: SyncJob) -> tuple[int, int, int, int]:
    integration = _load_integration(db, job.client_id)
    api_key = _api_key()
    site_id = integration.external_property_id or ""

    engines = ser_client.list_search_engines(api_key, site_id)
    engine_ids = _engine_ids(engines) or [""]

    groups = ser_client.list_keyword_groups(api_key, site_id)
    group_names = {
        _as_str(g.get("id")): _as_str(g.get("name"))
        for g in groups
        if _as_str(g.get("id"))
    }

    keywords_raw: list[dict[str, Any]] = []
    for eid in engine_ids:
        batch = ser_client.list_keywords(api_key, site_id, site_engine_id=eid or None)
        for item in batch:
            if not isinstance(item, dict):
                continue
            item = dict(item)
            item.setdefault("site_engine_id", eid or item.get("site_engine_id"))
            keywords_raw.append(item)
    if not keywords_raw:
        # Some accounts return keywords without requiring site_engine_id.
        for item in ser_client.list_keywords(api_key, site_id):
            if isinstance(item, dict):
                keywords_raw.append(item)

    positions_raw: list[dict[str, Any]] = []
    features_by_keyword: dict[tuple[str, str], list[str]] = {}
    for eid in engine_ids:
        payload = ser_client.list_positions(
            api_key=api_key,
            site_id=site_id,
            date_from=job.start_date,
            date_to=job.end_date,
            site_engine_id=eid or None,
        )
        features_by_keyword.update(extract_features_by_keyword(payload))
        positions_raw.extend(_flatten_positions(payload, eid or None))

    competitors = ser_client.list_competitors(api_key, site_id)
    competitor_rows: list[dict[str, Any]] = []
    metric_date = job.end_date
    for eid in engine_ids:
        metrics_payload = None
        if eid:
            try:
                metrics_payload = ser_client.competitor_metrics(
                    api_key=api_key,
                    site_id=site_id,
                    metric_date=metric_date,
                    site_engine_id=eid,
                )
            except Exception:  # noqa: BLE001 — metrics optional; do not fail whole sync
                metrics_payload = None
        metrics_by_domain = _index_metrics_by_domain(metrics_payload)
        has_metrics = bool(metrics_by_domain)

        for comp in competitors:
            if not isinstance(comp, dict):
                continue
            cid = _as_str(comp.get("id") or comp.get("competitor_id"))
            metric = _lookup_competitor_metric(comp, metrics_by_domain)
            visibility = _as_decimal(
                metric.get("visibility")
                or metric.get("search_visibility")
                or comp.get("visibility")
            )
            if visibility is None and has_metrics:
                visibility = Decimal("0")
            competitor_rows.append(
                {
                    "raw": {"competitor": comp, "metrics": metric},
                    "site_engine_id": eid or _as_str(comp.get("site_engine_id")) or "",
                    "competitor_id": cid,
                    "name": _as_str(comp.get("name") or comp.get("title")),
                    "url": _as_str(comp.get("url") or comp.get("domain")),
                    "visibility": visibility,
                    "metric_date": metric_date,
                }
            )

    db.query(StagingSerKeyword).filter(StagingSerKeyword.job_id == job.id).delete()
    db.query(StagingSerPosition).filter(StagingSerPosition.job_id == job.id).delete()
    db.query(StagingSerCompetitor).filter(StagingSerCompetitor.job_id == job.id).delete()
    db.query(StagingSerSiteSummary).filter(StagingSerSiteSummary.job_id == job.id).delete()

    for item in keywords_raw:
        keyword = _as_str(item.get("name") or item.get("keyword"))
        keyword_id = _as_str(item.get("id") or item.get("keyword_id"))
        if not keyword or not keyword_id:
            continue
        group_id = _as_str(item.get("group_id") or item.get("group"))
        site_engine_id = _as_str(item.get("site_engine_id")) or (engine_ids[0] if engine_ids else "")
        raw = dict(item)
        earned = features_by_keyword.get((site_engine_id or "", keyword_id or ""))
        if earned:
            raw["earned_serp_features"] = earned
        db.add(
            StagingSerKeyword(
                job_id=job.id,
                client_id=job.client_id,
                raw=raw,
                site_engine_id=site_engine_id,
                keyword_id=keyword_id,
                keyword=keyword,
                group_id=group_id,
                group_name=group_names.get(group_id) if group_id else _as_str(item.get("group_name")),
                volume=_as_decimal(item.get("volume") or item.get("search_volume")),
            )
        )

    for row in positions_raw:
        if not row.get("keyword_id") or not row.get("date"):
            continue
        db.add(
            StagingSerPosition(
                job_id=job.id,
                client_id=job.client_id,
                raw=row["raw"],
                date=row["date"],
                site_engine_id=row.get("site_engine_id") or (engine_ids[0] if engine_ids else ""),
                keyword_id=row.get("keyword_id"),
                keyword=row.get("keyword"),
                position=row.get("position"),
                position_change=row.get("position_change"),
                volume=row.get("volume"),
                ranking_url=row.get("ranking_url"),
                visibility=row.get("visibility"),
            )
        )

    for row in competitor_rows:
        if not row.get("competitor_id"):
            continue
        db.add(
            StagingSerCompetitor(
                job_id=job.id,
                client_id=job.client_id,
                raw=row["raw"],
                site_engine_id=row.get("site_engine_id") or "",
                competitor_id=row.get("competitor_id"),
                name=row.get("name"),
                url=row.get("url"),
                visibility=row.get("visibility"),
                metric_date=row.get("metric_date"),
            )
        )

    summary_rows = 0
    try:
        summary_payload = ser_client.site_summary(api_key, site_id)
    except Exception:  # noqa: BLE001 — summary optional; do not fail whole sync
        summary_payload = {}
    if isinstance(summary_payload, dict) and summary_payload:
        metric_date = job.end_date
        db.add(
            StagingSerSiteSummary(
                job_id=job.id,
                client_id=job.client_id,
                raw=summary_payload,
                metric_date=metric_date,
                visibility=_as_decimal(summary_payload.get("visibility")),
                visibility_percent=_as_decimal(summary_payload.get("visibility_percent")),
                top5=_as_int(summary_payload.get("top5")),
                top10=_as_int(summary_payload.get("top10")),
                top30=_as_int(summary_payload.get("top30")),
            )
        )
        summary_rows = 1

    db.commit()
    return len(keywords_raw), len(positions_raw), len(competitor_rows), summary_rows
