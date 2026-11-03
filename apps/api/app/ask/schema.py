"""The read-only door into a client's data.

Questions are answered by a model that writes SQL, so the database has to make the dangerous things impossible, not
the prompt. Each question runs as `ask_data_reader`, a role that can only SELECT from the tables listed here, and
row-level security on every one of them shows it only the rows of the client in `app.client_id`. The role has no
other table, no writes, and a short statement timeout; the transaction is read-only.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("organiciq.ask")

ROLE = "ask_data_reader"

#: What may be asked about. Nothing with credentials, tokens or other clients' settings is here.
TABLES = (
    "facts_ga4_traffic",
    "facts_ga4_events",
    "facts_gsc_daily",
    "facts_gsc_pages",
    "facts_gsc_query_pages",
    "facts_ser_rankings",
    "facts_ser_competitors",
    "facts_ser_competitor_keywords",
    "facts_serp_features",
    "facts_bing_query_stats",
    "facts_crawl_page_snapshots",
    "facts_crawl_page_issues",
    "facts_crawl_internal_links",
    "llm_runs",
    "llm_responses",
    "conversion_definitions",
    "watchlist_buckets",
    "watchlist_keywords",
    "annotations",
    "engine_tasks",
)

_ready = False


def ensure(db: Session) -> None:
    """Create the role, the grants and the row-level policies, if they are not there. Safe to run again."""
    global _ready
    if _ready:
        return
    existing = {r[0] for r in db.execute(text("select table_name from information_schema.tables where table_schema = 'public'"))}
    db.execute(text(f"""
        do $$ begin
          if not exists (select 1 from pg_roles where rolname = '{ROLE}') then create role {ROLE} nologin; end if;
        end $$;
    """))
    # The session user must be able to become the role (SET LOCAL ROLE).
    db.execute(text(f"grant {ROLE} to current_user"))
    db.execute(text(f"grant usage on schema public to {ROLE}"))
    for table in TABLES:
        if table not in existing:
            continue
        db.execute(text(f"alter table {table} enable row level security"))
        db.execute(text(f"drop policy if exists ask_scope on {table}"))
        db.execute(text(
            f"create policy ask_scope on {table} for select to {ROLE} "
            "using (client_id = nullif(current_setting('app.client_id', true), '')::uuid)"
        ))
        db.execute(text(f"grant select on {table} to {ROLE}"))
    db.commit()
    _ready = True
    logger.info("Ask the data: read-only role and row policies are in place")


def table_notes(db: Session) -> str:
    """Each askable table with its columns, for the model's prompt."""
    rows = db.execute(text(
        "select table_name, column_name, data_type from information_schema.columns "
        "where table_schema = 'public' and table_name = any(:t) order by table_name, ordinal_position"
    ), {"t": list(TABLES)})
    out: dict[str, list[str]] = {}
    for table, column, kind in rows:
        if column in ("id", "client_id", "created_at", "updated_at"):
            continue
        out.setdefault(table, []).append(f"{column} {kind.replace('character varying', 'text').replace('timestamp with time zone', 'timestamptz')}")
    return "\n".join(f"{t}({', '.join(cols)})" for t, cols in out.items())
