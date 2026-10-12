"""Pull the full SERP feature list for each client's priority terms.

    python -m app.pull_serp_features                       # cost, no spend
    python -m app.pull_serp_features --client sma-marketing --apply
    python -m app.pull_serp_features --apply --limit 20

Every query is a billed call, so nothing is pulled without --apply and the
dry run says what it would cost. Monthly is the cadence the spec assumes: a
SERP older than 45 days is not read back, so a pull that is skipped shows up
as T-2 going quiet rather than as a stale finding.
"""

from __future__ import annotations

import argparse

from app.core.db import SessionLocal
from app.integrations import dataforseo
from app.models.client import Client
from app.services.serp_features import DEFAULT_LIMIT, coverage, pull, terms_to_pull


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="slug; omit for every client")
    parser.add_argument("--apply", action="store_true", help="spend credits and store")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    db = SessionLocal()
    clients = db.query(Client).order_by(Client.client_name)
    if args.client:
        clients = clients.filter(Client.slug == args.client)
    rows = clients.all()

    if not args.apply:
        total = 0
        for client in rows:
            terms = terms_to_pull(db, client, limit=args.limit)
            have, wanted = coverage(db, client)
            total += len(terms)
            if terms:
                print(
                    f"{client.slug}: would pull {len(terms)} "
                    f"(covered {have}/{wanted} today)"
                )
        print(f"\n{total} call(s) would be billed. Nothing pulled — pass --apply.")
        return

    if not dataforseo.configured():
        print(
            "DataForSEO is not configured. Set DATAFORSEO_LOGIN and "
            "DATAFORSEO_PASSWORD."
        )
        return

    for client in rows:
        try:
            pulled, failures = pull(db, client, limit=args.limit)
        except dataforseo.DataForSeoAuthError as exc:
            # One message, not one per client per keyword.
            print(f"\n{exc}")
            return
        print(f"{client.slug}: pulled {pulled}, {len(failures)} failed")
        for failure in failures[:5]:
            print(f"    {failure}")


if __name__ == "__main__":
    main()
