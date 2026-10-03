"""Print finding cards the way a strategist reads them.

What happened · Why · Do this · Expected result · Check on.

Read-only. Runs the same `diagnose` the dashboard calls.

    python -m app.finding_cards --client sma-marketing [--limit 3]
"""

from __future__ import annotations

import argparse
import logging
import textwrap
from datetime import date, timedelta

from app.core.db import SessionLocal
from app.models.client import Client
from app.services.lever_engine import diagnose

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.finding_cards")


def _wrap(text: str, indent: str = "     ") -> str:
    return textwrap.fill(text, width=92, initial_indent=indent, subsequent_indent=indent)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--cause", help="only cards with this cause")
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

        rows = [row for row in result.findings if row.evidence_json.get("cause")]
        if args.cause:
            rows = [row for row in rows if row.evidence_json["cause"] == args.cause]
        rows.sort(key=lambda row: -row.priority_score)

        logger.info("%s — %s to %s", client.client_name, start, end)
        logger.info("%d findings, %d carrying a prescription\n", len(result.findings), len(rows))

        for row in rows[: args.limit]:
            evidence = row.evidence_json
            logger.info("=" * 92)
            logger.info("%s  ·  score %.1f", row.label.upper(), row.priority_score)
            logger.info("")
            logger.info("  WHAT HAPPENED")
            logger.info(_wrap(row.diagnosis))
            logger.info("")
            logger.info("  WHY — %s", evidence.get("cause_summary", "?"))
            facts = ", ".join(
                f"{key.replace('_', ' ')} {value}"
                for key, value in (evidence.get("evidence") or {}).items()
                if value is not None
            )
            if facts:
                logger.info(_wrap(facts))
            logger.info("")
            logger.info("  DO THIS")
            for index, action in enumerate(evidence.get("actions") or [], start=1):
                who = " [human]" if action.get("human") else ""
                logger.info(_wrap(f"{index}. {action['text']}{who}", indent="     "))
                if action.get("target"):
                    logger.info(_wrap(action["target"], indent="        "))
                if action.get("detail"):
                    logger.info(_wrap(action["detail"], indent="        "))
            logger.info("")
            logger.info("  EXPECTED RESULT   %s", evidence.get("expected_impact") or "—")
            logger.info(
                "  CHECK ON          %s  (%s)",
                (end + timedelta(days=int(evidence.get("verify_after_days") or 28))).isoformat(),
                evidence.get("verify_metric") or "—",
            )
            if evidence.get("routed_to"):
                logger.info("  ROUTED TO         %s", evidence["routed_to"])
            logger.info("")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
