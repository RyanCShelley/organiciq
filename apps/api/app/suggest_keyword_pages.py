"""Propose a page for each tracked term, by subject.

    python -m app.suggest_keyword_pages                        # what it would do
    python -m app.suggest_keyword_pages --client sma-marketing --apply
    python -m app.suggest_keyword_pages --apply

Needs the embedding model, which is a 159 MB dependency and downloads ~90 MB
on first use. It is a monthly job rather than a request: around forty seconds
per client on CPU.
"""

from __future__ import annotations

import argparse

from app.core.db import SessionLocal
from app.models.client import Client
from app.services.keyword_matcher import crawled_pages, refresh_for, tracked_terms


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="slug; omit for every client")
    parser.add_argument("--apply", action="store_true", help="measure, match and store")
    args = parser.parse_args()

    db = SessionLocal()
    clients = db.query(Client).order_by(Client.client_name)
    if args.client:
        clients = clients.filter(Client.slug == args.client)

    for client in clients.all():
        if not args.apply:
            pages = crawled_pages(db, client)
            terms = tracked_terms(db, client.id)
            if pages and terms:
                print(f"{client.slug}: {len(pages)} pages, {len(terms)} terms to match")
            continue
        found = refresh_for(db, client)
        if not found["terms"]:
            continue
        margin = found["margin"]
        print(
            f"{client.slug}: {found['stored']} proposed of {found['terms']} terms "
            f"· margin {margin:.2f}"
            + ("" if found.get("measured") else " (default — too few pairs to measure)")
        )


if __name__ == "__main__":
    main()
