"""Defects the top-to-bottom audit found, each pinned by a test."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.models.client import ClientStatus
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.services.annotations import _window_metrics
from app.services.daily_sync import _mapped_sources_by_client


def test_a_page_scoped_annotation_can_be_measured(db, client_a):
    """_window_metrics filtered on `landing_page`, a column only the staging
    tables have, so any annotation with a page URL raised AttributeError and
    remeasure and import both returned 500."""
    result = _window_metrics(
        db,
        client_a.id,
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
        page_url="https://example.com/guide",
        lead_events=["generate_lead"],
    )
    assert set(result) == {"sessions", "leads", "lead_rate", "impressions", "clicks"}
    assert result["sessions"] == 0


def _connect_gsc(db, client):
    row = (
        db.query(Integration)
        .filter(
            Integration.client_id == client.id,
            Integration.provider == IntegrationProvider.GSC,
        )
        .one_or_none()
    )
    if row is None:
        row = Integration(id=uuid4(), client_id=client.id, provider=IntegrationProvider.GSC)
        db.add(row)
    row.connection_status = ConnectionStatus.CONNECTED
    row.external_property_id = "sc-domain:example.com"
    db.commit()


def test_an_active_client_is_synced(db, client_a):
    _connect_gsc(db, client_a)
    assert client_a.id in _mapped_sources_by_client(db)


def test_a_paused_or_archived_client_is_not_synced(db, client_a):
    """They kept syncing GSC, GA4 and SE Ranking because only some loops asked."""
    _connect_gsc(db, client_a)
    for status in (ClientStatus.PAUSED, ClientStatus.ARCHIVED):
        client_a.status = status
        db.commit()
        assert client_a.id not in _mapped_sources_by_client(db), status


def test_an_onboarding_client_is_synced(db, client_a):
    """Its data has to land for setup to be checkable."""
    _connect_gsc(db, client_a)
    client_a.status = ClientStatus.ONBOARDING
    db.commit()
    assert client_a.id in _mapped_sources_by_client(db)
