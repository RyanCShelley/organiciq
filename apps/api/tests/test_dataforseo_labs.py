"""DataForSEO Labs: a domain's rankings and keyword market data.

Billed per request and per row, so these tests are mostly about asking once,
asking correctly, and not mistaking an omitted keyword for an error.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.integrations import dataforseo

CONFIG = dataforseo.DataForSeoConfig(login="l", password="p")


def _http(body: dict, seen: list | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _task(items: list[dict]) -> dict:
    return {"tasks": [{"status_code": 20000, "result": [{"items": items}]}]}


def test_ranked_keywords_asks_once_for_the_top_ten_biggest_first():
    seen: list = []
    http = _http(_task([]), seen)
    dataforseo.ranked_keywords("rival.com", source="uk", config=CONFIG, client=http)

    assert len(seen) == 1
    url, payload = seen[0]
    assert url.endswith("/dataforseo_labs/google/ranked_keywords/live")
    task = payload[0]
    assert task["target"] == "rival.com"
    assert task["location_code"] == 2826 and task["language_code"] == "en"
    assert task["limit"] == 1000
    assert task["item_types"] == ["organic"]
    assert task["filters"] == [["ranked_serp_element.serp_item.rank_group", "<=", 10]]
    assert task["order_by"] == ["keyword_data.keyword_info.search_volume,desc"]


def test_ranked_keywords_reads_the_documented_item_shape():
    http = _http(
        _task(
            [
                {
                    "keyword_data": {
                        "keyword": "heat pump installation",
                        "keyword_info": {"search_volume": 900, "cpc": None},
                        "keyword_properties": {"keyword_difficulty": 31},
                    },
                    "ranked_serp_element": {
                        "serp_item": {"rank_group": 3, "url": "https://rival.com/heat-pumps"}
                    },
                },
                {"keyword_data": {"keyword": ""}},
            ]
        )
    )
    rows = dataforseo.ranked_keywords("rival.com", config=CONFIG, client=http)
    assert rows == [
        {
            "keyword": "heat pump installation",
            "position": 3.0,
            "volume": 900.0,
            "difficulty": 31.0,
            "cpc": None,
            "url": "https://rival.com/heat-pumps",
        }
    ]


def test_keyword_overview_batches_at_the_documented_limit_and_skips_unaskable_terms():
    seen: list = []
    http = _http(_task([]), seen)
    keywords = [f"term {i}" for i in range(701)] + ["x" * 81, "one two three four five six seven eight nine ten eleven"]
    out = dataforseo.keyword_overview(keywords, config=CONFIG, client=http)

    assert [len(payload[0]["keywords"]) for _, payload in seen] == [700, 1]
    assert len(out) == len(keywords) and not any(row["is_data_found"] for row in out)


def test_keyword_overview_reads_the_item_shape_and_marks_omitted_terms_not_found():
    http = _http(
        _task(
            [
                {
                    "keyword": "Heat Pump Installation",
                    "keyword_info": {"search_volume": 900, "cpc": 4.2, "competition": 0.4},
                    "keyword_properties": {"keyword_difficulty": 31},
                    "search_intent_info": {"main_intent": "commercial"},
                }
            ]
        )
    )
    rows = dataforseo.keyword_overview(
        ["heat pump installation", "nobody searches this"], config=CONFIG, client=http
    )
    assert rows[0] == {
        "keyword": "Heat Pump Installation",
        "volume": 900.0,
        "difficulty": 31.0,
        "cpc": 4.2,
        "competition": 0.4,
        "intents": ["commercial"],
        "is_data_found": True,
    }
    assert rows[1]["keyword"] == "nobody searches this" and rows[1]["is_data_found"] is False


def test_a_failed_task_is_an_error_not_an_empty_answer():
    http = _http({"tasks": [{"status_code": 40501, "status_message": "Invalid Field"}]})
    with pytest.raises(dataforseo.DataForSeoError, match="40501"):
        dataforseo.ranked_keywords("rival.com", config=CONFIG, client=http)


def test_an_unconfigured_account_fails_loudly(monkeypatch):
    monkeypatch.setattr(dataforseo, "load_config", lambda: None)
    with pytest.raises(dataforseo.DataForSeoError, match="not configured"):
        dataforseo.keyword_overview(["x"])


def test_an_unknown_market_falls_back_to_the_us():
    assert dataforseo.market("mars") == (2840, "en")
    assert dataforseo.market("au") == (2036, "en")


def test_the_scheduler_does_not_queue_work_it_cannot_do(db, client_a, monkeypatch):
    from app.services import daily_sync

    monkeypatch.setattr(dataforseo, "load_config", lambda: None)
    assert daily_sync.enqueue_due_keyword_metrics(db)["enqueued"] == 0
    assert daily_sync.enqueue_due_competitor_keywords(db)["enqueued"] == 0
