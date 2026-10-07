"""Shared data-health status for one client."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.integration import Integration
from app.models.job import DataWatermark

WATERMARK_SOURCES = (
    "gsc_pages",
    "gsc_queries",
    "ga4",
    "se_ranking_search",
    "se_ranking_ai",
    "site_crawl",
)

#: The integration a source depends on. `site_crawl` has none — it crawls the
#: client's own site directly — so its health is the watermark alone, and
#: requiring an integration would have shown it permanently "Not Connected".
PROVIDER_FOR_SOURCE = {
    "gsc_pages": "gsc",
    "gsc_queries": "gsc",
    "ga4": "ga4",
    "se_ranking_search": "se_ranking",
    "se_ranking_ai": "se_ranking",
    "site_crawl": None,
}

#: Sources that run on a weekly cycle rather than daily, so "stale" means
#: something different for them.
WEEKLY_SOURCES = frozenset({"site_crawl"})


def data_health_rows(
    integrations: dict[str, Integration],
    watermarks: dict[str, DataWatermark],
) -> list[dict]:
    result = []
    for source in WATERMARK_SOURCES:
        provider = PROVIDER_FOR_SOURCE[source]
        integration = integrations.get(provider) if provider else None
        watermark = watermarks.get(source)
        needs_integration = provider is not None
        if needs_integration and (
            integration is None or integration.connection_status.value == "not_connected"
        ):
            status_label = "Not Connected"
        elif watermark is None:
            status_label = "Not scheduled yet" if source in WEEKLY_SOURCES else "Not Connected"
        else:
            status_label = (
                "Healthy"
                if watermark.validation_status and watermark.validation_status.value == "passed"
                else "Stale"
            )

        result.append(
            {
                "source": source,
                "status": status_label,
                "fact_through": watermark.fact_through_date.isoformat()
                if watermark and watermark.fact_through_date
                else None,
                "last_sync": watermark.last_successful_sync_at.isoformat()
                if watermark and watermark.last_successful_sync_at
                else None,
                "validation": watermark.validation_status.value
                if watermark and watermark.validation_status
                else None,
            }
        )
    return result


def load_client_data_health(db: Session, client_id: UUID) -> list[dict]:
    integrations = {
        i.provider.value: i
        for i in db.query(Integration).filter(Integration.client_id == client_id).all()
    }
    watermarks = {
        w.source: w
        for w in db.query(DataWatermark).filter(DataWatermark.client_id == client_id).all()
    }
    return data_health_rows(integrations, watermarks)


def integration_status_label(integration: Integration | None) -> str:
    if integration is None:
        return "Not Connected"
    if integration.connection_status.value == "not_connected":
        return "Not Connected"
    if integration.connection_status.value == "connected":
        return "Connected"
    return integration.connection_status.value.replace("_", " ").title()
