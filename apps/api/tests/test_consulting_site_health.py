"""Site health in the consulting reports: the two scores and their checks, taken from the screen's own saved months."""

from __future__ import annotations

from datetime import date

from app.models.site_health import SiteHealthSnapshot
from app.services import consulting_exec, consulting_report, consulting_site_health
from tests.conftest import client_header
from tests.test_portal_access import consult


def payload(seo: int, geo: int, issues: list[str]):
    return {
        "crawl": {"date": "2026-10-28", "pages": 120, "limit": 500, "hit_limit": False},
        "seo": {"score": seo, "grade": "B", "pages": 120, "checks": [{"key": "titles", "label": "Page titles", "weight": 10, "score": 80, "affected": 24, "total": 120, "detail": "x", "urls": issues}]},
        "geo": {"score": geo, "grade": "C", "partial": True, "signals": [
            {"key": "schema", "label": "Structured data", "weight": 20, "score": 60, "measured": True, "detail": {}, "summary": None, "items": [], "affected": 0},
            {"key": "citation", "label": "Citation", "weight": 10, "score": 0, "measured": False, "detail": {}, "summary": None, "items": [], "affected": 0}]},
        "weights": {},
    }


def seed(db, client):
    db.add_all([
        SiteHealthSnapshot(client_id=client.id, month="2026-09", crawl_date=date(2026, 9, 28), payload=payload(70, 50, ["https://x/a", "https://x/b"])),
        SiteHealthSnapshot(client_id=client.id, month="2026-10", crawl_date=date(2026, 10, 28), payload=payload(76, 58, ["https://x/b", "https://x/c"])),
    ])
    db.commit()


def test_both_scores_with_the_change_on_last_month_and_the_checks_behind_them(db, client_a):
    seed(db, client_a)
    sh = consulting_site_health.build(db, client_a, "2026-10")
    assert (sh["seo"]["score"], sh["seo"]["previous"], sh["seo"]["change"]) == (76, 70, 6)
    assert (sh["geo"]["score"], sh["geo"]["change"], sh["geo"]["partial"]) == (58, 8, True)
    assert sh["seo"]["checks"] == [{"label": "Page titles", "score": 80, "affected": 24, "total": 120}]
    assert sh["geo"]["signals"][0]["score"] == 60 and sh["geo"]["signals"][1]["score"] is None  # an unmeasured signal is blank, never 0
    assert (sh["new_issues"], sh["fixed_issues"]) == (1, 1)
    assert sh["pages"] == 120 and sh["source"] == "Organic IQ site crawl"


def test_the_first_month_has_no_change_and_no_issue_counts(db, client_a):
    seed(db, client_a)
    sh = consulting_site_health.build(db, client_a, "2026-09")
    assert sh["seo"]["change"] is None and sh["new_issues"] is None


def test_a_month_without_a_crawl_has_no_site_health(db, client_a):
    assert consulting_site_health.build(db, client_a, "2026-10") is None


def test_both_reports_carry_site_health(db, client_a):
    seed(db, client_a)
    assert consulting_report.headline(db, client_a, "2026-10")["site_health"]["seo"]["score"] == 76
    assert consulting_exec.build(db, client_a, "2026-10")["site_health"]["geo"]["score"] == 58


def test_the_client_sees_it_in_the_published_snapshot(client, db, client_a, admin_user):
    consult(db, client_a)
    seed(db, client_a)
    h = client_header(client_a.id, admin_user.email)
    client.put("/v2/consulting/report", json={"month": "2026-10", "analysis": "Words."}, headers=h)
    client.post("/v2/consulting/report/state", json={"month": "2026-10", "to": "published"}, headers=h)
    got = client.get("/v2/consulting/portal/reports", headers=h).json()["monthly"]["data"]
    assert got["site_health"]["seo"]["score"] == 76
