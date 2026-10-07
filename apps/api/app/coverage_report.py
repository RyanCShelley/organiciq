"""Which rules ran for each client, and why the rest did not.

A trigger that finds nothing and a trigger that never ran look identical
in a findings list, and the second one is the one that needs fixing. This
separates them.

    python -m app.coverage_report [--client slug]
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from datetime import date, timedelta

from app.core.db import SessionLocal
from app.models.client import Client, ClientStatus
from app.services.lever_engine import diagnose

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.coverage")


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

        totals: Counter[str] = Counter()
        findings_by_rule: Counter[str] = Counter()
        for client in clients:
            result = diagnose(db, client, from_date=start, to_date=end)
            if not result.coverage:
                logger.info("%-26s engine blocked", client.client_name[:26])
                totals["engine_blocked"] += 1
                continue
            for row in result.coverage:
                rule, status = str(row["rule_id"]), str(row["status"])
                totals[f"{rule} {status}"] += 1
                findings_by_rule[rule] += int(row["findings"])
            if args.client:
                logger.info("%s", client.client_name)
                for row in result.coverage:
                    logger.info(
                        "  %-10s %-26s findings %-4s %s",
                        row["rule_id"],
                        row["status"],
                        row["findings"],
                        row.get("notes") or "",
                    )

        if not args.client:
            logger.info("%d clients\n", len(clients))
            logger.info("%-34s %s", "rule / status", "clients")
            for key, count in sorted(totals.items()):
                logger.info("  %-32s %d", key, count)
            logger.info("\n%-14s %s", "rule", "findings (all clients)")
            for rule, count in sorted(findings_by_rule.items()):
                logger.info("  %-12s %d", rule, count)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
