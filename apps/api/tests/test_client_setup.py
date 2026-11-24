"""The setup checklist, and the dependency order it encodes.

The order is not a preference: the lead-definitions screen offers the client's
own GA4 event names, so it has nothing to show before the first pull, and the
baseline averages GA4 sessions and lead events, so it needs both. Each test
here pins one of those dependencies, because the value of the list is that a
blocked step says what it is waiting for.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.client_focus import ClientFocus
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.consulting import ConsultingProfile, ConsultingRecommendation
from app.models.engine_task import EngineTask
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscPage
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services.client_setup import setup_state
from tests.conftest import client_header

TODAY = date(2026, 10, 10)


def _step(state: dict, key: str) -> dict:
    return next(s for s in state["steps"] if s["key"] == key)


def _ga4(db: Session, client: Client, url: str = "https://x.test/", sessions: int = 10):
    db.add(
        FactGa4Traffic(
            client_id=client.id,
            date=TODAY - timedelta(days=2),
            raw_url=url,
            normalized_url=url,
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=sessions,
        )
    )
    db.commit()


def _gsc(db: Session, client: Client, url: str = "https://x.test/"):
    db.add(
        FactGscPage(
            client_id=client.id,
            date=TODAY - timedelta(days=2),
            raw_url=url,
            normalized_url=url,
            clicks=5,
            impressions=100,
            ctr=0.05,
            average_position=8.0,
        )
    )
    db.commit()


def test_a_fresh_client_is_told_to_connect_a_source_first(
    db: Session, client_a: Client
):
    state = setup_state(db, client_a)
    assert state["next"] == "sources"
    assert state["service_mode"] == "execution"
    assert _step(state, "account")["done"] is True
    assert _step(state, "sources")["done"] is False


def test_lead_definitions_wait_for_the_ga4_pull(db: Session, client_a: Client):
    state = setup_state(db, client_a)
    # Not "do this next" — there are no event names to choose from yet.
    assert _step(state, "leads")["blocked_by"] == "needs the GA4 pull"

    _ga4(db, client_a)
    state = setup_state(db, client_a)
    assert _step(state, "leads")["blocked_by"] is None


def test_the_baseline_waits_for_the_lead_definitions(db: Session, client_a: Client):
    _ga4(db, client_a)
    state = setup_state(db, client_a)
    assert _step(state, "baseline")["blocked_by"] == "needs lead definitions"

    db.add(
        ConversionDefinition(
            client_id=client_a.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            active=True,
        )
    )
    db.commit()

    state = setup_state(db, client_a)
    assert _step(state, "baseline")["blocked_by"] is None
    assert _step(state, "baseline")["detail"] == "ready to build from GA4"
    assert _step(state, "leads")["detail"] == "1 event marked as leads"


def test_the_baseline_reports_the_goal_it_wrote(db: Session, client_a: Client):
    # The goal comes from here, which is why the add-client form stopped
    # asking for one.
    client_a.baseline_as_of = date(2026, 9, 1)
    client_a.baseline_monthly_sessions = 1200
    client_a.monthly_lead_goal = 31
    db.commit()

    step = _step(setup_state(db, client_a), "baseline")
    assert step["done"] is True
    assert "goal 31/mo" in step["detail"]


def test_the_next_step_is_never_a_blocked_one(db: Session, client_a: Client):
    state = setup_state(db, client_a)
    nxt = _step(state, state["next"])
    assert nxt["blocked_by"] is None
    assert nxt["done"] is False


def test_progress_counts_only_required_done_steps(db: Session, client_a: Client):
    state = setup_state(db, client_a)
    required = [s for s in state["steps"] if not s["optional"]]
    assert state["done"] == sum(1 for s in required if s["done"])
    assert state["total"] == len(required)
    assert state["total"] == 7


def test_the_endpoint_serves_the_checklist(client, client_a, admin_user):
    response = client.get(
        f"/clients/{client_a.id}/setup",
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 7
    assert body["service_mode"] == "execution"
    keys = [s["key"] for s in body["steps"]]
    assert keys == [
        "account",
        "sources",
        "pull",
        "leads",
        "baseline",
        "watchlist",
        "first_run",
        "competitors",
    ]
    assert "content_sources" not in keys
    assert "conversion_pages" not in keys
    assert _step(body, "competitors")["optional"] is True
    assert all(s["optional"] is False for s in body["steps"] if s["key"] != "competitors")


def test_another_clients_setup_is_refused(client, client_b, team_user):
    # team_user is assigned to client_a only.
    response = client.get(
        f"/clients/{client_b.id}/setup",
        headers=client_header(client_b.id, team_user.email),
    )
    assert response.status_code == 403


def test_each_step_links_to_where_it_is_actually_done(db: Session, client_a: Client):
    """Every step links to an existing `apps/web-v2` slug-relative route."""
    steps = {s["key"]: s for s in setup_state(db, client_a)["steps"]}

    for key, scope, link in (
        ("account", "settings", "settings"),
        ("sources", "settings", "settings/connections"),
        ("pull", "settings", "settings/connections"),
        ("leads", "settings", "settings/conversions"),
        ("baseline", "settings", "settings/baseline"),
        ("watchlist", "tool", "watchlist"),
        ("competitors", "settings", "settings/competitors"),
        ("first_run", "tool", "engine"),
    ):
        assert steps[key]["scope"] == scope, key
        assert steps[key]["link"] == link, key


def test_connected_sources_require_saved_properties_and_only_ga4_gsc(
    db: Session, client_a: Client
):
    for integration in db.query(Integration).filter(Integration.client_id == client_a.id):
        integration.connection_status = ConnectionStatus.CONNECTED
        integration.external_property_id = None
    db.commit()
    assert _step(setup_state(db, client_a), "sources")["done"] is False

    # Connect only GA4 and GSC (without SE Ranking): v2 does not require SE Ranking.
    for integration in db.query(Integration).filter(Integration.client_id == client_a.id):
        if integration.provider in (IntegrationProvider.GA4, IntegrationProvider.GSC):
            integration.external_property_id = "selected-property"
        else:
            integration.connection_status = ConnectionStatus.DISCONNECTED
    db.commit()
    assert _step(setup_state(db, client_a), "sources")["done"] is True


def test_watchlist_step_reads_watchlist_keywords(db: Session, client_a: Client):
    assert _step(setup_state(db, client_a), "watchlist")["done"] is False

    bucket = WatchlistBucket(
        client_id=client_a.id,
        name="Core Services",
        name_key="core services",
    )
    db.add(bucket)
    db.flush()
    db.add(
        WatchlistKeyword(
            client_id=client_a.id,
            bucket_id=bucket.id,
            keyword="commercial hvac repair",
            keyword_key="commercial hvac repair",
        )
    )
    db.commit()

    step = _step(setup_state(db, client_a), "watchlist")
    assert step["done"] is True
    assert "1 keyword in 1 bucket" in step["detail"]


def test_optional_competitors_step_never_blocks_completion(db: Session, client_a: Client):
    # Complete all 7 required steps for execution while leaving competitors empty.
    for integration in db.query(Integration).filter(Integration.client_id == client_a.id):
        if integration.provider in (IntegrationProvider.GA4, IntegrationProvider.GSC):
            integration.connection_status = ConnectionStatus.CONNECTED
            integration.external_property_id = "selected-property"
    _ga4(db, client_a)
    _gsc(db, client_a)
    db.add(
        ConversionDefinition(
            client_id=client_a.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            active=True,
        )
    )
    client_a.baseline_as_of = date(2026, 9, 1)
    client_a.baseline_monthly_sessions = 1200
    client_a.monthly_lead_goal = 31
    bucket = WatchlistBucket(
        client_id=client_a.id,
        name="Core Services",
        name_key="core services",
    )
    db.add(bucket)
    db.flush()
    db.add(
        WatchlistKeyword(
            client_id=client_a.id,
            bucket_id=bucket.id,
            keyword="commercial hvac repair",
            keyword_key="commercial hvac repair",
        )
    )
    db.add(
        EngineTask(
            client_id=client_a.id,
            month="2026-10",
            kind="prescription",
            rule_id="R-01",
            search="commercial hvac",
            page_url="https://client-a.example/hvac",
            title="Optimize HVAC page",
            confirmed_by="admin@smamarketing.com",
        )
    )
    db.commit()

    state = setup_state(db, client_a)
    comp = _step(state, "competitors")
    assert comp["optional"] is True
    assert comp["done"] is False
    assert state["done"] == 7
    assert state["total"] == 7
    assert state["next"] is None

    # Adding competitors updates the optional step detail without altering required totals.
    client_a.competitor_domains = ["rival1.example", "rival2.example"]
    db.commit()
    state = setup_state(db, client_a)
    comp = _step(state, "competitors")
    assert comp["done"] is True
    assert "rival1.example, rival2.example" in comp["detail"]
    assert state["done"] == 7
    assert state["total"] == 7


def test_first_run_recognizes_v2_engine_task(db: Session, client_a: Client):
    assert _step(setup_state(db, client_a), "first_run")["blocked_by"] == "needs GA4 and Search Console data"

    _ga4(db, client_a)
    _gsc(db, client_a)

    db.add(
        ClientFocus(
            client_id=client_a.id,
            month=date(2026, 10, 1),
            focus="visibility",
        )
    )
    db.commit()
    focus_state = setup_state(db, client_a)
    assert _step(focus_state, "first_run")["done"] is False
    assert "monthly focus set" in _step(focus_state, "first_run")["detail"]

    db.add(
        EngineTask(
            client_id=client_a.id,
            month="2026-10",
            kind="prescription",
            rule_id="R-01",
            search="commercial hvac",
            page_url="https://client-a.example/hvac",
            title="Optimize HVAC page",
            confirmed_by="admin@smamarketing.com",
        )
    )
    db.commit()

    done_state = setup_state(db, client_a)
    assert _step(done_state, "first_run")["blocked_by"] is None
    assert _step(done_state, "first_run")["done"] is True
    assert "1 task confirmed" in _step(done_state, "first_run")["detail"]


def test_consulting_client_gets_consulting_steps_instead_of_execution_run(
    db: Session, client_a: Client
):
    client_a.service_mode = "consulting"
    db.commit()

    state = setup_state(db, client_a)
    assert state["service_mode"] == "consulting"
    assert state["total"] == 8
    keys = [s["key"] for s in state["steps"]]
    assert "first_run" not in keys
    assert "content_sources" not in keys
    assert "conversion_pages" not in keys
    assert "consulting_profile" in keys
    assert "consulting_deliverable" in keys

    prof = _step(state, "consulting_profile")
    deliv = _step(state, "consulting_deliverable")
    assert prof["scope"] == "tool"
    assert prof["link"] == "consulting"
    assert prof["done"] is False
    assert deliv["link"] == "consulting/recommendations"
    assert deliv["blocked_by"] == "needs GA4 and Search Console data"

    _ga4(db, client_a)
    _gsc(db, client_a)
    db.add(ConsultingProfile(client_id=client_a.id, goals="Grow inbound leads"))
    db.add(
        ConsultingRecommendation(
            client_id=client_a.id,
            title="Publish service hub",
            category="visibility",
            created_by="admin@smamarketing.com",
        )
    )
    db.commit()

    state = setup_state(db, client_a)
    assert _step(state, "consulting_profile")["done"] is True
    assert _step(state, "consulting_deliverable")["done"] is True
    assert _step(state, "consulting_deliverable")["blocked_by"] is None
