"""Why Search Console is empty, per client.

Nineteen clients were blocked on `search_console` with two different
causes wearing the same label: a 403, meaning the property is not shared
with our credentials, and a job that succeeded with zero rows, which almost
always means we asked about a property identifier Google does not recognise
for that site. A domain property (`sc-domain:example.com`) and a URL-prefix
property (`https://example.com/`) are different objects, and asking the
wrong one returns an empty success rather than an error.

Read-only. Lists what each client is configured to read and what the
credentials can actually see.

    python -m app.gsc_audit [--client slug]
"""

from __future__ import annotations

import argparse
import logging
from urllib.parse import urlsplit

from app.core.db import SessionLocal
from app.ingestion.google_credentials import (
    access_token_for_client,
    client_has_google_credentials,
)
from app.ingestion.gsc.client import list_sites
from app.models.client import Client, ClientStatus
from app.models.integration import Integration, IntegrationProvider

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.gsc_audit")


def _host(value: str) -> str:
    text = (value or "").strip().lower()
    if text.startswith("sc-domain:"):
        return text.removeprefix("sc-domain:").strip("/")
    if "://" in text:
        return (urlsplit(text).hostname or "").removeprefix("www.")
    return text.removeprefix("www.").strip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="one slug; default is every client")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Client).filter(Client.status != ClientStatus.ARCHIVED)
        if args.client:
            query = query.filter(Client.slug == args.client)
        clients = query.order_by(Client.client_name).all()

        for client in clients:
            integration = (
                db.query(Integration)
                .filter(
                    Integration.client_id == client.id,
                    Integration.provider == IntegrationProvider.GSC,
                )
                .one_or_none()
            )
            configured = integration.external_property_id if integration else None
            logger.info("\n%s (%s)", client.client_name, client.domain)
            logger.info("  configured: %s", configured or "— none —")

            if not client_has_google_credentials(db, client.id):
                logger.info("  no Google credentials for this client")
                continue
            try:
                sites = list_sites(access_token_for_client(db, client.id))
            except Exception as exc:  # noqa: BLE001 — a report, not a pipeline
                logger.info("  could not list properties: %s", str(exc)[:160])
                continue

            wanted = _host(client.domain)
            matches = [
                row
                for row in sites
                if _host(str(row.get("siteUrl") or "")) == wanted
            ]
            if not matches:
                logger.info(
                    "  credentials see %d properties, none for %s", len(sites), wanted
                )
                continue
            for row in matches:
                site_url = str(row.get("siteUrl") or "")
                flag = "  <-- configured" if site_url == configured else ""
                logger.info(
                    "  available:  %-44s %s%s",
                    site_url,
                    row.get("permissionLevel", "?"),
                    flag,
                )
            if configured and all(
                str(row.get("siteUrl")) != configured for row in matches
            ):
                logger.info("  MISMATCH: configured property is not one of the above")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
