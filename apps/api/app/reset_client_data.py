"""Reset a client for a fresh start in v2: clear what was synced and what was set up, keep who they are and how they connect.

Usage, on the API service (one client at a time):

    # 1. See exactly what would be deleted, and what is kept
    python -m app.reset_client_data --client-slug acctek

    # 2. Delete it. Type the client's exact name to confirm.
    python -m app.reset_client_data --client-slug acctek --apply --confirm "ACCTek"

    # 3. Pull the data again (queues one job per source, long windows; the worker runs them)
    python -m app.reset_client_data --client-slug acctek --backfill

    # or list every client's counts, deleting nothing
    python -m app.reset_client_data --all

Dry run by default. Nothing is deleted without `--apply` and the client's name, and `--apply` takes one client,
never `--all`. Take a database backup first: this is not reversible.

What it clears
  Synced data (it is pulled again): Search Console, GA4, SE Ranking, crawl, Bing and SERP-feature facts, the
    staging tables, sync jobs and watermarks, and the derived tables built from them.
  Set up in the tool (it is entered again): baselines and goals, conversion events and pages, completion patterns,
    feeds, the watchlist and the monthly focus, AI visibility prompts, settings and runs, Decision Engine tasks,
    actions and records, thresholds, overrides, excluded pages, page stages, keyword targets, topics and decisions,
    and the old watch targets.

What it keeps
  The client record (name, domain, tier, business model, competitors and the other columns), the people who can
  see it, its Google and other integrations, the Bing site, Teamwork tasklist, annotations (their links to
  decisions and topics are cleared, since those go) and Copilot conversations.

A table that holds client data and is not listed here stops the run, so a new table cannot be skipped or deleted
by accident.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("organiciq.reset")

#: Deleted in this order: each table before the ones it depends on.
SYNCED = (
    "staging_ga4_events", "staging_ga4_traffic", "staging_gsc_daily", "staging_gsc_pages", "staging_gsc_query_pages",
    "staging_ser_ai_checks", "staging_ser_ai_presence", "staging_ser_ai_prompts", "staging_ser_ai_tracker_stats",
    "staging_ser_audit_issues", "staging_ser_audit_pages", "staging_ser_competitors", "staging_ser_keywords",
    "staging_ser_positions", "staging_ser_site_summary",
    "facts_bing_query_stats", "facts_crawl_internal_links", "facts_crawl_page_issues", "facts_crawl_page_schema",
    "facts_crawl_page_snapshots", "facts_ga4_events", "facts_ga4_traffic", "facts_gsc_daily", "facts_gsc_pages",
    "facts_gsc_query_pages", "facts_ser_ai_checks", "facts_ser_ai_presence", "facts_ser_ai_prompts",
    "facts_ser_ai_search_prompts", "facts_ser_ai_tracker_stats", "facts_ser_backlink_pages",
    "facts_ser_competitor_keywords", "facts_ser_competitors", "facts_ser_domain_keywords", "facts_ser_keyword_metrics",
    "facts_ser_keywords", "facts_ser_rankings", "facts_ser_site_summary", "facts_serp_features",
    "ga4_lead_measurements", "ga4_native_channel_observations", "keyword_page_suggestions",
    "refresh_queue", "sync_jobs", "data_watermarks", "monthly_review_snapshots", "site_health_snapshots",
)
SETUP = (
    "llm_responses", "llm_runs", "engine_tasks", "engine_actions", "client_focuses", "watchlist_keywords",
    "watchlist_buckets", "client_llm_prompts", "client_llm_settings", "client_feeds", "client_completion_patterns",
    "client_conversion_pages", "conversion_definitions", "baseline_versions", "monthly_records", "decision_thresholds",
    "constraint_overrides", "excluded_pages", "client_page_stages", "keyword_targets", "watch_targets",
    "decisions", "topics",
)
#: Never touched.
KEPT = ("integrations", "client_bing_sites", "user_clients", "annotations", "copilot_conversations", "ask_data_log", "client_schema_concepts", "schema_page_reports", "client_schema_ignores", "ctr_title_drafts", "inlink_states", "content_states", "content_model_runs")
#: Annotations point at decisions and topics, which are deleted, so the links go and the notes stay.
UNLINK_ANNOTATIONS = "update annotations set decision_id = null, topic_id = null where client_id = :c"

#: Windows for the pull-again step. Search Console keeps about sixteen months; GA4 keeps what the property does.


class UnclassifiedTable(Exception):
    """A table with client_id that this tool does not know whether to clear or keep."""


def _client(db: Session, *, slug: str | None, client_id: str | None) -> Any:
    from app.models.client import Client

    query = db.query(Client)
    row = query.filter(Client.slug == slug).one_or_none() if slug else query.filter(Client.id == UUID(client_id)).one_or_none()
    if row is None:
        raise LookupError("No such client.")
    return row


def check_every_table_is_classified(db: Session) -> None:
    """Fail if a table with client_id is in none of the lists, so a table added later is decided, not guessed."""
    inspector = inspect(db.get_bind())
    known = set(SYNCED) | set(SETUP) | set(KEPT)
    held = {t for t in inspector.get_table_names() if "client_id" in {c["name"] for c in inspector.get_columns(t)}}
    unknown = sorted(held - known)
    if unknown:
        raise UnclassifiedTable("Not classified as clear or keep: " + ", ".join(unknown))


def count(db: Session, table: str, client_id: UUID) -> int:
    return int(db.execute(text(f'select count(*) from "{table}" where client_id = :c'), {"c": str(client_id)}).scalar() or 0)


def plan(db: Session, client: Any) -> dict[str, dict[str, int]]:
    """How many rows each table holds for this client, by what would happen to them."""
    check_every_table_is_classified(db)
    return {
        "clear_synced": {t: count(db, t, client.id) for t in SYNCED},
        "clear_setup": {t: count(db, t, client.id) for t in SETUP},
        "kept": {t: count(db, t, client.id) for t in KEPT},
    }


def apply(db: Session, client: Any) -> dict[str, int]:
    """Delete the synced and set-up data for one client. The caller commits."""
    check_every_table_is_classified(db)
    deleted: dict[str, int] = {}
    # Notes outlive the decisions and topics they pointed at.
    db.execute(text(UNLINK_ANNOTATIONS), {"c": str(client.id)})
    for table in SETUP[:SETUP.index("decisions")] + SYNCED + SETUP[SETUP.index("decisions"):]:
        result = db.execute(text(f'delete from "{table}" where client_id = :c'), {"c": str(client.id)})
        if result.rowcount:
            deleted[table] = result.rowcount
    return deleted


def purge(db: Session, client: Any) -> dict[str, int]:
    """Delete a client and everything of its: the reset, then the rows that reset keeps, then the client. The caller commits.

    The hand-kept list this replaces had fallen behind the tables, so a client with a watchlist or a task could not be
    deleted. This one stops on any table it has not been told about (see `check_every_table_is_classified`).
    """
    deleted = apply(db, client)
    c = {"c": str(client.id)}
    result = db.execute(text("delete from copilot_messages where conversation_id in (select id from copilot_conversations where client_id = :c)"), c)
    if result.rowcount:
        deleted["copilot_messages"] = result.rowcount
    for table in ("annotations", "copilot_conversations", "client_bing_sites", "user_clients", "integrations"):
        result = db.execute(text(f'delete from "{table}" where client_id = :c'), c)
        if result.rowcount:
            deleted[table] = result.rowcount
    db.execute(text("delete from clients where id = :c"), {"c": str(client.id)})
    deleted["clients"] = 1
    return deleted


def enqueue_backfill(db: Session, client: Any, today: date | None = None) -> list[str]:
    """Queue one job per source with a long window. A source with no connection for this client is skipped."""
    from app.services.data_pull import queue_pull

    # The data was just cleared, so earlier successful jobs say nothing about what is there now.
    return queue_pull(db, client, today, force=True)


def _print_plan(client: Any, counts: dict[str, dict[str, int]]) -> None:
    logger.info("CLIENT %s (%s)", client.client_name, client.slug)
    for label, key in (("CLEAR, synced data (pulled again)", "clear_synced"), ("CLEAR, set up in the tool", "clear_setup"), ("KEEP", "kept")):
        rows = {t: n for t, n in counts[key].items() if n}
        logger.info("  %s: %d rows in %d tables", label, sum(rows.values()), len(rows))
        for table, n in rows.items():
            logger.info("      %-34s %9d", table, n)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--client-slug")
    target.add_argument("--client-id")
    target.add_argument("--all", action="store_true", help="list every client's counts; deletes nothing")
    parser.add_argument("--apply", action="store_true", help="delete; otherwise a dry run")
    parser.add_argument("--confirm", help="the client's exact name, required with --apply")
    parser.add_argument("--backfill", action="store_true", help="queue the pull-again jobs for the client")
    args = parser.parse_args()

    if args.apply and args.all:
        parser.error("--apply takes one client at a time, not --all")
    db = SessionLocal()
    try:
        if args.all:
            from app.models.client import Client

            for client in db.query(Client).order_by(Client.client_name):
                _print_plan(client, plan(db, client))
            logger.info("Dry run only. Nothing was deleted.")
            return 0

        client = _client(db, slug=args.client_slug, client_id=args.client_id)
        if args.backfill:
            queued = enqueue_backfill(db, client)
            db.commit()
            logger.info("Queued for %s: %s. The worker runs them; watch Settings or the job list.", client.client_name, ", ".join(queued) or "nothing")
            return 0

        _print_plan(client, plan(db, client))
        if not args.apply:
            logger.info("Dry run only. To delete, add --apply --confirm \"%s\".", client.client_name)
            return 0
        if args.confirm != client.client_name:
            logger.error("--confirm must be the client's exact name: %r", client.client_name)
            return 1
        deleted = apply(db, client)
        db.commit()
        logger.info("Deleted %d rows in %d tables. Next: --backfill to pull the data again.", sum(deleted.values()), len(deleted))
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
