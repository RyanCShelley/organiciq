"""How much of the keyword map is filled in, and what the UI will show.

Every ranking finding asks a person which page owns the term. This says
how many of those questions are already answered, per client, and prints
what the page would render so the endpoint can be checked without a login.

Read-only.

    python -m app.keyword_map_report [--client sma-marketing] [--rows 10]
"""

from __future__ import annotations

import argparse
import logging

from app.core.db import SessionLocal
from app.models.client import Client, ClientStatus
from app.services.decisions import keyword_page_map_view

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.keyword_map")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="one slug; default is every client")
    parser.add_argument("--rows", type=int, default=0, help="sample rows to print")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Client).filter(Client.status != ClientStatus.ARCHIVED)
        if args.client:
            query = query.filter(Client.slug == args.client)
        clients = query.order_by(Client.client_name).all()

        logger.info("%-30s %8s %8s %8s", "client", "tracked", "mapped", "pages")
        for client in clients:
            view = keyword_page_map_view(db, client.id)
            rows = view["keywords"]
            mapped = sum(1 for row in rows if row["mapped"])
            logger.info(
                "%-30s %8d %8d %8d",
                client.client_name[:30],
                len(rows),
                mapped,
                len(view["pages"]),
            )
            if args.rows and rows:
                for row in rows[: args.rows]:
                    logger.info(
                        "    %-34s vol %-8s diff %-5s pos %-10s suggests %s",
                        row["keyword"][:34],
                        int(row["volume"]) if row["volume"] else "-",
                        int(row["difficulty"]) if row["difficulty"] else "-",
                        int(row["current_position"]) if row["current_position"] else "not ranking",
                        row["suggested_page_url"] or "-",
                    )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
