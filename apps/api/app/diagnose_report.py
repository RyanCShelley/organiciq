"""Print what the Decision Engine says about one client, without the UI.

Every rule in the engine is proven by tests and, until this is run, none has
produced a finding from real data. Thresholds were reasoned about rather than
calibrated, so the first honest test is reading real output and seeing which
of them is wrong.

Read-only: it runs the same `diagnose` the dashboard calls and prints the
result. Nothing is written.

    python -m app.diagnose_report --client sma-marketing [--days 30]
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import date, timedelta

from app.core.db import SessionLocal
from app.models.client import Client
from app.services.lever_engine import diagnose

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.diagnose_report")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True, help="client slug")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.slug == args.client).one_or_none()
        if client is None:
            logger.error("No client with slug %r", args.client)
            return 1

        end = date.today()
        start = end - timedelta(days=args.days - 1)
        result = diagnose(db, client, from_date=start, to_date=end)

        logger.info("%s — %s to %s", client.client_name, start, end)
        logger.info("ready=%s  %s", result.ready, (result.message or "")[:90])
        logger.info("findings=%d  recommended=%d", len(result.findings), len(result.recommendations))

        by_gate = Counter(
            row.evidence_json.get("gate")
            or row.evidence_json.get("audit_signal")
            or row.lever
            for row in result.findings
        )
        logger.info("\nBy rule:")
        for name, count in by_gate.most_common():
            logger.info("  %-28s %d", name, count)

        states = Counter(
            "recommended"
            if row.is_recommended_action
            else "suppressed"
            if row.suppressed_by
            else "core work"
            if row.core_work
            else "contested"
            if row.override_count >= 3
            else (row.promotion_blocked_reason or "other")
            for row in result.findings
        )
        logger.info("\nBy state:")
        for name, count in states.most_common():
            logger.info("  %-40s %d", str(name)[:40], count)

        logger.info("\nTop findings:")
        logger.info("  %-6s %-9s %s", "score", "impact", "diagnosis")
        for row in sorted(result.findings, key=lambda r: -r.priority_score)[: args.limit]:
            logger.info("  %-6.1f %-9.1f %s", row.priority_score, row.impact, row.diagnosis[:90])
            if row.is_recommended_action:
                logger.info("         -> %s", row.recommended_action[:110])
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
