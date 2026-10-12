"""The full SERP feature list, and the T-2 it unblocks.

`earned_serp_features` records what a client *won*. T-2 fires on a feature
present that the client does *not* hold, so the difference between those two
questions is the whole finding — and until now only the first was stored,
which is why T-2 sat in BLOCKED_ACTIONS from the day it was written.

Every call here is billed in production, so the tests that matter most are
the ones about not spending: nothing pulls without being asked, and nothing
pulls twice for the same day.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from app.decisions.catalog import BLOCKED_ACTIONS, TRAFFIC_ACTIONS, prescribe_page
from app.decisions.page_targets import PageCandidate
from app.integrations import dataforseo
from app.models.client import Client
from app.models.decision import KeywordTarget
from app.models.seranking import FactSerpFeature
from app.services.serp_features import STALE_AFTER_DAYS, load, pull, terms_to_pull

TODAY = date(2026, 10, 12)


def _page(**kw) -> PageCandidate:
    base = dict(
        url="/a",
        impressions=2000.0,
        clicks=40.0,
        position=6.0,
        top_query="how is carbon fibre made",
        serp_pulled=True,
        missing_serp_features=("featured_snippet", "people_also_ask"),
    )
    base.update(kw)
    return PageCandidate(**base)


def _t(page: PageCandidate):
    return prescribe_page(page, actions=TRAFFIC_ACTIONS)


# ── The client ──────────────────────────────────────────────────────────────


def test_item_types_is_the_whole_feature_list():
    found = dataforseo.parse(
        {
            "keyword": "x",
            "item_types": ["organic", "ai_overview", "people_also_ask"],
            "items": [{"type": "ai_overview", "items": [{"domain": "www.rival.com"}]}],
        }
    )
    assert found.item_types == ("organic", "ai_overview", "people_also_ask")
    assert found.holds("ai_overview", "rival.com")
    assert not found.holds("ai_overview", "acme.com")


def test_a_task_level_failure_is_an_error_despite_the_200():
    def handler(request: httpx.Request) -> httpx.Response:
        # DataForSEO answers 200 with a per-task status, so the HTTP code
        # alone does not say the pull worked.
        return httpx.Response(
            200,
            json={"tasks": [{"status_code": 40501, "status_message": "Invalid Field"}]},
        )

    with pytest.raises(dataforseo.DataForSeoError, match="40501"):
        dataforseo.fetch(
            "x",
            config=dataforseo.DataForSeoConfig(login="l", password="p"),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )


def test_the_request_is_an_array_of_tasks():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "status_code": 20000,
                        "result": [{"keyword": "x", "item_types": ["organic"]}],
                    }
                ]
            },
        )

    dataforseo.fetch(
        "x",
        config=dataforseo.DataForSeoConfig(login="l", password="p"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    # The body is an array even for one task.
    assert seen["body"].startswith("[")
    assert seen["auth"].startswith("Basic ")


# ── Spending ────────────────────────────────────────────────────────────────


def test_the_same_term_is_not_pulled_twice_in_a_day(db: Session, client_a: Client):
    db.add(KeywordTarget(client_id=client_a.id, keyword="carbon fibre", target_url="/a"))
    db.commit()

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.read().decode())
        return httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "status_code": 20000,
                        "result": [{"keyword": "carbon fibre", "item_types": ["organic"]}],
                    }
                ]
            },
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    config = dataforseo.DataForSeoConfig(login="l", password="p")
    import app.integrations.dataforseo as dfs

    original = dfs.load_config
    dfs.load_config = lambda: config  # type: ignore[assignment]
    try:
        assert pull(db, client_a, today=TODAY, client_http=http)[0] == 1
        # Already paid for today.
        assert pull(db, client_a, today=TODAY, client_http=http)[0] == 0
    finally:
        dfs.load_config = original  # type: ignore[assignment]
    assert len(calls) == 1


def test_declared_targets_are_pulled_before_tracked_terms(
    db: Session, client_a: Client
):
    db.add(KeywordTarget(client_id=client_a.id, keyword="declared", target_url="/a"))
    db.commit()
    assert terms_to_pull(db, client_a, limit=5)[0] == "declared"


# ── Reading back ────────────────────────────────────────────────────────────


def _store(db: Session, client: Client, when: date, types: list[str]):
    db.add(
        FactSerpFeature(
            client_id=client.id,
            pulled_on=when,
            keyword="carbon fibre",
            item_types=types,
            holders={"ai_overview": ["rival.com"]},
        )
    )
    db.commit()


def test_a_stale_serp_is_not_read_back(db: Session, client_a: Client):
    # A SERP from two months ago is not evidence about this one.
    _store(db, client_a, TODAY - timedelta(days=STALE_AFTER_DAYS + 1), ["ai_overview"])
    assert load(db, client_a, today=TODAY) == {}


def test_the_newest_reading_wins(db: Session, client_a: Client):
    _store(db, client_a, TODAY - timedelta(days=30), ["organic"])
    _store(db, client_a, TODAY - timedelta(days=2), ["organic", "featured_snippet"])
    row = load(db, client_a, today=TODAY)["carbon fibre"]
    assert "featured_snippet" in row.item_types
    assert row.held_by("ai_overview", "www.rival.com")


# ── T-2 ─────────────────────────────────────────────────────────────────────


def test_t2_is_no_longer_blocked():
    assert "T-2" not in {b.action_id for b in BLOCKED_ACTIONS}
    # V-5 still is, and for the half that is still missing.
    v5 = next(b for b in BLOCKED_ACTIONS if b.action_id == "V-5")
    assert "per-section table" in v5.reason


def test_t2_fires_on_a_feature_the_client_does_not_hold():
    found = _t(_page())
    assert found is not None
    assert found.action_id == "T-2"
    assert "featured snippet" in found.title
    assert "40 to 60 word answer" in found.done_when


def test_t2_stays_quiet_until_a_serp_has_been_pulled():
    # No pull is not the same as a SERP with nothing on it.
    assert _t(_page(serp_pulled=False, missing_serp_features=())) is None


def test_t2_ignores_features_a_page_cannot_win_by_being_rewritten():
    assert _t(_page(missing_serp_features=("organic", "paid", "related_searches"))) is None


def test_t2_does_not_fire_on_a_navigational_query():
    assert _t(_page(top_query_is_navigational=True)) is None


# ── Bad credentials ─────────────────────────────────────────────────────────


def _auth_handler(status: int = 401, task_code: int | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if task_code is not None:
            return httpx.Response(
                200,
                json={"tasks": [{"status_code": task_code, "status_message": "Auth error"}]},
            )
        return httpx.Response(status, text="Unauthorized")

    return handler


@pytest.mark.parametrize(
    "kwargs", [{"status": 401}, {"status": 403}, {"task_code": 40101}]
)
def test_rejected_credentials_are_their_own_failure(kwargs):
    """However they arrive — as an HTTP status or inside a 200."""
    with pytest.raises(dataforseo.DataForSeoAuthError):
        dataforseo.fetch(
            "x",
            config=dataforseo.DataForSeoConfig(login="l", password="p"),
            client=httpx.Client(transport=httpx.MockTransport(_auth_handler(**kwargs))),
        )


def test_a_pull_stops_on_bad_credentials_rather_than_failing_once_per_term(
    db: Session, client_a: Client
):
    """Setting the variables to the placeholders out of a README reads as
    configured. It failed 425 times, which is how this was found."""
    for i in range(5):
        db.add(
            KeywordTarget(client_id=client_a.id, keyword=f"term {i}", target_url="/a")
        )
    db.commit()

    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, text="Unauthorized")

    import app.integrations.dataforseo as dfs

    original = dfs.load_config
    dfs.load_config = lambda: dataforseo.DataForSeoConfig(login="l", password="p")  # type: ignore[assignment]
    try:
        with pytest.raises(dataforseo.DataForSeoAuthError):
            pull(
                db,
                client_a,
                today=TODAY,
                client_http=httpx.Client(transport=httpx.MockTransport(handler)),
            )
    finally:
        dfs.load_config = original  # type: ignore[assignment]

    assert len(calls) == 1, "kept going after the credentials were rejected"


def test_t2_does_not_prescribe_a_feature_a_page_cannot_reach():
    """SMA's "aeo agency", verbatim.

    The SERP carries an AI Overview, a People Also Ask box and an image pack,
    and SMA holds no organic position on page one at all. A feature is drawn
    from the results on page one, so the format that wins one cannot pay for
    a page sitting at 47.
    """
    assert _t(_page(position=47.0)) is None
    assert _t(_page(position=None)) is None

    found = _t(_page(position=4.0))
    assert found is not None and found.action_id == "T-2"
    assert "position 4.0" in found.why


def test_the_pull_asks_for_the_ai_overview_to_be_resolved():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={"tasks": [{"status_code": 20000, "result": [{"keyword": "x", "item_types": []}]}]},
        )

    dataforseo.fetch(
        "x",
        config=dataforseo.DataForSeoConfig(login="l", password="p"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert '"load_async_ai_overview":true' in seen["body"].replace(" ", "")


# ── The monthly schedule ────────────────────────────────────────────────────


def _as_configured(monkeypatch):
    import app.integrations.dataforseo as dfs

    monkeypatch.setattr(
        dfs, "load_config", lambda: dataforseo.DataForSeoConfig(login="l", password="p")
    )


def test_the_pull_runs_once_a_month_not_once_a_day(
    db: Session, client_a: Client, monkeypatch
):
    from app.core import settings as settings_module
    from app.services.serp_features import maybe_pull_serp_features

    _as_configured(monkeypatch)
    settings = settings_module.get_settings()
    monkeypatch.setattr(settings, "serp_pull_enabled", True, raising=False)
    monkeypatch.setattr(settings, "serp_pull_hour_utc", 99, raising=False)
    # Before its hour, nothing.
    assert maybe_pull_serp_features(db) is False

    monkeypatch.setattr(settings, "serp_pull_hour_utc", 0, raising=False)
    assert maybe_pull_serp_features(db) is True
    # Every query is billed, so a second pass the same month must not start
    # the bill again.
    assert maybe_pull_serp_features(db) is False


def test_nothing_pulls_when_dataforseo_is_not_configured(
    db: Session, client_a: Client, monkeypatch
):
    from app.core import settings as settings_module
    from app.services.serp_features import maybe_pull_serp_features
    import app.integrations.dataforseo as dfs

    monkeypatch.setattr(dfs, "load_config", lambda: None)
    settings = settings_module.get_settings()
    monkeypatch.setattr(settings, "serp_pull_enabled", True, raising=False)
    monkeypatch.setattr(settings, "serp_pull_hour_utc", 0, raising=False)
    assert maybe_pull_serp_features(db) is False


def test_a_client_without_search_console_data_is_not_pulled_for(
    db: Session, client_a: Client
):
    """T-2 needs the page's position and top query, both from Search Console.

    Without them a SERP reading has nothing to attach to and expires — they
    are read back for 45 days — before anything can use it.
    """
    from datetime import date as _date
    from app.models.gsc import FactGscPage
    from app.services.serp_features import _worth_pulling_for

    assert _worth_pulling_for(db, client_a) is False

    db.add(
        FactGscPage(
            client_id=client_a.id,
            date=_date(2026, 10, 1),
            raw_url="https://x.test/a",
            normalized_url="https://x.test/a",
            impressions=10,
            clicks=1,
        )
    )
    db.commit()
    assert _worth_pulling_for(db, client_a) is True
