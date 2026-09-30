"""Bulk client import: domain matching, idempotency, and refusing to guess."""

from __future__ import annotations

import pytest

from app.import_clients import Resolver, import_clients, normalize_host, slugify
from app.models.client import Client
from app.models.config import ConversionDefinition
from app.models.client import Tier
from app.models.integration import Integration, IntegrationProvider


@pytest.fixture(autouse=True)
def plan_tiers(db):
    """The real plan names, which the CSV's `tier` column is matched against."""
    for name in ("Launch", "Lift", "Lead"):
        db.add(Tier(tier_name=name))
    db.commit()


@pytest.fixture
def resolver(monkeypatch):
    """A resolver with a fixed catalogue and no network."""

    def build(db, *, skip_lookups=False):
        instance = Resolver.__new__(Resolver)
        instance.ga4 = [
            {"property_id": "properties/111", "display_name": "Acme Roofing", "account_name": "SMA"},
            {"property_id": "properties/222", "display_name": "Beta Dental", "account_name": "SMA"},
            {"property_id": "properties/333", "display_name": "Acme Roofing (old)", "account_name": "SMA"},
        ]
        instance.gsc = [
            {"siteUrl": "sc-domain:acmeroofing.com"},
            {"siteUrl": "https://www.betadental.com/"},
        ]
        instance.seranking = [
            {"id": 9001, "url": "https://acmeroofing.com"},
            {"id": 9002, "name": "betadental.com"},
        ]
        return instance

    monkeypatch.setattr("app.import_clients.Resolver", build)
    return build


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("sc-domain:example.com", "example.com"),
        ("https://www.example.com/", "example.com"),
        ("http://example.com/path?x=1", "example.com"),
        ("EXAMPLE.com", "example.com"),
        ("example.com.", "example.com"),
        ("", ""),
    ],
)
def test_normalize_host_handles_every_shape_the_apis_use(raw, expected):
    assert normalize_host(raw) == expected


def test_slugify_is_url_safe():
    assert slugify("Acme Roofing & Co.") == "acme-roofing-co"


def test_creates_a_client_with_resolved_integrations(db, resolver):
    rows = [
        {
            "client_name": "Beta Dental",
            "domain": "https://www.betadental.com/",
            "tier": "Lift",
            "lead_events": "generate_lead;book_appointment",
        }
    ]

    counts = import_clients(db, rows, apply=True)

    assert counts["created"] == 1
    client = db.query(Client).filter(Client.slug == "beta-dental").one()
    # The stored domain is the normalized host, which is what the fact tables join on.
    assert client.domain == "betadental.com"

    mapped = {
        row.provider: row.external_property_id
        for row in db.query(Integration).filter(Integration.client_id == client.id).all()
    }
    assert mapped[IntegrationProvider.GSC] == "https://www.betadental.com/"
    assert mapped[IntegrationProvider.SE_RANKING] == "9002"
    assert mapped[IntegrationProvider.GA4] == "properties/222"

    events = (
        db.query(ConversionDefinition).filter(ConversionDefinition.client_id == client.id).all()
    )
    assert sorted(e.event_name for e in events) == ["book_appointment", "generate_lead"]
    assert sum(1 for e in events if e.is_primary) == 1


def test_an_ambiguous_match_is_left_empty_rather_than_guessed(db, resolver):
    """Two GA4 properties look like Acme; binding either would be silent bad data."""
    rows = [{"client_name": "Acme Roofing", "domain": "acmeroofing.com", "tier": "Launch"}]

    counts = import_clients(db, rows, apply=True)

    assert counts["unresolved"] == 1
    client = db.query(Client).filter(Client.slug == "acme-roofing").one()
    mapped = {
        row.provider: row.external_property_id
        for row in db.query(Integration).filter(Integration.client_id == client.id).all()
    }
    assert IntegrationProvider.GA4 not in mapped
    # The unambiguous ones are still bound.
    assert mapped[IntegrationProvider.GSC] == "sc-domain:acmeroofing.com"
    assert mapped[IntegrationProvider.SE_RANKING] == "9001"


def test_a_csv_id_beats_a_lookup(db, resolver):
    rows = [
        {
            "client_name": "Acme Roofing",
            "domain": "acmeroofing.com",
            "tier": "Launch",
            "ga4_property_id": "properties/999",
        }
    ]

    import_clients(db, rows, apply=True)

    client = db.query(Client).filter(Client.slug == "acme-roofing").one()
    row = (
        db.query(Integration)
        .filter(Integration.client_id == client.id, Integration.provider == IntegrationProvider.GA4)
        .one()
    )
    assert row.external_property_id == "properties/999"


def test_a_dry_run_writes_nothing(db, resolver):
    rows = [{"client_name": "Beta Dental", "domain": "betadental.com", "tier": "Lift"}]

    counts = import_clients(db, rows, apply=False)

    assert counts["created"] == 1
    assert db.query(Client).filter(Client.slug == "beta-dental").one_or_none() is None


def test_rerunning_updates_rather_than_duplicates(db, resolver):
    rows = [{"client_name": "Beta Dental", "domain": "betadental.com", "tier": "Lift"}]
    import_clients(db, rows, apply=True)

    rows[0]["monthly_lead_goal"] = "40"
    counts = import_clients(db, rows, apply=True)

    assert counts["updated"] == 1
    assert counts["created"] == 0
    assert db.query(Client).filter(Client.slug == "beta-dental").count() == 1
    assert db.query(Client).filter(Client.slug == "beta-dental").one().monthly_lead_goal == 40


def test_an_unknown_tier_is_skipped_not_defaulted(db, resolver):
    """Defaulting the tier would silently put a client on the wrong projection curve."""
    rows = [{"client_name": "Gamma Co", "domain": "gamma.com", "tier": "Platinum"}]

    counts = import_clients(db, rows, apply=True)

    assert counts["skipped"] == 1
    assert db.query(Client).filter(Client.slug == "gamma-co").one_or_none() is None


def test_a_row_missing_a_required_field_is_skipped(db, resolver):
    rows = [{"client_name": "", "domain": "nowhere.com", "tier": "Launch"}]

    counts = import_clients(db, rows, apply=True)

    assert counts["skipped"] == 1
