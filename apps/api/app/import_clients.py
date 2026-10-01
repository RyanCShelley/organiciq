"""Load many clients at once from a CSV, resolving their integration IDs.

Adding a client by hand means creating the record, then finding its GA4
property, its Search Console property and its SE Ranking project, and typing
three identifiers that no one can eyeball for correctness. Across a whole book
of business that is both slow and a good way to bind a client to the wrong
property without noticing.

This reads a CSV, matches each row's domain against what the three APIs
actually report, and writes clients, integrations and conversion definitions.

Only the Google *property mapping* is written here — never credentials. The
OAuth grant is shared across the workspace (see
`google_credentials.load_google_refresh_token`), so one existing Google
connection covers every client this creates.

CSV columns
-----------
Required: client_name, domain, tier

Everything else is optional and may simply be left out of the file — the
columns exist so a whole book of business can be loaded in one pass, not
because a row needs them. Connecting the integrations by hand afterwards is a
perfectly good way to work, and the lookups below only save that labour.

Optional: lead_events (semicolon-separated GA4 event names), slug, start_date,
          timezone, primary_market, monthly_lead_goal, crawl_page_limit,
          sitemap_url, ai_search_prompt_limit, status
Overrides: ga4_property_id, gsc_site_url, seranking_project_id
           — supplied values always win over a lookup.

Usage, on the API service:

    # 1. See what it would create and what it matched
    python -m app.import_clients --csv clients.csv

    # 2. Do it
    python -m app.import_clients --csv clients.csv --apply

Dry run by default. Re-running is safe: a client already present (by slug) is
updated rather than duplicated, and integrations are upserted.

On matching
-----------
Search Console and SE Ranking both report a URL, so those are matched on the
domain itself and are trustworthy. GA4's accountSummaries returns only a
display name — there is no domain in the payload — so GA4 can only be matched
on *name*, which is a guess. Name matches are marked `~` in the report and are
worth reading before applying; supply `ga4_property_id` to remove the doubt.

An ambiguous match (more than one candidate) is never bound. It is reported and
left empty, because the cost of a wrong property is silent bad data for months.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.settings import get_settings
from app.ingestion.ga4.client import list_ga4_properties
from app.ingestion.google_credentials import workspace_google_refresh_token
from app.ingestion.gsc.client import list_sites as list_gsc_sites
from app.ingestion.seranking.client import list_sites as list_seranking_sites
from app.models.client import Client, ClientStatus, Tier
from app.models.config import ConversionDefinition
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.import_clients")

REQUIRED_COLUMNS = ("client_name", "domain", "tier")


def normalize_host(value: str) -> str:
    """Reduce anything domain-shaped to a bare comparable host.

    Handles the forms the three APIs use between them: `sc-domain:example.com`,
    `https://www.example.com/`, and a plain `example.com`.
    """
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = text.removeprefix("sc-domain:")
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)
    text = text.split("/", 1)[0]
    text = text.split("?", 1)[0]
    text = text.removeprefix("www.")
    return text.strip().strip(".")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:120] or "client"


@dataclass
class Match:
    """One resolved identifier, and how much the resolution can be trusted."""

    value: str | None = None
    #: "csv" (supplied), "domain" (matched on URL), "name" (guessed), "none", "ambiguous"
    how: str = "none"
    candidates: list[str] = field(default_factory=list)

    @property
    def mark(self) -> str:
        return {"csv": "=", "domain": "+", "name": "~", "ambiguous": "?", "none": "-"}[self.how]

    def describe(self) -> str:
        if self.how == "ambiguous":
            return f"ambiguous ({len(self.candidates)} candidates)"
        return self.value or "not found"


class Resolver:
    """Looks each provider's catalogue up once, then answers per domain."""

    def __init__(self, db: Session, *, skip_lookups: bool = False) -> None:
        self.ga4: list[dict[str, str]] = []
        self.gsc: list[dict[str, Any]] = []
        self.seranking: list[dict[str, Any]] = []
        if skip_lookups:
            return

        refresh_token = workspace_google_refresh_token(db)
        if refresh_token:
            from app.ingestion.google_auth import credentials_from_tokens, ensure_access_token

            settings = get_settings()
            creds = credentials_from_tokens(
                refresh_token=refresh_token,
                client_id=settings.google_data_oauth_client_id,
                client_secret=settings.google_data_oauth_client_secret,
                token=None,
            )
            token = ensure_access_token(creds)
            self.ga4 = list_ga4_properties(token)
            self.gsc = list_gsc_sites(token)
            logger.info("Catalogue: %d GA4 properties, %d GSC sites", len(self.ga4), len(self.gsc))
        else:
            logger.warning(
                "No Google connection in the workspace — GA4 and GSC cannot be resolved. "
                "Connect one client through the UI first, or supply the IDs in the CSV."
            )

        api_key = get_settings().se_ranking_api_key
        if api_key:
            self.seranking = list_seranking_sites(api_key)
            logger.info("Catalogue: %d SE Ranking projects", len(self.seranking))
        else:
            logger.warning("SE_RANKING_API_KEY is not set — SE Ranking cannot be resolved.")

    @staticmethod
    def _pick(candidates: list[str], how: str) -> Match:
        unique = list(dict.fromkeys(candidates))
        if not unique:
            return Match(how="none")
        if len(unique) > 1:
            return Match(how="ambiguous", candidates=unique)
        return Match(value=unique[0], how=how)

    def gsc_site(self, host: str) -> Match:
        hits = [
            str(entry.get("siteUrl"))
            for entry in self.gsc
            if normalize_host(str(entry.get("siteUrl") or "")) == host
        ]
        return self._pick(hits, "domain")

    def seranking_project(self, host: str) -> Match:
        hits = []
        for site in self.seranking:
            for key in ("url", "domain", "site", "name", "title"):
                if normalize_host(str(site.get(key) or "")) == host:
                    identifier = site.get("id") or site.get("site_id") or site.get("project_id")
                    if identifier is not None:
                        hits.append(str(identifier))
                    break
        return self._pick(hits, "domain")

    def ga4_property(self, host: str, client_name: str) -> Match:
        """Name-based, because accountSummaries carries no domain. A guess, marked as one."""
        root = host.split(".")[0]
        name_key = re.sub(r"[^a-z0-9]", "", client_name.lower())
        hits = []
        for prop in self.ga4:
            display = re.sub(r"[^a-z0-9]", "", str(prop.get("display_name") or "").lower())
            if not display:
                continue
            if host.replace(".", "") in display or (len(root) > 3 and root in display):
                hits.append(prop["property_id"])
            elif name_key and len(name_key) > 3 and name_key in display:
                hits.append(prop["property_id"])
        return self._pick(hits, "name")


def _as_int(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _as_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def _upsert_integration(
    db: Session, client_id, provider: IntegrationProvider, external_id: str | None
) -> None:
    """Write the property mapping. Credentials are never touched here."""
    if not external_id:
        return
    row = (
        db.query(Integration)
        .filter(Integration.client_id == client_id, Integration.provider == provider)
        .one_or_none()
    )
    if row is None:
        row = Integration(client_id=client_id, provider=provider)
        db.add(row)
    row.external_property_id = external_id
    # The grant is workspace-wide, so a mapped property is a usable connection.
    if row.connection_status == ConnectionStatus.NOT_CONNECTED:
        row.connection_status = ConnectionStatus.CONNECTED


def _upsert_lead_events(db: Session, client_id, names: list[str]) -> int:
    added = 0
    for index, name in enumerate(names):
        exists = (
            db.query(ConversionDefinition)
            .filter(
                ConversionDefinition.client_id == client_id,
                ConversionDefinition.event_name == name,
            )
            .one_or_none()
        )
        if exists is not None:
            continue
        db.add(
            ConversionDefinition(
                client_id=client_id,
                event_name=name,
                conversion_name=name.replace("_", " ").title(),
                conversion_type="lead",
                is_primary=index == 0,
                active=True,
            )
        )
        added += 1
    return added


def import_clients(
    db: Session, rows: list[dict[str, str]], *, apply: bool = False, skip_lookups: bool = False
) -> dict[str, int]:
    tiers = {t.tier_name.strip().lower(): t for t in db.query(Tier).all()}
    if not tiers:
        raise RuntimeError("No tiers in the database — seed them before importing clients.")

    resolver = Resolver(db, skip_lookups=skip_lookups)
    counts = {"created": 0, "updated": 0, "skipped": 0, "unresolved": 0, "blank": 0}

    logger.info("")
    logger.info(
        "%-24s %-24s   %-16s   %-26s   %-12s",
        "Client",
        "Domain",
        "GA4 property",
        "Search Console",
        "SE Ranking",
    )
    logger.info("%s", "-" * 116)

    for line, row in enumerate(rows, start=2):
        name = (row.get("client_name") or "").strip()
        domain_raw = (row.get("domain") or "").strip()
        tier_name = (row.get("tier") or "").strip().lower()

        # Spreadsheets export hundreds of empty trailing rows. Warning about
        # each one buries the report the operator actually needs to read.
        if not any((value or "").strip() for value in row.values()):
            counts["blank"] += 1
            continue
        if not name or not domain_raw or not tier_name:
            logger.warning("line %d: missing client_name, domain or tier — skipped", line)
            counts["skipped"] += 1
            continue
        tier = tiers.get(tier_name)
        if tier is None:
            logger.warning(
                "line %d: unknown tier %r (have: %s) — skipped",
                line,
                row.get("tier"),
                ", ".join(sorted(t.tier_name for t in tiers.values())),
            )
            counts["skipped"] += 1
            continue

        host = normalize_host(domain_raw)
        slug = slugify(row.get("slug") or name)

        ga4 = (
            Match(value=row["ga4_property_id"].strip(), how="csv")
            if (row.get("ga4_property_id") or "").strip()
            else resolver.ga4_property(host, name)
        )
        gsc = (
            Match(value=row["gsc_site_url"].strip(), how="csv")
            if (row.get("gsc_site_url") or "").strip()
            else resolver.gsc_site(host)
        )
        ser = (
            Match(value=row["seranking_project_id"].strip(), how="csv")
            if (row.get("seranking_project_id") or "").strip()
            else resolver.seranking_project(host)
        )

        logger.info(
            "%-24s %-24s %s %-16s %s %-26s %s %-12s",
            name[:24],
            host[:24],
            ga4.mark,
            ga4.describe()[:16],
            gsc.mark,
            gsc.describe()[:26],
            ser.mark,
            ser.describe()[:12],
        )
        for label, match in (("GA4", ga4), ("GSC", gsc), ("SE Ranking", ser)):
            if match.how == "ambiguous":
                logger.warning(
                    "    %s ambiguous for %s, left empty: %s",
                    label,
                    host,
                    ", ".join(match.candidates[:5]),
                )
        if any(m.how in {"none", "ambiguous"} for m in (ga4, gsc, ser)):
            counts["unresolved"] += 1

        existing = db.query(Client).filter(Client.slug == slug).one_or_none()
        counts["created" if existing is None else "updated"] += 1

        if not apply:
            continue

        client = existing or Client(slug=slug)
        client.client_name = name
        client.domain = host
        client.tier_id = tier.id
        client.timezone = (row.get("timezone") or "").strip() or "America/New_York"
        client.start_date = _as_date(row.get("start_date")) or client.start_date
        client.monthly_lead_goal = _as_int(row.get("monthly_lead_goal")) or client.monthly_lead_goal
        client.crawl_page_limit = _as_int(row.get("crawl_page_limit")) or client.crawl_page_limit
        client.ai_search_prompt_limit = (
            _as_int(row.get("ai_search_prompt_limit")) or client.ai_search_prompt_limit
        )
        client.sitemap_url = (row.get("sitemap_url") or "").strip() or client.sitemap_url
        client.primary_market = (row.get("primary_market") or "").strip() or client.primary_market
        status = (row.get("status") or "").strip().lower()
        if existing is None:
            client.status = ClientStatus(status) if status else ClientStatus.ONBOARDING
            db.add(client)
        elif status:
            client.status = ClientStatus(status)
        db.flush()

        _upsert_integration(db, client.id, IntegrationProvider.GA4, ga4.value)
        _upsert_integration(db, client.id, IntegrationProvider.GSC, gsc.value)
        _upsert_integration(db, client.id, IntegrationProvider.SE_RANKING, ser.value)

        events = [e.strip() for e in (row.get("lead_events") or "").split(";") if e.strip()]
        _upsert_lead_events(db, client.id, events)

        # Sessions here run with autoflush off, so without this a later row
        # looking up the same slug would not see this one and would duplicate it.
        db.flush()

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="path to the client CSV")
    parser.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    parser.add_argument(
        "--skip-lookups",
        action="store_true",
        help="do not call the provider APIs; use only IDs given in the CSV",
    )
    args = parser.parse_args()

    with open(args.csv, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            logger.error("CSV is missing required columns: %s", ", ".join(missing))
            return 1
        rows = list(reader)

    if not rows:
        logger.error("No rows in %s", args.csv)
        return 1

    logger.info("%s: %d rows from %s", "APPLY" if args.apply else "DRY RUN", len(rows), args.csv)

    db = SessionLocal()
    try:
        counts = import_clients(db, rows, apply=args.apply, skip_lookups=args.skip_lookups)
        if args.apply:
            db.commit()
            logger.info(
                "\nCreated %d, updated %d, skipped %d.",
                counts["created"],
                counts["updated"],
                counts["skipped"],
            )
            logger.info("Run a sync for the new clients, then take baselines from GA4.")
        else:
            db.rollback()
            logger.info(
                "\nWould create %d and update %d; %d skipped, %d with an unresolved ID.",
                counts["created"],
                counts["updated"],
                counts["skipped"],
                counts["unresolved"],
            )
            if counts["blank"]:
                logger.info("Ignored %d empty rows.", counts["blank"])
            logger.info("Key: = from CSV, + matched on domain, ~ matched on name, ? ambiguous, - none")
            logger.info("Re-run with --apply to write.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
