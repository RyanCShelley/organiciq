"""Which mapped pages the engine can actually read, and which saved actions rest on one it could not.

The visibility rules (V-1 to V-8) judge a page from the crawl: its title, headings,
FAQ, schema and link counts. The crawl only records those for a page fetched as a
2xx, and a keyword target is typed by a person (`http://`, `www.`, a trailing
slash), so a target can point at a crawl row that holds a title and nothing else.
Rules that read that as "the page has none" prescribe work the page does not
need. This reports how many targets are in that state, per client, and which
saved actions were built on one, so those plans can be re-run.

Read-only.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.urls import normalize_url
from app.models.client import WORKED_STATUSES, Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.decision import KeywordTarget, MonthlyRecord
from app.services.target_signals import _latest_crawl_date, _snapshot_for

#: The rules whose verdict comes from what the crawl read on the target page.
CRAWL_JUDGED_ACTIONS = frozenset({"V-1", "V-2", "V-3", "V-4", "V-8"})

STATUS_OK = "ok"
STATUS_REDIRECT_FOLLOWED = "redirect_followed"
STATUS_NOT_IN_CRAWL = "not_in_crawl"
STATUS_UNREADABLE = "unreadable"
STATUS_HEADINGS_NOT_CAPTURED = "headings_not_captured"

#: What each state means for the plan, in the words the report shows.
DETAIL = {
    STATUS_REDIRECT_FOLLOWED: "Mapped to a URL that redirects; the engine now reads the page it lands on.",
    STATUS_NOT_IN_CRAWL: "No crawl row for this URL, so nothing is prescribed from it. Map the live URL.",
    STATUS_UNREADABLE: "The crawl did not get a 2xx page here (redirect that goes nowhere, error, or blocked).",
    STATUS_HEADINGS_NOT_CAPTURED: "Crawled before headings were captured. Re-crawl the site.",
}


def classify(crawl: dict, url: str) -> tuple[str, str | None]:
    """The state of one target URL, and the status code behind it where there is one."""
    row = crawl.get(normalize_url(url))
    if row is None:
        return STATUS_NOT_IN_CRAWL, None
    resolved = _snapshot_for(crawl, url)
    code = resolved.status_code if resolved is not None else None
    if resolved is None or resolved.sections is None:
        if code is not None and not (200 <= code < 300):
            return STATUS_UNREADABLE, str(code)
        return STATUS_HEADINGS_NOT_CAPTURED, None
    if resolved is not row:
        return STATUS_REDIRECT_FOLLOWED, str(row.status_code) if row.status_code else None
    return STATUS_OK, None


def report(db: Session) -> dict:
    clients_out: list[dict] = []
    totals = {"clients": 0, "targets": 0, "needing_attention": 0, "affected_actions": 0}

    for client in (
        db.query(Client).filter(Client.status.in_(WORKED_STATUSES)).order_by(Client.client_name)
    ):
        targets = (
            db.query(KeywordTarget)
            .filter(KeywordTarget.client_id == client.id, KeywordTarget.source == "confirmed")
            .all()
        )
        targets = [t for t in targets if (t.target_url or "").strip()]
        crawl_date = _latest_crawl_date(db, client.id)
        crawl = (
            {
                row.normalized_url: row
                for row in db.query(FactCrawlPageSnapshot).filter(
                    FactCrawlPageSnapshot.client_id == client.id,
                    FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
                    FactCrawlPageSnapshot.snapshot_date == crawl_date,
                )
            }
            if crawl_date
            else {}
        )

        counts = {
            STATUS_OK: 0,
            STATUS_REDIRECT_FOLLOWED: 0,
            STATUS_NOT_IN_CRAWL: 0,
            STATUS_UNREADABLE: 0,
            STATUS_HEADINGS_NOT_CAPTURED: 0,
        }
        problems: list[dict] = []
        flagged: set[str] = set()
        for target in targets:
            url = target.target_url.strip()
            status, code = classify(crawl, url)
            counts[status] += 1
            if status != STATUS_OK:
                flagged.add(normalize_url(url))
                problems.append(
                    {
                        "keyword": target.keyword,
                        "target_url": url,
                        "status": status,
                        "http_status": code,
                        "detail": DETAIL[status],
                    }
                )

        latest = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.client_id == client.id)
            .order_by(MonthlyRecord.month.desc())
            .first()
        )
        affected: list[dict] = []
        if latest is not None and flagged:
            for action in (latest.record or {}).get("actions", []):
                if (
                    action.get("id") in CRAWL_JUDGED_ACTIONS
                    and normalize_url(str(action.get("target_url") or "")) in flagged
                ):
                    affected.append(
                        {
                            "month": latest.month,
                            "id": action.get("id"),
                            "title": action.get("title"),
                            "target_url": action.get("target_url"),
                        }
                    )

        if not targets and not crawl_date:
            continue
        clients_out.append(
            {
                "client_id": str(client.id),
                "client_name": client.client_name,
                "crawl_date": crawl_date.isoformat() if crawl_date else None,
                "targets": len(targets),
                **counts,
                "problems": problems,
                "affected_actions": affected,
            }
        )
        totals["clients"] += 1
        totals["targets"] += len(targets)
        totals["needing_attention"] += len(problems)
        totals["affected_actions"] += len(affected)

    return {"totals": totals, "clients": clients_out}
