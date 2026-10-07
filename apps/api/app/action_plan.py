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
from app.models.client import Client
from app.services.lever_engine import action_rule_id, diagnose

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
                client.custom_growth_action_allowance
                if client.custom_growth_action_allowance is not None
                else (tier.growth_action_allowance if tier else 0)
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

            actions = [
                row
                for row in result.findings
                if action_rule_id(row) is not None
                and not row.evidence_json.get("below_floor")
                and not row.evidence_json.get("value_error")
            ]
            below = [
                row for row in result.findings if row.evidence_json.get("below_floor")
            ]
            broken = [
                row for row in result.findings if row.evidence_json.get("value_error")
            ]

            logger.info(
                "  %d actions above the floor, %d below, %d unvalued\n",
                len(actions), len(below), len(broken),
            )
            for index, row in enumerate(actions, start=1):
                evidence = row.evidence_json
                taken = "  ← taken" if index <= (allowance or 0) else ""
                logger.info(
                    "  %2d. %-4s %5.2f leads/mo  %3s min  %-12s %s%s",
                    index,
                    evidence.get("rule_id", "?"),
                    evidence.get("expected_leads_monthly", 0.0),
                    evidence.get("estimated_minutes", "?"),
                    evidence.get("value_basis", "?"),
                    (row.page_url or row.query or "site-wide")[-44:],
                    taken,
                )
                tie = evidence.get("tiebreak_volume")
                if tie:
                    logger.info("        (tiebreak: %s searches/mo)", int(tie))
                logger.info(
                    "%s",
                    textwrap.fill(
                        row.recommended_action or "",
                        width=80,
                        initial_indent="        ",
                        subsequent_indent="        ",
                    )[:400],
                )
            for row in broken:
                logger.info(
                    "  UNVALUED  %-6s %s",
                    row.evidence_json.get("rule_id")
                    or row.evidence_json.get("gate")
                    or row.evidence_json.get("audit_signal"),
                    (row.page_url or row.query or "site-wide")[-50:],
                )
            if allowance and len(actions) < allowance:
                logger.info(
                    "\n  SHORT: %d of %d. Nothing is padded — weaker work is not an action.",
                    len(actions), allowance,
                )
                # What a short plan nearly offered. Without this the floor is
                # an assertion: the reader is told there was nothing better
                # without being shown what came closest, which is the one
                # thing that says whether the floor is set right.
                for row in sorted(
                    below,
                    key=lambda r: -float(
                        r.evidence_json.get("expected_leads_monthly") or 0.0
                    ),
                )[:5]:
                    evidence = row.evidence_json
                    logger.info(
                        "        below the floor: %-4s %5.3f leads/mo  %s",
                        evidence.get("rule_id", "?"),
                        evidence.get("expected_leads_monthly", 0.0),
                        (row.page_url or row.query or "site-wide")[-44:],
                    )
                    # A conversion rule valued at zero is either a page
                    # with nothing to recover or an estimate that lost its
                    # inputs, and the two read identically without these.
                    if "sessions" in evidence:
                        logger.info(
                            "            %s sessions, %s leads, benchmark %.2f%% (%s)"
                            " → shortfall %s",
                            evidence.get("sessions"),
                            evidence.get("leads"),
                            evidence.get("benchmark_rate_pct") or 0.0,
                            evidence.get("benchmark_source", "?"),
                            evidence.get("shortfall_leads"),
                        )
            logger.info("")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
