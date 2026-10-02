"""What the data-driven confidence score would do, before it is switched on.

C1 replaces a per-lever constant (70-85) with a score read from the evidence.
Every constant sat above the promotion gate of 60, so that gate has never
rejected a finding; a score that can fall below it would start rejecting work,
and nobody has yet seen which work that is. Applying the score is therefore
off by default and this report is what the decision to switch it on rests on.

Read-only: runs the same `diagnose` the dashboard calls, reads the score
already recorded on each finding, and prints the distribution.

    python -m app.confidence_distribution [--days 30] [--gate 60]
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter, defaultdict
from datetime import date, timedelta

from app.core.db import SessionLocal
from app.models.client import Client, ClientStatus
from app.services.lever_engine import diagnose

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.confidence_distribution")

BUCKETS = [(0, 40), (40, 50), (50, 55), (55, 60), (60, 70), (70, 80), (80, 101)]


def _bucket(value: float) -> str:
    for low, high in BUCKETS:
        if low <= value < high:
            return f"{low}-{high - 1}"
    return "?"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--gate", type=float, default=60.0)
    parser.add_argument("--client", help="one slug; default is every active client")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Client).filter(Client.status != ClientStatus.ARCHIVED)
        if args.client:
            query = query.filter(Client.slug == args.client)
        clients = query.order_by(Client.client_name).all()

        end = date.today()
        start = end - timedelta(days=args.days - 1)

        buckets: Counter[str] = Counter()
        by_lever: dict[str, list[float]] = defaultdict(list)
        scores: list[float] = []
        demoted: list[tuple[str, str, float, float]] = []
        promoted_total = 0
        skipped: list[str] = []

        for client in clients:
            result = diagnose(db, client, from_date=start, to_date=end)
            if not result.ready:
                skipped.append(f"{client.client_name}: {(result.message or '')[:60]}")
                continue
            promoted = {row.rule_key for row in result.recommendations}
            promoted_total += len(promoted)
            for row in result.findings:
                scored = row.evidence_json.get("data_driven_confidence")
                if scored is None:
                    continue
                scored = float(scored)
                scores.append(scored)
                buckets[_bucket(scored)] += 1
                by_lever[str(row.lever)].append(scored)
                if row.rule_key in promoted and scored < args.gate:
                    demoted.append(
                        (client.client_name, str(row.lever), float(row.confidence), scored)
                    )

        logger.info("%d clients, %s to %s", len(clients), start, end)
        for line in skipped:
            logger.info("  skipped — %s", line)
        if not scores:
            logger.info("\nNo findings carried a score.")
            return 0

        scores.sort()
        logger.info("\n%d findings scored", len(scores))
        logger.info(
            "  min %.1f   p25 %.1f   median %.1f   p75 %.1f   max %.1f",
            scores[0],
            scores[len(scores) // 4],
            scores[len(scores) // 2],
            scores[(len(scores) * 3) // 4],
            scores[-1],
        )

        logger.info("\nDistribution:")
        for low, high in BUCKETS:
            name = f"{low}-{high - 1}"
            count = buckets.get(name, 0)
            bar = "#" * round(40 * count / len(scores))
            logger.info("  %-7s %4d  %s", name, count, bar)

        logger.info("\nBy lever (count, median):")
        for lever, values in sorted(by_lever.items(), key=lambda row: -len(row[1])):
            values.sort()
            logger.info("  %-24s %4d  %.1f", lever, len(values), values[len(values) // 2])

        logger.info(
            "\nAt a gate of %.0f: %d of %d promoted findings would stop being "
            "recommended.",
            args.gate,
            len(demoted),
            promoted_total,
        )
        for name, lever, was, now in sorted(demoted, key=lambda row: row[3])[:30]:
            logger.info("  %-26s %-22s %.0f -> %.1f", name[:26], lever, was, now)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
