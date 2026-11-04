"""The read-only door into a client's data.

Questions are answered by a model that writes SQL, so the database has to make the dangerous things impossible, not
the prompt. Each question runs as `ask_data_reader`, a role that can only SELECT from the tables listed here, and
row-level security on every one of them shows it only the rows of the client in the scope row written for this
transaction. The scope is NOT a session setting: a setting (`app.client_id`) can be overwritten by any SELECT that reaches `set_config`
by a spelling the query filter does not see (`U&"\\0073et_config"(...)`, `query_to_xml('se'||'lect ...')`). It is a row in
`ask_scope_state`, keyed by this backend and transaction, read through a SECURITY DEFINER function; the role has no privilege on that
table and the transaction is read-only. The role has no other table, no writes, and a short statement timeout.
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

SCOPE_TABLE = "ask_scope_state"
SCOPE_FUNCTION = "ask_scope_client"

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
    # Where the client for the running question is kept: one row per transaction, gone when it ends. Only the owner can touch it.
    db.execute(text(f"create unlogged table if not exists {SCOPE_TABLE} (pid integer not null, xid bigint not null, client_id uuid not null, primary key (pid, xid))"))
    db.execute(text(f"revoke all on {SCOPE_TABLE} from public"))
    db.execute(text(f"revoke all on {SCOPE_TABLE} from {ROLE}"))
    db.execute(text(
        f"create or replace function {SCOPE_FUNCTION}() returns uuid language sql stable security definer set search_path = pg_catalog, public "
        f"as $$ select client_id from public.{SCOPE_TABLE} where pid = pg_backend_pid() and xid = txid_current() $$"
    ))
    db.execute(text(f"revoke all on function {SCOPE_FUNCTION}() from public"))
    db.execute(text(f"grant execute on function {SCOPE_FUNCTION}() to {ROLE}"))
    for table in TABLES:
        if table not in existing:
            continue
        db.execute(text(f"alter table {table} enable row level security"))
        db.execute(text(f"drop policy if exists ask_scope on {table}"))
        db.execute(text(
            f"create policy ask_scope on {table} for select to {ROLE} "
            f"using (client_id = {SCOPE_FUNCTION}())"
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
