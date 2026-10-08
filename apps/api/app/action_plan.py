"""The growth actions for a client, ranked, with what each is worth.

What a strategist picks from at the start of the month: the candidates
above the floor in order, the time each takes, and whether there are
fewer than the plan allows.

    python -m app.action_plan --client aquaman-leak-detection
"""

from __future__ import annotations

import argparse
import logging
import textwrap
from datetime import date, timedelta

from app.core.db import SessionLocal
from app.services.plan_allowances import resolve_plan_allowances
from app.models.client import Client
from app.services.lever_engine import diagnose

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.action_plan")

#: The clients under test. Everything else is unconfigured and reporting
#: on it is noise.
DEFAULT_CLIENTS = ("aquaman-leak-detection", "sma-marketing")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", action="append")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    slugs = tuple(args.client) if args.client else DEFAULT_CLIENTS
    db = SessionLocal()
    try:
        end = date.today()
        start = end - timedelta(days=args.days - 1)
        for slug in slugs:
            client = db.query(Client).filter(Client.slug == slug).one_or_none()
            if client is None:
                logger.info("No client with slug %r", slug)
                continue

            tier = client.tier
            allowance = (
                resolve_plan_allowances(client, tier).growth_action_allowance
                if tier is not None
                else 0
            )
            result = diagnose(db, client, from_date=start, to_date=end)

            logger.info("=" * 86)
            logger.info(
                "%s  ·  %s  ·  allowance %s  ·  %s to %s",
                client.client_name,
                tier.tier_name if tier else "—",
                allowance,
                start,
                end,
            )
            if not result.ready:
                logger.info("  engine blocked: %s\n", (result.message or "")[:120])
                continue

            # The same list the API serves and the screen reads. This was
            # open-coded here while the web read a different field entirely,
            # so this command and that page disagreed about what the
            # client's actions even were.
            actions = result.growth_actions
            constraint = result.constraint

            logger.info(
                "  constraint: %s · %d actions\n",
                constraint.layer.value if constraint else "none measurable",
                len(actions),
            )
            for index, row in enumerate(actions, start=1):
                evidence = row.evidence_json
                taken = "  ← taken" if index <= (allowance or 0) else ""
                logger.info(
                    "  %2d. %-4s %-11s %9s %-14s %3s min  %s%s",
                    index,
                    evidence.get("rule_id", "?"),
                    row.stage.value,
                    ("precondition" if evidence.get("precondition")
                     else f"{evidence.get('demand', 0.0):,.0f}"),
                    evidence.get("demand_unit", ""),
                    evidence.get("estimated_minutes", "?"),
                    (row.page_url or row.query or "site-wide")[-40:],
                    taken,
                )
                logger.info(
                    "%s",
                    textwrap.fill(
                        row.recommended_action or "",
                        width=80,
                        initial_indent="        ",
                        subsequent_indent="        ",
                    )[:400],
                )
            if allowance and len(actions) < allowance:
                # Nothing is padded, and the shortfall is stated rather than
                # filled with weaker work.
                logger.info(
                    "\n  SHORT: %d of %d. Nothing is padded — weaker work is not an action.",
                    len(actions), allowance,
                )
            logger.info("")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
