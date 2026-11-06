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


# ── The markup naming somebody else is NOT reported ─────────────────────────


def test_a_foreign_brand_in_the_markup_is_not_an_incident():
    """The spec's example, written and then removed.

    Over the warehouse it flagged three clients and was wrong about all
    three: SMA's markup names OpenAI and Google because its blog posts cite
    them, Robinson Unmanned's names the manufacturers it resells, and
    ACCTek's names "ACC Technical Services Inc.", which is ACCTek.
    Structured data says who is mentioned as readily as who owns the site.
    """
    assert (
        _ids(
            IncidentSignals(
                foreign_brands=(("OpenAI", 40), ("Google", 12)),
                pages_with_organization=2440,
            )
        )
        == []
    )


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
    """Nothing reports on this, but the signal is still read."""
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


# ── Test-lead exclusions ────────────────────────────────────────────────────


def _lead_def(db: Session, client: Client) -> None:
    db.add(
        ConversionDefinition(
            client_id=client.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            active=True,
        )
    )


def _lead(db: Session, client: Client, day: date, url: str = "/a", count: int = 2) -> None:
    db.add(
        FactGa4Event(
            client_id=client.id,
            date=day,
            raw_url=url,
            normalized_url=url,
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="generate_lead",
            event_count=count,
        )
    )


def test_excluded_leads_do_not_count_and_the_incident_says_so(db: Session, client_a: Client):
    from app.models.config import LeadExclusion

    _lead_def(db, client_a)
    for week in range(4):
        _lead(db, client_a, TODAY - timedelta(days=40 + week * 7))
    # Recent leads, all on the contact-test page.
    _lead(db, client_a, TODAY - timedelta(days=3), url="/test-form", count=5)
    db.add(LeadExclusion(client_id=client_a.id, url_pattern="/test-form*", reason="owner testing"))
    db.commit()

    signals = read_incident_signals(db, client_a, today=TODAY)
    assert signals.days_since_last_lead == 40
    assert signals.leads_in_prior_window == 8
    assert signals.excluded_leads_since_last == 5
    found = check(signals, month="2026-10", slug="x")
    assert len(found) == 1
    assert "5 more lead events" in found[0].detail
    assert "excluded as test submissions" in found[0].detail


def test_a_date_range_exclusion_drops_a_burst_of_test_submissions(db: Session, client_a: Client):
    from app.models.config import LeadExclusion

    _lead_def(db, client_a)
    _lead(db, client_a, TODAY - timedelta(days=60))
    for day in range(3):
        _lead(db, client_a, date(2026, 9, 1) + timedelta(days=day))
    db.add(
        LeadExclusion(
            client_id=client_a.id,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 30),
            reason="September was test submissions",
        )
    )
    db.commit()
    assert read_incident_signals(db, client_a, today=TODAY).days_since_last_lead == 60


def test_without_exclusions_nothing_changes(db: Session, client_a: Client):
    _lead_def(db, client_a)
    _lead(db, client_a, TODAY - timedelta(days=20))
    db.commit()
    signals = read_incident_signals(db, client_a, today=TODAY)
    assert signals.days_since_last_lead == 20
    assert signals.excluded_leads_since_last == 0
    assert "excluded" not in check(
        IncidentSignals(days_since_last_lead=20, leads_in_prior_window=4), month="2026-10", slug="x"
    )[0].detail
