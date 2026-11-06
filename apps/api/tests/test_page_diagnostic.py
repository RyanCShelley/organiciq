"""Diagnosing a ticked page: the live read, the existing rules, and what could not be judged."""

from __future__ import annotations

from datetime import date

import pytest

from app.models.gsc import FactGscQueryPage
from app.services import page_diagnostic as pd
from tests.conftest import client_header

ROW = {"position": 12.2, "impressions": 1891, "clicks": 3, "expected_extra_clicks": 11.7}
URL = "https://shop.example/products/tanning-oil"


def page(*, head="", body="", status=200, final_url=URL):
    html = f"<html><head><title>Tanning Oil</title><meta name='description' content='Dark tan'>{head}</head><body><h1>Platinum Tanning Oil</h1>{body}</body></html>"

    async def fetch(url):
        return pd.Fetched(status=status, final_url=final_url, headers={}, body=html)

    return fetch


FAQ_PAGE = (
    "<h2>Frequently asked questions</h2><p>Does it stain?</p>"
    "<h2>How long does it last?</h2><p>Two days.</p>"
)


def run(fetch, search="tanning oil", url=URL, row=ROW, domain="shop.example"):
    return pd.diagnose(search=search, url=url, row=row, client_domain=domain, fetch=fetch)


def test_an_faq_the_page_already_has_fires_the_markup_rule():
    out = run(page(body=FAQ_PAGE))
    assert out["read"]["ok"] is True
    assert [p["action_id"] for p in out["prescriptions"]] == ["V-7"]
    fired = out["prescriptions"][0]
    assert fired["branch"] == "visibility" and fired["target_url"] == URL and fired["effort_min"] == 15
    assert "FAQPage" in fired["done_when"]


def test_a_page_with_faq_markup_already_gets_no_prescription_and_says_why():
    schema = '<script type="application/ld+json">{"@type":"FAQPage","mainEntity":[]}</script>'
    out = run(page(head=schema, body=FAQ_PAGE))
    assert out["prescriptions"] == []
    reasons = {n["action_id"]: n["reason"] for n in out["not_judged"]}
    assert reasons["V-7"] == "The page already has FAQ markup."


def test_what_cannot_be_judged_is_said_and_never_read_as_no_problem():
    out = run(page())
    ids = {n["action_id"]: n["reason"] for n in out["not_judged"]}
    assert set(ids) == {"V-6", "V-7", "V-5", "V-4"}
    assert "page that should own the search" in ids["V-6"] and "featured snippet" in ids["V-5"] and "crawl of the whole site" in ids["V-4"]
    assert ids["V-7"] == "The page has no FAQ section, so there are no questions to mark up."


def test_observations_say_where_the_search_appears_and_how_clicks_compare():
    out = run(page())
    texts = [o["text"] for o in out["observations"]]
    assert any("appears in the title, the main heading" in t or "appears in the title" in t for t in texts)
    assert any("Click-through is 0.2% against" in t and "well under" in t for t in texts)


def test_a_search_missing_from_the_page_is_a_note_not_a_problem():
    out = run(page(), search="best after sun lotion")
    note = next(o for o in out["observations"] if "does not appear as a phrase" in o["text"])
    assert note["level"] == "note" and "not a content gap" in note["text"]


def test_a_noindex_page_and_a_canonical_elsewhere_are_problems():
    noindex = run(page(head='<meta name="robots" content="noindex">'))
    assert any(o["level"] == "problem" and "noindex" in o["text"] for o in noindex["observations"])
    moved = run(page(head='<link rel="canonical" href="https://shop.example/other-page">'))
    assert any(o["level"] == "problem" and "canonical points elsewhere" in o["text"] for o in moved["observations"])


def test_a_page_that_errors_is_reported_and_no_rule_is_run_on_it():
    out = run(page(status=404))
    assert out["read"]["status"] == 404 and out["prescriptions"] == []
    assert any("error (404)" in o["text"] for o in out["observations"])
    assert all("did not load" in n["reason"] for n in out["not_judged"])


def test_a_page_off_the_clients_site_is_never_fetched():
    called = []

    async def fetch(url):
        called.append(url)
        raise AssertionError("must not be fetched")

    out = run(fetch, url="https://evil.example/x", domain="shop.example")
    assert out["read"]["ok"] is False and "not on this client's website" in out["read"]["error"]
    assert called == []
    assert run(fetch, url="ftp://shop.example/x")["read"]["error"] == "That is not a web address."


def test_a_redirect_off_the_site_is_refused():
    out = run(page(final_url="https://elsewhere.example/landing"))
    assert out["read"]["ok"] is False and "redirects off this client's website" in out["read"]["error"]


def test_www_and_bare_domains_are_the_same_site():
    assert run(page(final_url="https://www.shop.example/products/tanning-oil"), domain="www.shop.example")["read"]["ok"] is True


@pytest.fixture()
def gsc_row(db, client_a):
    db.add(
        FactGscQueryPage(
            client_id=client_a.id, date=date(2026, 8, 10), query="tanning oil", raw_url=f"https://{client_a.domain}/p",
            normalized_url=f"https://{client_a.domain}/p", country="usa", device="DESKTOP",
            impressions=1000, clicks=5, ctr=0, average_position=12.0,
        )
    )
    db.commit()


def test_the_route_recomputes_the_numbers_and_runs_the_rules(client, db, client_a, admin_user, gsc_row, monkeypatch):
    seen = {}

    async def fetch(url):
        seen["url"] = url
        return pd.Fetched(200, url, {}, "<html><head><title>x</title></head><body><h1>Tanning oil</h1></body></html>")

    monkeypatch.setattr(pd, "_fetch", fetch)
    response = client.post(
        "/v2/engine/diagnose",
        json={"month": "2026-09", "selections": [{"search": "Tanning Oil", "page": f"https://{client_a.domain}/p"}]},
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["position"] == 12.0 and result["impressions"] == 1000 and result["read"]["ok"] is True
    assert seen["url"] == f"https://{client_a.domain}/p"


def test_a_pair_not_in_search_console_is_not_fetched(client, db, client_a, admin_user, monkeypatch):
    async def fetch(url):
        raise AssertionError("must not be fetched")

    monkeypatch.setattr(pd, "_fetch", fetch)
    response = client.post(
        "/v2/engine/diagnose",
        json={"selections": [{"search": "made up", "page": f"https://{client_a.domain}/nope"}]},
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.json()["results"][0]["read"]["error"].startswith("That search and page are not in")


def test_no_more_than_five_pages_at_a_time(client, db, client_a, admin_user):
    picks = [{"search": f"s{i}", "page": f"https://{client_a.domain}/{i}"} for i in range(6)]
    response = client.post("/v2/engine/diagnose", json={"selections": picks}, headers=client_header(client_a.id, admin_user.email))
    assert response.status_code == 422


def served(*, status=200, headers=None, html="", size=None):
    async def fetch(url):
        return pd.Fetched(status=status, final_url=URL, headers=headers or {}, body=html, requested_url=url, user_agent="OrganicIQ-page-diagnostic/1.0", fetched_at="2026-11-06T14:30:00+00:00", size=size or len(html))

    return fetch


def test_every_flag_says_where_it_came_from():
    """A finding is only as good as what it was read from, so each one names the tag or header, the address, the status, the time and who asked."""
    meta = run(served(html="<html><head><title>Tanning Oil</title><meta name='robots' content='noindex, follow'></head><body><h1>Platinum Tanning Oil</h1><p>words</p></body></html>"))
    flag = next(o for o in meta["observations"] if "noindex" in o["text"])
    assert flag["level"] == "problem" and "the meta robots tag says “noindex, follow”" in flag["how"]
    assert URL in flag["how"] and "HTTP 200" in flag["how"] and "Nov 06, 2026 at 14:30 UTC" in flag["how"] and "OrganicIQ-page-diagnostic/1.0" in flag["how"] and "can differ from what Google" in flag["how"]
    header = run(served(headers={"x-robots-tag": "noindex"}, html="<html><head><title>Tanning Oil</title></head><body><h1>Platinum Tanning Oil</h1><p>words</p></body></html>"))
    assert "the X-Robots-Tag response header says “noindex”" in next(o for o in header["observations"] if "noindex" in o["text"])["how"]
    assert all(o.get("how") for o in meta["observations"] if o["level"] in ("problem", "ok")), "no finding is left without its source"
    assert meta["read"]["received"]["status"] == 200 and meta["read"]["received"]["bytes"] > 0


def test_a_host_bot_check_is_not_read_as_a_page_with_no_title_and_noindex():
    """Live home pages were reported as noindex with no title and no words when the host sent our reader a captcha or an empty shell."""
    captcha = served(status=202, headers={"sg-captcha": "challenge"}, html="<html><head><meta name='robots' content='noindex'><meta http-equiv='refresh' content='0;/.well-known/sgcaptcha/?r=%2F'></head></html>")
    out = run(captcha)
    assert out["read"]["blocked"] == "The site answered our reader with SiteGround's captcha instead of the page."
    assert [o["level"] for o in out["observations"]] == ["note"] and "noindex" not in out["observations"][0]["text"] and "Nothing about it is judged" in out["observations"][0]["text"]
    assert "HTTP 202" in out["observations"][0]["how"] and out["read"]["received"]["headers"]["sg-captcha"] == "challenge" and "sgcaptcha" in out["read"]["received"]["body_starts"]
    assert out["prescriptions"] == [] and all("could not be read" in n["reason"] for n in out["not_judged"])

    empty = run(served(html="<html><head><meta name='robots' content='noindex'></head><body></body></html>"))
    assert empty["read"]["blocked"].startswith("The response had no title, no heading and no text")
    assert not any("noindex" in o["text"] for o in empty["observations"]), "an empty response says nothing about the page"
    assert empty["read"]["received"]["body_starts"].startswith("<html><head><meta name='robots'")

    traffic = pd.diagnose_page(focus="traffic", url=URL, client_domain="shop.example", fetch=captcha, evidence={"lost": []})
    assert traffic["read"]["blocked"] and traffic["suggestions"] == [] and "noindex" not in traffic["observations"][0]["text"]
