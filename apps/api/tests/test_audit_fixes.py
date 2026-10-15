"""Defects the top-to-bottom audit found, each pinned by a test."""

from __future__ import annotations

from datetime import date, datetime, timezone
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


# ── Platform views follow assignments ──


def _job(db, client, source="gsc_pages"):
    from app.models.job import SyncJob, SyncJobStatus

    db.add(
        SyncJob(
            id=uuid4(), client_id=client.id, source=source,
            start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
            status=SyncJobStatus.FAILED, error_message=f"boom for {client.client_name}",
        )
    )
    db.commit()


def _names(rows):
    return {row["client_name"] for row in rows}


def test_a_team_member_sees_only_their_clients_on_the_platform_views(
    db, client, client_a, client_b, team_user
):
    """They listed every client — name, domain, integration status and job error
    text — to any staff account, including one with no assignments."""
    from tests.conftest import auth_header

    _job(db, client_a)
    _job(db, client_b)
    headers = auth_header(team_user.email)
    for path in ("/admin/platform/overview", "/admin/platform/data-health", "/admin/platform/jobs"):
        res = client.get(path, headers=headers)
        assert res.status_code == 200, path
        assert _names(res.json()) == {client_a.client_name}, path


def test_an_admin_still_sees_every_client(db, client, client_a, client_b, admin_user):
    from tests.conftest import auth_header

    _job(db, client_a)
    _job(db, client_b)
    headers = auth_header(admin_user.email)
    for path in ("/admin/platform/overview", "/admin/platform/data-health", "/admin/platform/jobs"):
        res = client.get(path, headers=headers)
        assert {client_a.client_name, client_b.client_name} <= _names(res.json()), path


def test_a_team_member_with_no_assignments_sees_nothing(db, client, client_a):
    from app.models.user import User, UserRole
    from tests.conftest import auth_header

    loner = User(id=uuid4(), email="loner@smamarketing.com", name="Loner", role=UserRole.SMA_TEAM)
    db.add(loner)
    db.commit()
    _job(db, client_a)
    for path in ("/admin/platform/overview", "/admin/platform/data-health", "/admin/platform/jobs"):
        assert client.get(path, headers=auth_header(loner.email)).json() == [], path


# ── Plan and spend limits are an admin's ──


def _patch(client, who, client_obj, **body):
    from tests.conftest import client_header

    return client.patch(
        f"/clients/{client_obj.id}", json=body, headers=client_header(client_obj.id, who.email)
    )


def test_a_team_member_cannot_raise_their_own_spend_limits(client, client_a, team_user):
    """Plan tier, allowances and the crawl and AI-search ceilings decide how much
    is fetched and how many billed prompts run."""
    for body in (
        {"ai_search_prompt_limit": 500},
        {"crawl_page_limit": 100000},
        {"custom_update_allowance": 99},
        {"custom_watchlist_cadence": "daily"},
    ):
        res = _patch(client, team_user, client_a, **body)
        assert res.status_code == 403, body
        assert "Only an SMA admin" in res.json()["detail"]


def test_a_team_member_cannot_move_a_client_to_another_tier(client, db, client_a, client_b, team_user):
    res = _patch(client, team_user, client_a, tier_id=str(uuid4()))
    assert res.status_code == 403


def test_saving_the_form_with_limits_untouched_still_works_for_a_team_member(
    client, client_a, team_user
):
    """The settings form sends every field on every save. Only a change is refused."""
    res = _patch(
        client, team_user, client_a,
        tier_id=str(client_a.tier_id),
        ai_search_prompt_limit=client_a.ai_search_prompt_limit,
        crawl_page_limit=client_a.crawl_page_limit,
        custom_update_allowance=client_a.custom_update_allowance,
        timezone="America/Chicago",
    )
    assert res.status_code == 200, res.text
    assert res.json()["timezone"] == "America/Chicago"


def test_a_team_member_can_still_change_operational_fields(client, client_a, team_user):
    res = _patch(client, team_user, client_a, teamwork_tasklist_id="12345", primary_market="Canada")
    assert res.status_code == 200
    assert res.json()["teamwork_tasklist_id"] == "12345"


def test_an_admin_can_change_the_limits(client, client_a, admin_user):
    res = _patch(client, admin_user, client_a, ai_search_prompt_limit=7, crawl_page_limit=250)
    assert res.status_code == 200, res.text
    assert res.json()["ai_search_prompt_limit"] == 7
    assert res.json()["crawl_page_limit"] == 250


# ── One Google grant sees every property ──


def _connected(db, client, provider, *, primary, secondaries=None):
    from app.core.crypto import encrypt_json

    row = (
        db.query(Integration)
        .filter(Integration.client_id == client.id, Integration.provider == provider)
        .one()
    )
    row.connection_status = ConnectionStatus.CONNECTED
    row.external_property_id = primary
    row.gsc_secondary_site_urls = list(secondaries or [])
    row.credentials = encrypt_json({"refresh_token": "rt-test", "token": "at-test"})
    db.commit()
    return row


def _save_gsc(client, who, client_obj, site, role="primary"):
    from tests.conftest import client_header

    return client.post(
        "/integrations/gsc/property",
        json={"site_url": site, "role": role},
        headers=client_header(client_obj.id, who.email),
    )


def test_a_team_member_cannot_map_a_property_another_client_already_has(
    db, client, client_a, client_b, team_user
):
    """One Google grant sees every property in the workspace. Picking client B's
    for client A would pull B's data into A's tenant."""
    _connected(db, client_a, IntegrationProvider.GSC, primary="sc-domain:a.example")
    _connected(db, client_b, IntegrationProvider.GSC, primary="sc-domain:b.example")
    res = _save_gsc(client, team_user, client_a, "sc-domain:b.example")
    assert res.status_code == 409
    assert "Ask an admin" in res.json()["detail"]
    row = db.query(Integration).filter(
        Integration.client_id == client_a.id, Integration.provider == IntegrationProvider.GSC
    ).one()
    db.refresh(row)
    assert row.external_property_id == "sc-domain:a.example"


def test_a_property_listed_as_another_clients_secondary_is_claimed_too(
    db, client, client_a, client_b, team_user
):
    _connected(db, client_a, IntegrationProvider.GSC, primary="sc-domain:a.example")
    _connected(
        db, client_b, IntegrationProvider.GSC, primary="sc-domain:b.example",
        secondaries=["sc-domain:old-b.example"],
    )
    assert _save_gsc(client, team_user, client_a, "sc-domain:old-b.example").status_code == 409


def test_a_team_member_can_connect_a_property_nobody_has(db, client, client_a, client_b, team_user):
    _connected(db, client_a, IntegrationProvider.GSC, primary="sc-domain:a.example")
    _connected(db, client_b, IntegrationProvider.GSC, primary="sc-domain:b.example")
    res = _save_gsc(client, team_user, client_a, "sc-domain:brand-new.example")
    assert res.status_code == 200, res.text


def test_an_admin_can_share_a_property_across_clients(db, client, client_a, client_b, admin_user):
    _connected(db, client_a, IntegrationProvider.GSC, primary="sc-domain:a.example")
    _connected(db, client_b, IntegrationProvider.GSC, primary="sc-domain:b.example")
    assert _save_gsc(client, admin_user, client_a, "sc-domain:b.example").status_code == 200


def test_a_folder_scoped_client_shares_its_parents_property_by_design(
    db, client, client_a, client_b, team_user
):
    _connected(db, client_a, IntegrationProvider.GSC, primary="sc-domain:a.example")
    _connected(db, client_b, IntegrationProvider.GSC, primary="sc-domain:b.example")
    client_a.path_prefix = "/unmanned"
    db.commit()
    assert _save_gsc(client, team_user, client_a, "sc-domain:b.example").status_code == 200


def test_ga4_properties_are_protected_the_same_way(db, client, client_a, client_b, team_user):
    from tests.conftest import client_header

    _connected(db, client_a, IntegrationProvider.GA4, primary="properties/1")
    _connected(db, client_b, IntegrationProvider.GA4, primary="properties/222")
    headers = client_header(client_a.id, team_user.email)
    blocked = client.post("/integrations/ga4/property", json={"property_id": "222"}, headers=headers)
    assert blocked.status_code == 409
    free = client.post("/integrations/ga4/property", json={"property_id": "333"}, headers=headers)
    assert free.status_code == 200, free.text


def test_only_an_admin_can_replace_the_workspace_wide_google_grant(client, client_a, team_user, admin_user):
    from tests.conftest import auth_header

    path = f"/oauth/google/start?client_id={client_a.id}"
    res = client.get(path, headers=auth_header(team_user.email))
    assert res.status_code == 403
    assert "admin" in res.json()["detail"].lower()


# ── Sign-in registration ──


def _upsert(client, email, **extra):
    from app.core.settings import get_settings

    secret = get_settings().internal_api_secret
    headers = {"X-OrganicIQ-Internal-Secret": secret} if secret else {}
    return client.post(
        "/auth/upsert", json={"email": email, "name": "Someone", "google_sub": "g-1", **extra},
        headers=headers,
    )


def _workspace_domain() -> str:
    from app.core.settings import get_settings

    return sorted(get_settings().hosted_domains)[0]


def test_a_workspace_account_is_registered(client):
    email = f"new.person@{_workspace_domain()}"
    res = _upsert(client, email)
    assert res.status_code == 200, res.text
    assert res.json()["email"] == email


def test_an_address_outside_the_workspace_is_refused(client):
    """Anyone holding the internal secret could create a staff user for any address."""
    res = _upsert(client, "someone@gmail.com")
    assert res.status_code == 403


def test_a_deactivated_account_is_refused_at_sign_in(db, client, team_user):
    team_user.is_active = False
    db.commit()
    res = _upsert(client, team_user.email)
    assert res.status_code == 403
    assert "deactivated" in res.json()["detail"].lower()


# ── Page-stage suggestions are paid for per page ──


class _CountingClassifier:
    name = "test-model"

    def __init__(self):
        self.read: list[str] = []

    def classify(self, candidates):
        from app.services.page_stage import Suggestion

        self.read = [c.normalized_url for c in candidates]
        return [Suggestion(c.normalized_url, "mofu", "high", "test") for c in candidates]


def _candidates(urls):
    from app.services.page_stage import PageCandidate

    return [
        PageCandidate(
            normalized_url=u, sessions=10.0, title=u, description=None,
            headings=(), first_paragraphs=(), word_count=500,
        )
        for u in urls
    ]


def test_suggesting_does_not_pay_to_classify_a_confirmed_page(db, client, client_a, team_user, monkeypatch):
    """Every page went to the model and the answers for confirmed ones were
    discarded — billed per page, inside the request."""
    from app.models.config import ClientPageStage
    from app.services import page_stage
    from tests.conftest import client_header

    urls = ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
    classifier = _CountingClassifier()
    monkeypatch.setattr(page_stage, "load_classifier", lambda: classifier)
    monkeypatch.setattr(page_stage, "load_candidates", lambda db, client_, **kw: _candidates(urls))
    db.add(
        ClientPageStage(
            client_id=client_a.id, normalized_url=urls[0], stage="bofu",
            confirmed_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    res = client.post("/decisions/page-stages/suggest", headers=client_header(client_a.id, team_user.email))

    assert res.status_code == 200, res.text
    assert sorted(classifier.read) == sorted(urls[1:])  # the confirmed one was not sent
    body = res.json()
    assert body["suggested"] == 2 and body["already_confirmed"] == 1


def test_suggesting_with_everything_confirmed_makes_no_model_call(db, client, client_a, team_user, monkeypatch):
    from app.models.config import ClientPageStage
    from app.services import page_stage
    from tests.conftest import client_header

    urls = ["https://example.com/a"]
    classifier = _CountingClassifier()
    monkeypatch.setattr(page_stage, "load_classifier", lambda: classifier)
    monkeypatch.setattr(page_stage, "load_candidates", lambda db, client_, **kw: _candidates(urls))
    db.add(
        ClientPageStage(
            client_id=client_a.id, normalized_url=urls[0], stage="bofu",
            confirmed_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    res = client.post("/decisions/page-stages/suggest", headers=client_header(client_a.id, team_user.email))

    assert res.json() == {"suggested": 0, "pages": 1, "already_confirmed": 1}
    assert classifier.read == []


# ── The site-crawl lists do not load what they never show ──


def _seed_crawl(db, client_a, pages: int, start: int = 0):
    from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSchema, FactCrawlPageSnapshot

    for i in range(start, start + pages):
        url = f"https://example.com/p{i}"
        db.add(
            FactCrawlPageSnapshot(
                id=uuid4(), client_id=client_a.id, source=CRAWL_SOURCE_FIRST_PARTY,
                snapshot_date=date(2026, 10, 1), raw_url=url, normalized_url=url, status_code=200,
                indexable=True, word_count=900, inbound_internal_links=3, inbound_editorial_links=1,
                redirect_count=0, title=f"Page {i}", description="d" * 400,
                sections=[{"heading": "h", "first_paragraph": "p" * 300}] * 8,
                faq_questions=["why?"] * 5,
            )
        )
        for t in ("Article", "FAQPage"):
            db.add(
                FactCrawlPageSchema(
                    id=uuid4(), client_id=client_a.id, snapshot_date=date(2026, 10, 1),
                    normalized_url=url, syntax="json-ld", schema_type=t,
                    raw={"@type": t, "blob": "x" * 2000},
                )
            )
    db.commit()


def _record_sql(engine):
    from sqlalchemy import event

    seen: list[str] = []

    def capture(conn, cursor, statement, *args):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    return seen, lambda: event.remove(engine, "before_cursor_execute", capture)


def test_the_crawl_lists_never_select_the_wide_columns(db, engine, client, client_a, team_user):
    """`raw` (a whole JSON-LD document per block) and `sections` were loaded for
    every page of every filter click and thrown away."""
    from tests.conftest import client_header

    _seed_crawl(db, client_a, pages=5)
    headers = client_header(client_a.id, team_user.email)
    seen, stop = _record_sql(engine)
    try:
        for path in ("/site-crawl/pages", "/site-crawl/schema", "/site-crawl/schema/pages?type=Article"):
            assert client.get(path, headers=headers).status_code == 200, path
    finally:
        stop()
    selects = [s for s in seen if s.lstrip().upper().startswith("SELECT")]
    joined = "\n".join(selects)
    assert "facts_crawl_page_schema.raw" not in joined
    assert "facts_crawl_page_snapshots.sections" not in joined
    assert "facts_crawl_page_snapshots.faq_questions" not in joined


def test_the_crawl_list_query_count_does_not_grow_with_the_site(db, engine, client, client_a, team_user):
    """A deferred column read later becomes one query per row. This would show it."""
    from tests.conftest import client_header

    headers = client_header(client_a.id, team_user.email)

    seeded = 0

    def count(pages):
        nonlocal seeded
        _seed_crawl(db, client_a, pages=pages, start=seeded)
        seeded += pages
        seen, stop = _record_sql(engine)
        try:
            client.get("/site-crawl/pages", headers=headers)
        finally:
            stop()
        return len([s for s in seen if s.lstrip().upper().startswith("SELECT")])

    small = count(3)
    large = count(40)
    assert large == small, (small, large)


# ── The keyword map asks Search Console only about its own terms ──


def _gsc_query(db, client_id, query, url, impressions):
    from decimal import Decimal

    from app.models.gsc import FactGscQueryPage

    db.add(
        FactGscQueryPage(
            id=uuid4(), client_id=client_id, date=date(2026, 10, 10), query=query,
            raw_url=url, normalized_url=url, country="", device="",
            impressions=Decimal(impressions), clicks=Decimal(1), ctr=Decimal("0.01"),
            average_position=Decimal("5"),
        )
    )


def test_the_page_lookup_can_be_limited_to_the_terms_wanted(db, client_a):
    from app.services.query_pages import pages_for_queries as _pages_for_queries

    _gsc_query(db, client_a.id, "managed it services", "https://x.test/a", 300)
    _gsc_query(db, client_a.id, "Managed IT Services", "https://x.test/b", 100)
    _gsc_query(db, client_a.id, "something else", "https://x.test/c", 900)
    db.commit()
    period = (date(2026, 10, 1), date(2026, 10, 31))

    everything = _pages_for_queries(db, client_a.id, period=period)
    only = _pages_for_queries(db, client_a.id, period=period, only={"managed it services"})

    assert set(everything) == {"managed it services", "something else"}
    assert set(only) == {"managed it services"}
    # The winning page for the term is the same either way.
    assert only["managed it services"] == everything["managed it services"]
    assert only["managed it services"].page_url == "https://x.test/a"


def test_asking_for_no_terms_reads_nothing(db, client_a):
    from app.services.query_pages import pages_for_queries as _pages_for_queries

    _gsc_query(db, client_a.id, "managed it services", "https://x.test/a", 300)
    db.commit()
    assert _pages_for_queries(db, client_a.id, period=(date(2026, 10, 1), date(2026, 10, 31)), only=set()) == {}


# ── One Google account, two addresses ──


def test_the_same_google_account_can_sign_in_under_two_addresses(client):
    """Your .com and .net addresses are one Google account, so Google reports the
    same id for both. The id is unique, so giving it to the second address was a
    duplicate-key error — AccessDenied, once sign-in began failing closed."""
    domain = _workspace_domain()
    first = _upsert(client, f"person@{domain}", google_sub="g-same")
    second = _upsert(client, f"person.alias@{domain}", google_sub="g-same")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text


def test_the_first_row_to_claim_a_google_id_keeps_it(db, client):
    from app.models.user import User

    domain = _workspace_domain()
    _upsert(client, f"one@{domain}", google_sub="g-keep")
    _upsert(client, f"two@{domain}", google_sub="g-keep")

    rows = {u.email: u.google_sub for u in db.query(User).filter(User.email.in_([f"one@{domain}", f"two@{domain}"]))}
    assert rows[f"one@{domain}"] == "g-keep"
    assert rows[f"two@{domain}"] is None  # matched by email, which is what everything reads


def test_a_returning_user_is_not_blanked_by_a_taken_id(db, client):
    from app.models.user import User

    domain = _workspace_domain()
    _upsert(client, f"stay@{domain}", google_sub="g-stay")
    _upsert(client, f"other@{domain}", google_sub="g-other")
    # `stay` signs in again, now reporting an id another row holds
    _upsert(client, f"stay@{domain}", google_sub="g-other")

    assert db.query(User).filter(User.email == f"stay@{domain}").one().google_sub == "g-stay"
