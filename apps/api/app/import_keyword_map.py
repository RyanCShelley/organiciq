"""Load an on-page keyword map into a client's keyword targets.

    python -m app.import_keyword_map --client sma-marketing --file map.csv [--apply]

Dry by default: it prints what would change and writes nothing. Every row is
written as `confirmed`, because a human maintained the spreadsheet — this is
somebody's decision arriving in bulk, not a suggestion.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path

from app.core.db import SessionLocal
from app.imports.keyword_map_csv import parse_keyword_map
from app.models.client import Client
from app.models.decision import KeywordTarget

logger = logging.getLogger("organiciq.keyword_map")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument(
        "--priority-sections",
        default="",
        help="Comma-separated sections whose terms are priority, e.g. "
        "'Core Pages,Industry Pages'. V1 reads priority terms and nothing else.",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    terms = parse_keyword_map(Path(args.file))
    if not terms:
        logger.error("No terms parsed from %s", args.file)
        return 1

    priority_sections = {
        s.strip().lower() for s in args.priority_sections.split(",") if s.strip()
    }

    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.slug == args.client).one_or_none()
        if client is None:
            logger.error("No client with slug %s", args.client)
            return 1

        existing = {
            row.keyword: row
            for row in db.query(KeywordTarget)
            .filter(KeywordTarget.client_id == client.id)
            .all()
        }

        created = updated = unchanged = 0
        for term in terms:
            priority = term.section.lower() in priority_sections
            row = existing.get(term.keyword)
            if row is None:
                created += 1
                if args.apply:
                    db.add(
                        KeywordTarget(
                            client_id=client.id,
                            keyword=term.keyword,
                            target_url=term.target_url,
                            term_role=term.term_role,
                            group_name=term.section,
                            priority=priority,
                            source="confirmed",
                        )
                    )
            elif (
                row.target_url != term.target_url
                or row.term_role != term.term_role
                or row.priority != priority
            ):
                updated += 1
                if args.apply:
                    row.target_url = term.target_url
                    row.term_role = term.term_role
                    row.group_name = term.section
                    row.priority = priority
                    row.source = "confirmed"
            else:
                unchanged += 1

        by_role = Counter(t.term_role for t in terms)
        by_section = Counter(t.section for t in terms)
        logger.info("%s: %d terms in the map", client.slug, len(terms))
        logger.info("  primary %d, secondary %d", by_role["primary"], by_role["secondary"])
        for section, n in by_section.most_common():
            mark = "  <- priority" if section.lower() in priority_sections else ""
            logger.info("  %-18s %3d%s", section, n, mark)
        logger.info(
            "  created %d, updated %d, unchanged %d%s",
            created, updated, unchanged, "" if args.apply else "   (dry run)",
        )

        if args.apply:
            db.commit()
            logger.info("  written")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
