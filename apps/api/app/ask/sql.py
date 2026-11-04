"""Run one model-written query, safely.

The database is the real guard (see schema.py); this adds what it cannot: one statement only, SELECT only, no way to
change the role or the client setting, and a cap on what comes back.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ask import schema

MAX_ROWS = 40
MAX_CHARS = 6000
STATEMENT_TIMEOUT_MS = 15000

_START = re.compile(r"(?is)^\s*(select|with)\b")
#: Words that have no place in a read-only question. `set_config` and `current_setting` could change or read the
#: client scope; the rest write, change the session, or reach outside the database.
_BLOCKED = re.compile(
    r"(?i)\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|call|do|vacuum|analyze|listen|notify|lock|"
    r"set|reset|show|execute|prepare|declare|fetch|set_config|current_setting|pg_[a-z_]+|dblink|lo_[a-z_]+)\b"
)


class QueryRejected(ValueError):
    pass


def check(query: str) -> str:
    q = (query or "").strip().rstrip(";").strip()
    if not q or not _START.match(q):
        raise QueryRejected("Only a single SELECT is allowed.")
    if ";" in q:
        raise QueryRejected("One statement at a time.")
    if "--" in q or "/*" in q:
        raise QueryRejected("Leave comments out of the query.")
    found = _BLOCKED.search(q)
    if found:
        raise QueryRejected(f"“{found.group(0)}” is not allowed in a read-only question.")
    return q


def run(db: Session, client_id: UUID, query: str) -> dict[str, Any]:
    """The rows (at most MAX_ROWS) as {columns, rows, truncated}, or {error}. Never raises for a bad query."""
    try:
        q = check(query)
    except QueryRejected as exc:
        return {"error": str(exc)}
    schema.ensure(db)
    try:
        # The scope row is written as the owner, in this transaction, before the transaction goes read-only and the role is taken.
        db.execute(text(f"insert into {schema.SCOPE_TABLE} (pid, xid, client_id) values (pg_backend_pid(), txid_current(), :c)"), {"c": str(client_id)})
        db.execute(text("set transaction read only"))
        db.execute(text(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        db.execute(text(f"set local role {schema.ROLE}"))
        result = db.execute(text(q))
        columns = list(result.keys())
        rows = result.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        payload = {"columns": columns, "rows": [[None if v is None else str(v) for v in r] for r in rows[:MAX_ROWS]], "truncated": truncated}
        out = json.dumps(payload)
        if len(out) > MAX_CHARS:
            while payload["rows"] and len(json.dumps(payload)) > MAX_CHARS:
                payload["rows"].pop()
            payload["truncated"] = True
        return payload
    except Exception as exc:  # noqa: BLE001 - a bad query is an answer for the model, not a failure
        return {"error": str(exc).splitlines()[0][:300]}
    finally:
        db.rollback()  # ends the read-only transaction and drops the role and the scope row with it
