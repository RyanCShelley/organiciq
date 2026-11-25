from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import event

from app.models.client import ClientGroup, ClientStatus
from app.models.config import ConversionDefinition, LeadExclusion, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscDaily
from app.models.user import User, UserClient, UserRole
from tests.conftest import _make_client, auth_header


def _add_user(db, email: str, role: UserRole, *clients) -> User:
    u = User(
        id=uuid.uuid4(),
        email=email,
        name=email.split("@")[0],
        google_sub=f"sub-{email}",
        role=role,
    )
    db.add(u)
    db.flush()
    for c in clients:
        db.add(UserClient(user_id=u.id, client_id=c.id, role=role))
    db.commit()
    db.refresh(u)
    return u


def _add_gsc(
    db,
    client_id: uuid.UUID,
    day: date,
    *,
    impressions: int,
    clicks: int,
    avg_pos: float,
    site_url: str = "sc-domain:example.com",
) -> None:
    db.add(
        FactGscDaily(
            id=uuid.uuid4(),
            client_id=client_id,
            gsc_site_url=site_url,
            date=day,
            impressions=Decimal(str(impressions)),
            clicks=Decimal(str(clicks)),
            ctr=Decimal("0.05"),
            average_position=Decimal(str(avg_pos)),
        )
    )


def _add_ga4_traffic(
    db,
    client_id: uuid.UUID,
    day: date,
    *,
    channel: OrganicChannel,
    sessions: int,
    url: str = "https://example.com/",
) -> None:
    db.add(
        FactGa4Traffic(
            id=uuid.uuid4(),
            client_id=client_id,
            date=day,
            raw_url=url,
            normalized_url=url,
            session_source="google" if channel == OrganicChannel.ORGANIC_SEARCH else "direct",
            session_medium="organic" if channel == OrganicChannel.ORGANIC_SEARCH else "none",
            channel=channel,
            sessions=Decimal(str(sessions)),
            active_users=Decimal(str(sessions)),
            views=Decimal(str(sessions)),
        )
    )


def _add_ga4_event(
    db,
    client_id: uuid.UUID,
    day: date,
    *,
    event_name: str,
    event_count: int,
    url: str = "https://example.com/contact",
    session_source: str = "google",
    channel: OrganicChannel = OrganicChannel.ORGANIC_SEARCH,
) -> None:
    db.add(
        FactGa4Event(
            id=uuid.uuid4(),
            client_id=client_id,
            date=day,
            raw_url=url,
            normalized_url=url,
            session_source=session_source,
            session_medium="organic",
            channel=channel,
            event_name=event_name,
            event_count=event_count,
        )
    )


def test_overview_auth_and_role_scoping(client, db, client_a, client_b, admin_user, team_user):
    # Unauthenticated -> 401
    assert client.get("/v2/clients/overview").status_code == 401

    # Client portal roles -> 403
    _add_user(db, "viewer@example.com", UserRole.CLIENT_VIEWER, client_a)
    _add_user(db, "cadmin@example.com", UserRole.CLIENT_ADMIN, client_a)
    assert client.get("/v2/clients/overview", headers=auth_header("viewer@example.com")).status_code == 403
    assert client.get("/v2/clients/overview", headers=auth_header("cadmin@example.com")).status_code == 403

    # SMA_ADMIN sees all clients
    admin_res = client.get("/v2/clients/overview", headers=auth_header(admin_user.email))
    assert admin_res.status_code == 200
    admin_slugs = [c["slug"] for c in admin_res.json()["clients"]]
    assert admin_slugs == [client_a.slug, client_b.slug]

    # SMA_TEAM (assigned only to client_a in conftest) sees only client_a
    team_res = client.get("/v2/clients/overview", headers=auth_header(team_user.email))
    assert team_res.status_code == 200
    assert [c["slug"] for c in team_res.json()["clients"]] == [client_a.slug]

    # SEO_LEAD assigned to client_b sees only client_b
    _add_user(db, "lead@smamarketing.com", UserRole.SEO_LEAD, client_b)
    lead_res = client.get("/v2/clients/overview", headers=auth_header("lead@smamarketing.com"))
    assert lead_res.status_code == 200
    assert [c["slug"] for c in lead_res.json()["clients"]] == [client_b.slug]

    # CONTENT_MANAGER with 0 assignments gets empty list
    _add_user(db, "cm@smamarketing.com", UserRole.CONTENT_MANAGER)
    cm_res = client.get("/v2/clients/overview", headers=auth_header("cm@smamarketing.com"))
    assert cm_res.status_code == 200
    assert cm_res.json()["clients"] == []
    assert cm_res.json()["window"]["days"] == 30


def test_overview_gsc_multiproperty_ga4_traffic_and_deltas(client, db, client_a, client_b, admin_user):
    as_of = date(2026, 11, 22)
    cur_day = as_of - timedelta(days=2)  # inside [Oct 24 .. Nov 22]
    prev_day = as_of - timedelta(days=35)  # inside [Sep 24 .. Oct 23]

    # Multi-property GSC for client_a in current window:
    # prop 1: 300 imp, 30 clicks, pos 10.0
    # prop 2: 100 imp, 10 clicks, pos 2.0
    # weighted avg pos = (300*10 + 100*2) / 400 = 3200 / 400 = 8.0
    _add_gsc(db, client_a.id, cur_day, impressions=300, clicks=30, avg_pos=10.0, site_url="sc-domain:a.example")
    _add_gsc(db, client_a.id, cur_day, impressions=100, clicks=10, avg_pos=2.0, site_url="https://blog.a.example/")
    # Prior window: 200 imp -> +100.0%
    _add_gsc(db, client_a.id, prev_day, impressions=200, clicks=15, avg_pos=12.0, site_url="sc-domain:a.example")

    # GA4 Traffic for client_a: organic=150, paid=50, direct=50 -> total=250, organic=150
    _add_ga4_traffic(db, client_a.id, cur_day, channel=OrganicChannel.ORGANIC_SEARCH, sessions=150, url="https://a.example/1")
    _add_ga4_traffic(db, client_a.id, cur_day, channel=OrganicChannel.PAID_SEARCH, sessions=50, url="https://a.example/2")
    _add_ga4_traffic(db, client_a.id, cur_day, channel=OrganicChannel.DIRECT_UNATTRIBUTED, sessions=50, url="https://a.example/3")
    # Prior window: organic=100 -> +50.0%
    _add_ga4_traffic(db, client_a.id, prev_day, channel=OrganicChannel.ORGANIC_SEARCH, sessions=100, url="https://a.example/1")

    # client_b has current data only, ZERO prior data -> change_pct must be None, not division error
    _add_gsc(db, client_b.id, cur_day, impressions=50, clicks=5, avg_pos=4.5, site_url="sc-domain:b.example")
    _add_ga4_traffic(db, client_b.id, cur_day, channel=OrganicChannel.ORGANIC_SEARCH, sessions=40, url="https://b.example/1")
    # Also test freshness outside 30d window if stale, vs latest day (here cur_day is latest)
    db.commit()

    res = client.get(f"/v2/clients/overview?as_of={as_of.isoformat()}", headers=auth_header(admin_user.email))
    assert res.status_code == 200
    body = res.json()
    assert body["window"] == {
        "from_date": "2026-10-24",
        "to_date": "2026-11-22",
        "previous_from": "2026-09-24",
        "previous_to": "2026-10-23",
        "days": 30,
    }

    by_slug = {row["slug"]: row for row in body["clients"]}
    a = by_slug[client_a.slug]
    assert a["impressions"] == 400
    assert a["clicks"] == 40
    assert a["avg_position"] == 8.0
    assert a["impressions_change_pct"] == 100.0
    assert a["total_sessions"] == 250
    assert a["organic_sessions"] == 150
    assert a["organic_change_pct"] == 50.0
    assert a["gsc_through"] == cur_day.isoformat()
    assert a["ga4_through"] == cur_day.isoformat()

    b = by_slug[client_b.slug]
    assert b["impressions"] == 50
    assert b["clicks"] == 5
    assert b["avg_position"] == 4.5
    assert b["impressions_change_pct"] is None
    assert b["total_sessions"] == 40
    assert b["organic_sessions"] == 40
    assert b["organic_change_pct"] is None


def test_overview_leads_exclusions_business_models_goals_and_metadata(
    client, db, tier, client_a, client_b, admin_user
):
    as_of = date(2026, 11, 22)
    cur_day = as_of - timedelta(days=3)
    prev_day = as_of - timedelta(days=35)

    group = ClientGroup(id=uuid.uuid4(), name="Acme Group", slug="acme-group")
    db.add(group)
    db.flush()

    # Client A: lead_gen, consulting, group, checkpoint goal
    client_a.business_model = "lead_gen"
    client_a.service_mode = "consulting"
    client_a.group_id = group.id
    client_a.monthly_lead_goal = 50
    client_a.baseline_as_of = date(2026, 10, 1)
    client_a.baseline_monthly_leads = 10
    client_a.baseline_projection_json = {
        "baseline_as_of": "2026-10-01",
        "checkpoints": [
            {"month": 0, "monthly_leads": 10},
            {"month": 3, "monthly_leads": 25},
            {"month": 6, "monthly_leads": 40},
        ],
    }

    # Client B: ecommerce, execution, fallback monthly_lead_goal
    client_b.business_model = "ecommerce"
    client_b.service_mode = "execution"
    client_b.monthly_lead_goal = 30

    # Client C: both
    client_c = _make_client(db, tier, "Client C")
    client_c.business_model = "both"
    client_c.status = ClientStatus.ONBOARDING

    # Client D: no data / no conversions at all
    client_d = _make_client(db, tier, "Client D")
    client_d.status = ClientStatus.PAUSED

    # Client E: has active lead conversion + GA4 traffic, but 0 events -> leads=0
    client_e = _make_client(db, tier, "Client E")
    db.add(
        ConversionDefinition(
            id=uuid.uuid4(),
            client_id=client_e.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            active=True,
        )
    )
    _add_ga4_traffic(db, client_e.id, cur_day, channel=OrganicChannel.ORGANIC_SEARCH, sessions=25)

    # ConversionDefinitions for A (active lead + inactive lead + engagement)
    db.add_all(
        [
            ConversionDefinition(
                id=uuid.uuid4(),
                client_id=client_a.id,
                event_name="form_submit",
                conversion_name="Form",
                conversion_type="lead",
                active=True,
            ),
            ConversionDefinition(
                id=uuid.uuid4(),
                client_id=client_a.id,
                event_name="old_form",
                conversion_name="Old",
                conversion_type="lead",
                active=False,
            ),
            ConversionDefinition(
                id=uuid.uuid4(),
                client_id=client_a.id,
                event_name="scroll_90",
                conversion_name="Scroll",
                conversion_type="engagement",
                active=True,
            ),
            # B (ecommerce): purchase active, plus a lead definition that shouldn't double count when ecommerce exists
            ConversionDefinition(
                id=uuid.uuid4(),
                client_id=client_b.id,
                event_name="purchase",
                conversion_name="Order",
                conversion_type="ecommerce",
                active=True,
            ),
            ConversionDefinition(
                id=uuid.uuid4(),
                client_id=client_b.id,
                event_name="newsletter",
                conversion_name="Newsletter",
                conversion_type="lead",
                active=True,
            ),
            # C (both): counts lead + ecommerce, excludes engagement
            ConversionDefinition(
                id=uuid.uuid4(),
                client_id=client_c.id,
                event_name="form_submit",
                conversion_name="Form",
                conversion_type="lead",
                active=True,
            ),
            ConversionDefinition(
                id=uuid.uuid4(),
                client_id=client_c.id,
                event_name="purchase",
                conversion_name="Purchase",
                conversion_type="ecommerce",
                active=True,
            ),
            ConversionDefinition(
                id=uuid.uuid4(),
                client_id=client_c.id,
                event_name="video_play",
                conversion_name="Video",
                conversion_type="engagement",
                active=True,
            ),
        ]
    )

    # LeadExclusions ONLY for client_a:
    # 1) prefix url_pattern "/test-*"
    # 2) session_source "qa_bot" within date window
    db.add_all(
        [
            LeadExclusion(
                id=uuid.uuid4(),
                client_id=client_a.id,
                url_pattern="https://a.example/test-*",
                reason="Test staging URL",
            ),
            LeadExclusion(
                id=uuid.uuid4(),
                client_id=client_a.id,
                session_source="qa_bot",
                date_from=cur_day - timedelta(days=1),
                date_to=cur_day + timedelta(days=1),
                reason="QA bot traffic",
            ),
        ]
    )

    # Events for client_a:
    # - 12 valid form_submit in cur
    # - 5 excluded via /test-form in cur
    # - 3 excluded via qa_bot in cur
    # - 4 inactive old_form in cur (ignored)
    # - 9 engagement scroll_90 in cur (ignored)
    # - 8 valid form_submit in prev -> (12 - 8) / 8 = +50.0%
    _add_ga4_event(db, client_a.id, cur_day, event_name="form_submit", event_count=12, url="https://a.example/contact")
    _add_ga4_event(db, client_a.id, cur_day, event_name="form_submit", event_count=5, url="https://a.example/test-form")
    _add_ga4_event(db, client_a.id, cur_day, event_name="form_submit", event_count=3, url="https://a.example/quote", session_source="qa_bot")
    _add_ga4_event(db, client_a.id, cur_day, event_name="old_form", event_count=4, url="https://a.example/contact")
    _add_ga4_event(db, client_a.id, cur_day, event_name="scroll_90", event_count=9, url="https://a.example/contact")
    _add_ga4_event(db, client_a.id, prev_day, event_name="form_submit", event_count=8, url="https://a.example/contact")

    # Events for client_b: same URL/source as client_a's exclusions MUST NOT be excluded!
    _add_ga4_event(db, client_b.id, cur_day, event_name="purchase", event_count=7, url="https://a.example/test-form", session_source="qa_bot")
    _add_ga4_event(db, client_b.id, cur_day, event_name="newsletter", event_count=10, url="https://b.example/news")
    _add_ga4_event(db, client_b.id, prev_day, event_name="purchase", event_count=10, url="https://b.example/checkout")

    # Events for client_c: both (5 form_submit + 4 purchase = 9, video_play ignored)
    _add_ga4_event(db, client_c.id, cur_day, event_name="form_submit", event_count=5, url="https://c.example/contact")
    _add_ga4_event(db, client_c.id, cur_day, event_name="purchase", event_count=4, url="https://c.example/buy")
    _add_ga4_event(db, client_c.id, cur_day, event_name="video_play", event_count=20, url="https://c.example/video")

    db.commit()

    res = client.get(f"/v2/clients/overview?as_of={as_of.isoformat()}", headers=auth_header(admin_user.email))
    assert res.status_code == 200
    by_slug = {row["slug"]: row for row in res.json()["clients"]}

    a = by_slug[client_a.slug]
    assert a["service_mode"] == "consulting"
    assert a["plan_label"] == "Consulting"
    assert a["group_name"] == "Acme Group"
    assert a["current_lead_goal"] == 25
    assert a["monthly_lead_goal"] == 50
    assert a["leads"] == 12
    assert a["lead_label"] == "leads"
    assert a["leads_change_pct"] == 50.0

    b = by_slug[client_b.slug]
    assert b["service_mode"] == "execution"
    assert b["plan_label"] == f"{tier.tier_name} plan"
    assert b["current_lead_goal"] == 30
    assert b["leads"] == 7
    assert b["lead_label"] == "orders"
    assert b["leads_change_pct"] == -30.0

    c = by_slug[client_c.slug]
    assert c["status"] == "onboarding"
    assert c["leads"] == 9
    assert c["lead_label"] == "conversions"
    assert c["leads_change_pct"] is None

    d = by_slug[client_d.slug]
    assert d["status"] == "paused"
    assert d["impressions"] is None
    assert d["clicks"] is None
    assert d["avg_position"] is None
    assert d["total_sessions"] is None
    assert d["organic_sessions"] is None
    assert d["leads"] is None
    assert d["gsc_through"] is None
    assert d["ga4_through"] is None

    e = by_slug[client_e.slug]
    assert e["leads"] == 0
    assert e["leads_change_pct"] is None


def test_overview_ecommerce_falls_back_to_lead_definitions(client, db, client_a, admin_user):
    as_of = date(2026, 11, 22)
    cur_day = as_of - timedelta(days=1)

    client_a.business_model = "ecommerce"
    db.add(
        ConversionDefinition(
            id=uuid.uuid4(),
            client_id=client_a.id,
            event_name="checkout_complete",
            conversion_name="Checkout",
            conversion_type="lead",
            active=True,
        )
    )
    _add_ga4_event(db, client_a.id, cur_day, event_name="checkout_complete", event_count=6)
    db.commit()

    res = client.get(f"/v2/clients/overview?as_of={as_of.isoformat()}", headers=auth_header(admin_user.email))
    assert res.status_code == 200
    row = res.json()["clients"][0]
    assert row["leads"] == 6
    assert row["lead_label"] == "orders"


def test_overview_query_count_is_bounded_no_n_plus_1(client, db, tier, admin_user):
    as_of = date(2026, 11, 22)
    cur_day = as_of - timedelta(days=2)

    for idx in range(6):
        c = _make_client(db, tier, f"Portfolio {idx}")
        _add_gsc(db, c.id, cur_day, impressions=100 + idx, clicks=10, avg_pos=5.0)
        _add_ga4_traffic(db, c.id, cur_day, channel=OrganicChannel.ORGANIC_SEARCH, sessions=50 + idx)
        db.add(
            ConversionDefinition(
                id=uuid.uuid4(),
                client_id=c.id,
                event_name="generate_lead",
                conversion_name="Lead",
                conversion_type="lead",
                active=True,
            )
        )
        db.add(
            LeadExclusion(
                id=uuid.uuid4(),
                client_id=c.id,
                session_source="test",
                reason="Test",
            )
        )
        _add_ga4_event(db, c.id, cur_day, event_name="generate_lead", event_count=4 + idx)
    db.commit()

    queries: list[str] = []
    bind = db.get_bind()

    def _count_query(_conn, _cursor, statement, _parameters, _context, _executemany):
        queries.append(statement)

    event.listen(bind, "before_cursor_execute", _count_query)
    try:
        res = client.get(f"/v2/clients/overview?as_of={as_of.isoformat()}", headers=auth_header(admin_user.email))
    finally:
        event.remove(bind, "before_cursor_execute", _count_query)

    assert res.status_code == 200
    assert len(res.json()["clients"]) == 6
    # 1 user lookup + 1 clients + 2 GSC + 2 GA4 + 1 conv_defs + 1 exclusions + 1 events + 1 watchlist = 10-11 queries
    assert len(queries) <= 11, f"Expected <= 11 queries, got {len(queries)}: {queries}"
