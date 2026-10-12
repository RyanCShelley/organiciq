"""Incidents: what is broken, as opposed to what to grow.

The rule they exist to keep: an incident takes no slot and does not change
the constraint. A site that stopped recording leads has a broken tag, not a
conversion problem, and spending a growth slot on it answers the wrong
question — while saying nothing lets the engine prescribe optimisation on a
page nobody can convert on.

Most of this file is about when they stay quiet. Each of the three can report
a disaster on a client who merely has thin data.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.decisions.incidents import IncidentSignals, check
from app.models.client import Client
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.crawl import FactCrawlPageSchema, FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Event
from app.services.incident_signals import _organization_names, read_incident_signals

TODAY = date(2026, 10, 12)


def _ids(signals: IncidentSignals) -> list[str]:
    return [i.uid.rsplit("-", 1)[-1] for i in check(signals, month="2026-10", slug="x")]


# ── Leads stopped ───────────────────────────────────────────────────────────


def test_leads_stopping_after_a_history_of_them_is_an_incident():
    found = check(
        IncidentSignals(days_since_last_lead=21, leads_in_prior_window=40),
        month="2026-10",
        slug="x",
    )
    assert len(found) == 1
    assert "two weeks" in found[0].title
    assert found[0].scope == "Site-wide"
    assert "21 days ago" in found[0].detail


def test_a_client_who_never_had_a_lead_has_not_stopped_getting_them():
    assert _ids(IncidentSignals(days_since_last_lead=400, leads_in_prior_window=0)) == []


def test_a_quiet_week_is_not_an_incident():
    assert _ids(IncidentSignals(days_since_last_lead=6, leads_in_prior_window=40)) == []


# ── Pages vanished ──────────────────────────────────────────────────────────


def test_losing_a_fifth_of_the_indexable_pages_is_an_incident():
    found = check(
        IncidentSignals(indexable_now=300, indexable_before=500, crawl_before_date="2026-09-12"),
        month="2026-10",
        slug="x",
    )
    assert len(found) == 1
    assert "200 indexable pages have gone" in found[0].title
    assert "40%" in found[0].detail


def test_ordinary_drift_is_not_an_incident():
    assert _ids(IncidentSignals(indexable_now=480, indexable_before=500)) == []


def test_a_first_crawl_has_nothing_to_compare_against():
    assert _ids(IncidentSignals(indexable_now=300, indexable_before=None)) == []


def test_pages_being_added_is_not_an_incident():
    assert _ids(IncidentSignals(indexable_now=900, indexable_before=500)) == []


# ── The markup names somebody else ──────────────────────────────────────────


def test_markup_naming_another_company_is_an_incident():
    found = check(
        IncidentSignals(foreign_brands=(("Acme Dental", 40),), pages_with_organization=42),
        month="2026-10",
        slug="x",
    )
    assert len(found) == 1
    assert "Acme Dental" in found[0].detail


def test_several_wrong_names_are_one_fault_not_several():
    found = check(
        IncidentSignals(
            foreign_brands=(("Acme Dental", 40), ("Other Co", 12)),
            pages_with_organization=42,
        ),
        month="2026-10",
        slug="x",
    )
    assert len(found) == 1


# ── Reading them ────────────────────────────────────────────────────────────


def test_organization_names_are_found_anywhere_in_the_document():
    # Reading only the top of the document made `@context` look like an
    # Organization block once already.
    raw = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebPage"},
            {"@type": ["Organization", "LocalBusiness"], "name": "Acme Dental"},
        ],
    }
    assert _organization_names(raw) == ["Acme Dental"]


def test_the_clients_own_name_is_not_a_foreign_brand(db: Session, client_a: Client):
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            snapshot_date=TODAY,
            raw_url="/a",
            normalized_url="/a",
            word_count=100,
        )
    )
    for i in range(4):
        db.add(
            FactCrawlPageSchema(
                client_id=client_a.id,
                snapshot_date=TODAY,
                normalized_url=f"/p{i}",
                syntax="json-ld",
                schema_type="Organization",
                # Punctuation and a suffix must not make it a different company.
                raw={"@type": "Organization", "name": f"{client_a.client_name}, LLC"},
            )
        )
    db.commit()

    signals = read_incident_signals(db, client_a, today=TODAY)
    assert signals.foreign_brands == ()


def test_one_stray_page_is_not_a_site_wide_fault(db: Session, client_a: Client):
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            snapshot_date=TODAY,
            raw_url="/a",
            normalized_url="/a",
            word_count=100,
        )
    )
    db.add(
        FactCrawlPageSchema(
            client_id=client_a.id,
            snapshot_date=TODAY,
            normalized_url="/one",
            syntax="json-ld",
            schema_type="Organization",
            raw={"@type": "Organization", "name": "Acme Dental"},
        )
    )
    db.commit()
    # One page with the wrong name is on-page work; the whole site carrying
    # it is an incident.
    assert read_incident_signals(db, client_a, today=TODAY).foreign_brands == ()


def test_lead_silence_is_read_from_the_events(db: Session, client_a: Client):
    db.add(
        ConversionDefinition(
            client_id=client_a.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            active=True,
        )
    )
    last = TODAY - timedelta(days=30)
    for day in range(5):
        db.add(
            FactGa4Event(
                client_id=client_a.id,
                date=last - timedelta(days=day * 7),
                raw_url="/a",
                normalized_url="/a",
                channel=OrganicChannel.ORGANIC_SEARCH,
                event_name="generate_lead",
                event_count=3,
            )
        )
    db.commit()

    signals = read_incident_signals(db, client_a, today=TODAY)
    assert signals.days_since_last_lead == 30
    assert signals.leads_in_prior_window == 15
    assert _ids(signals) == ["stopped"]
