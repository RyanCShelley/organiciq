from __future__ import annotations

import time
from datetime import date
from decimal import Decimal

from app.models.gsc import FactGscQueryPage
from app.services import ctr_optimizer, inlinks
from app.services.memo import Memo


def test_the_memo_keeps_a_result_until_its_key_changes_or_it_expires():
    memo = Memo(size=2, ttl=60.0)
    calls = []
    assert memo.get("a", lambda: calls.append(1) or "one") == "one"
    assert memo.get("a", lambda: calls.append(2) or "two") == "one" and calls == [1]
    memo.get("b", lambda: "b")
    memo.get("c", lambda: "c")  # evicts the oldest ("a")
    assert memo.get("a", lambda: "again") == "again"
    short = Memo(size=2, ttl=0.01)
    short.get("x", lambda: 1)
    time.sleep(0.03)
    assert short.get("x", lambda: 2) == 2


def _gsc(db, client, day, query, url, impressions, clicks, position):
    db.add(FactGscQueryPage(client_id=client.id, date=day, query=query, raw_url=url, normalized_url=url, country="usa", device="DESKTOP",
                            impressions=Decimal(impressions), clicks=Decimal(clicks), ctr=Decimal(0), average_position=Decimal(position)))


def test_the_twelve_months_come_from_one_query_and_match_the_range_query_for_each_month(db, client_a):
    for month in (8, 9, 10):
        _gsc(db, client_a, date(2026, month, 10), "seo audit", "https://shop.example/a", 500, 5, 4.0)
        _gsc(db, client_a, date(2026, month, 12), "seo audit", "https://shop.example/b", 300, 30, 2.0)
    db.commit()
    end = date(2026, 10, 20)
    series = {m["month"]: m for m in ctr_optimizer.monthly(db, client_a, end, [])}
    assert len(series) == 12 and series["2026-07"]["score"] is None and series["2026-07"]["clicks"] == 0
    for month in (8, 9, 10):
        pairs = ctr_optimizer._pairs(db, client_a, date(2026, month, 1), min(date(2026, month, 28), end), [])
        score, clicks, expected = ctr_optimizer._score(pairs)
        assert series[f"2026-{month:02d}"]["score"] == score and series[f"2026-{month:02d}"]["clicks"] == round(clicks)


def test_a_page_asks_the_database_for_its_own_pairs_only(db, client_a):
    _gsc(db, client_a, date(2026, 10, 10), "seo audit", "https://shop.example/a", 500, 5, 4.0)
    _gsc(db, client_a, date(2026, 10, 10), "seo audit", "https://shop.example/b", 500, 50, 4.0)
    db.commit()
    only = ctr_optimizer._pairs(db, client_a, date(2026, 10, 1), date(2026, 10, 31), [], "https://shop.example/a")
    assert list(only) == [("seo audit", "https://shop.example/a")]


def test_page_vectors_are_kept_per_crawl_and_only_new_pages_are_worked_out(monkeypatch, client_a):
    class Page:
        def __init__(self, url):
            self.normalized_url, self.snapshot_date = url, date(2026, 10, 1)

    seen = []
    monkeypatch.setattr(inlinks.keyword_matcher, "embed_pages", lambda pages: seen.append([p.normalized_url for p in pages]) or [[len(p.normalized_url)] for p in pages])
    a, b, c = Page("/a"), Page("/bb"), Page("/ccc")
    assert inlinks._vectors(None, client_a, [a, b]).keys() == {"/a", "/bb"}
    assert inlinks._vectors(None, client_a, [b, c]).keys() == {"/bb", "/ccc"}
    assert inlinks._vectors(None, client_a, [a, b, c]).keys() == {"/a", "/bb", "/ccc"}
    assert seen == [["/a", "/bb"], ["/ccc"]], "each page is worked out once"
