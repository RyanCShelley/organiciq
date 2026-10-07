"""What the six-trigger brief assumes, checked against real data.

Read-only. Answers the questions the brief says to verify before building:
whether the internal link graph is populated and carries in_content, whether
GA4 views look session-scoped enough for a pages-per-session proxy, whether
query-page data is dense enough for cannibalisation, and what schema the
crawl actually holds.

    python -m app.engine_inspect --client sma-marketing
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from sqlalchemy import func

from app.core.db import SessionLocal
from app.models.client import Client, ClientStatus
from app.models.crawl import FactCrawlInternalLink, FactCrawlPageSchema
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerKeyword

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.inspect")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Client).filter(Client.status != ClientStatus.ARCHIVED)
        if args.client:
            query = query.filter(Client.slug == args.client)
        clients = query.order_by(Client.client_name).all()
        end = date.today()
        start = end - timedelta(days=args.days - 1)

        logger.info(
            "%-26s %7s %7s %7s %8s %7s %7s",
            "client", "links", "incont", "qpages", "pps(med)", "schema", "parse!",
        )
        for client in clients:
            links = (
                db.query(func.count(FactCrawlInternalLink.id))
                .filter(FactCrawlInternalLink.client_id == client.id)
                .scalar()
                or 0
            )
            in_content = (
                db.query(func.count(FactCrawlInternalLink.id))
                .filter(
                    FactCrawlInternalLink.client_id == client.id,
                    FactCrawlInternalLink.in_content.is_(True),
                    FactCrawlInternalLink.is_template.is_(False),
                )
                .scalar()
                or 0
            )
            qpages = (
                db.query(func.count(FactGscQueryPage.id))
                .filter(
                    FactGscQueryPage.client_id == client.id,
                    FactGscQueryPage.date >= start,
                    FactGscQueryPage.date <= end,
                )
                .scalar()
                or 0
            )
            # Organic only, matching what the engine counts. Measuring
            # across every channel inflated the page counts and made the
            # gate look broken when it was filtering correctly.
            from app.services.lever_engine import MANAGED_CHANNELS

            rows = (
                db.query(
                    FactGa4Traffic.normalized_url,
                    func.sum(FactGa4Traffic.sessions),
                    func.sum(FactGa4Traffic.views),
                    func.sum(FactGa4Traffic.engaged_sessions),
                )
                .filter(
                    FactGa4Traffic.client_id == client.id,
                    FactGa4Traffic.date >= start,
                    FactGa4Traffic.date <= end,
                    FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
                )
                .group_by(FactGa4Traffic.normalized_url)
                .all()
            )
            ppses = sorted(
                float(views) / float(sessions)
                for _u, sessions, views, _e in rows
                if sessions and float(sessions) >= 30 and views is not None
            )
            engaged_known = sum(1 for _u, _s, _v, e in rows if e is not None)
            median_pps = ppses[len(ppses) // 2] if ppses else 0.0
            schema = (
                db.query(func.count(FactCrawlPageSchema.id))
                .filter(FactCrawlPageSchema.client_id == client.id)
                .scalar()
                or 0
            )
            bad = (
                db.query(func.count(FactCrawlPageSchema.id))
                .filter(
                    FactCrawlPageSchema.client_id == client.id,
                    FactCrawlPageSchema.parse_error.isnot(None),
                )
                .scalar()
                or 0
            )
            logger.info(
                "%-26s %7d %7d %7d %8.2f %7d %7d",
                client.client_name[:26], links, in_content, qpages, median_pps, schema, bad,
            )
            if args.client:
                logger.info(
                    "   pages with >=30 sessions: %d, engaged_sessions present on %d of %d",
                    len(ppses), engaged_known, len(rows),
                )
                if ppses:
                    logger.info(
                        "   pps spread: min %.2f p25 %.2f median %.2f p75 %.2f max %.2f",
                        ppses[0],
                        ppses[len(ppses) // 4],
                        median_pps,
                        ppses[(len(ppses) * 3) // 4],
                        ppses[-1],
                    )
                # Landed here and never converted anywhere. Both GA4 pulls
                # are keyed on landingPage, so this is sessions that began
                # on the page and produced no conversion in the whole visit
                # — a stronger statement than "this page has no form".
                from app.models.config import ConversionDefinition
                from app.models.ga4 import FactGa4Event

                lead_events = [
                    row[0]
                    for row in db.query(ConversionDefinition.event_name)
                    .filter(
                        ConversionDefinition.client_id == client.id,
                        ConversionDefinition.active.is_(True),
                    )
                    .all()
                ]
                leads_by_url = {}
                if lead_events:
                    leads_by_url = {
                        url: float(total)
                        for url, total in db.query(
                            FactGa4Event.normalized_url,
                            func.sum(FactGa4Event.event_count),
                        )
                        .filter(
                            FactGa4Event.client_id == client.id,
                            FactGa4Event.date >= start,
                            FactGa4Event.date <= end,
                            FactGa4Event.event_name.in_(lead_events),
                            FactGa4Event.channel.in_(MANAGED_CHANNELS),
                        )
                        .group_by(FactGa4Event.normalized_url)
                        .all()
                    }
                for floor in (10, 30, 100):
                    busy = [
                        (u, float(se))
                        for u, se, _v, _e in rows
                        if se and float(se) >= floor
                    ]
                    dry = [u for u, _ in busy if leads_by_url.get(u, 0.0) <= 0]
                    logger.info(
                        "   pages >=%3d sessions: %3d, of which zero leads: %3d",
                        floor, len(busy), len(dry),
                    )

                topics = (
                    db.query(func.count(FactSerKeyword.id))
                    .filter(
                        FactSerKeyword.client_id == client.id,
                        FactSerKeyword.topic_id.isnot(None),
                    )
                    .scalar()
                    or 0
                )
                logger.info("   tracked keywords carrying a topic_id: %d", topics)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
