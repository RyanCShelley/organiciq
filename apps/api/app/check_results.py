"""Judge the actions whose check date has arrived.

    python -m app.check_results                      # every client, dry run
    python -m app.check_results --apply
    python -m app.check_results --client sma-marketing --apply
    python -m app.check_results --capture-missing --apply

`--capture-missing` reads the `before` for an action saved before the results
loop existed. It works because every metric is read as-of a date: an action
prescribed in September can still be measured against what September knew.
Without it those actions have no reading to compare and stay unjudgeable
forever.
"""

from __future__ import annotations

import argparse
from datetime import date

from app.core.db import SessionLocal
from app.models.client import Client
from app.models.decision import MonthlyRecord
from app.services.results import (
    _slotted,
    capture_before,
    check_due,
    measure,
    metric_key_for,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="slug; omit for every client")
    parser.add_argument("--apply", action="store_true", help="write; otherwise report")
    parser.add_argument(
        "--capture-missing",
        action="store_true",
        help="read the before value for actions saved before this existed",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-read a before value already stored, to correct a bad one",
    )
    parser.add_argument("--today", help="ISO date to judge as of; defaults to today")
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    db = SessionLocal()
    clients = db.query(Client)
    if args.client:
        clients = clients.filter(Client.slug == args.client)

    for client in clients.all():
        records = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.client_id == client.id)
            .order_by(MonthlyRecord.month)
            .all()
        )
        if not records:
            continue

        # `capture_before` and `check_due` commit, so a rollback afterwards
        # undoes nothing — the first "dry run" of this wrote ten rows and
        # then reported nothing to do. Nothing writing code runs at all
        # unless --apply was given.
        captured = 0
        if not args.apply:
            due = sum(
                1
                for record in records
                for _kind, action in _slotted(record.record or {})
                if action.get("check_on")
                and date.fromisoformat(action["check_on"]) <= today
            )
            readable = sum(
                1
                for record in records
                for _kind, action in _slotted(record.record or {})
                if measure(
                    db,
                    client,
                    metric_key_for(action),
                    url=action.get("target_url"),
                    term=action.get("term"),
                    as_of=record.data_through
                    or date.fromisoformat(f"{record.month}-01"),
                ).value
                is not None
            )
            print(
                f"{client.slug}: {due} action(s) due, "
                f"{readable} before-reading(s) available (nothing written)"
            )
            continue

        if args.capture_missing:
            for record in records:
                captured += capture_before(db, client, record, force=args.force)
        judged = check_due(db, client, today=today)
        print(f"{client.slug}: captured {captured}, judged {len(judged)}")
        for row in judged:
            print(
                f"    {row.uid}: {row.before_value} -> {row.after_value} = {row.result}"
                + ("" if row.shipped_on else "  (not recorded as shipped)")
            )


if __name__ == "__main__":
    main()
