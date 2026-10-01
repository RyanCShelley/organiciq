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

A domain may carry a folder — `robinsonheli.com/unmanned` — for a client whose
site is a section of a larger domain. The folder is stored as the client's path
scope, never in `domain`, which is read as a host everywhere else.

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
from app.core.urls import normalize_path_prefix
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


def split_path_prefix(value: str) -> str | None:
    """The folder part of a domain cell, for a site that lives under a parent brand.

    `robinsonheli.com/unmanned` means a client scoped to that folder. Dropping
    the path would quietly widen it to the whole domain, so it is kept — in its
    own field, never in `domain`.
    """
    text = (value or "").strip()
    if "://" in text:
        text = text.split("://", 1)[1]
    _, _, path = text.partition("/")
    return normalize_path_prefix(path)


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
    #: What the provider calls it. A property id cannot be checked by eye; the
    #: name it was matched against can.
    label: str | None = None

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
    def _pick(candidates: list[str], how: str, labels: dict[str, str] | None = None) -> Match:
        unique = list(dict.fromkeys(candidates))
        if not unique:
            return Match(how="none")
        if len(unique) > 1:
            return Match(how="ambiguous", candidates=unique)
        return Match(value=unique[0], how=how, label=(labels or {}).get(unique[0]))

    #: Search Console lets one site be verified several ways at once. A domain
    #: property covers every scheme and subdomain, so it is strictly the best
    #: of them; https beats http. Preferring in that order is a rule, not a
    #: guess, so these do not need to be reported as ambiguous.
    _GSC_PREFERENCE = ("sc-domain:", "https://", "http://")

    def gsc_site(self, host: str) -> Match:
        hits = [
            str(entry.get("siteUrl"))
            for entry in self.gsc
            if normalize_host(str(entry.get("siteUrl") or "")) == host
        ]
        for prefix in self._GSC_PREFERENCE:
            preferred = [hit for hit in hits if hit.startswith(prefix)]
            if len(preferred) == 1:
                return Match(value=preferred[0], how="domain")
            if preferred:
                # Several of the same kind is a real ambiguity.
                return self._pick(preferred, "domain")
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
        labels: dict[str, str] = {}
        for prop in self.ga4:
            display = re.sub(r"[^a-z0-9]", "", str(prop.get("display_name") or "").lower())
            if not display:
                continue
            if host.replace(".", "") in display or (len(root) > 3 and root in display):
                hits.append(prop["property_id"])
            elif name_key and len(name_key) > 3 and name_key in display:
                hits.append(prop["property_id"])
            else:
                continue
            labels[prop["property_id"]] = str(prop.get("display_name") or "")
        return self._pick(hits, "name", labels)


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


@dataclass
class Resolved:
    """One CSV row after matching, before anything is written."""

    row: dict[str, str]
    name: str
    host: str
    path_prefix: str | None
    slug: str
    tier_id: Any
    ga4: Match
    gsc: Match
    ser: Match


def import_clients(
    db: Session, rows: list[dict[str, str]], *, apply: bool = False, skip_lookups: bool = False
) -> dict[str, int]:
    """Resolve every row, report, then write.

    Resolution and writing are separate passes because a collision is only
    visible once every row has been matched — and a client written in the first
    pass cannot be un-bound when the tenth row turns out to claim the same
    property.
    """
    tiers = {t.tier_name.strip().lower(): t for t in db.query(Tier).all()}
    if not tiers:
        raise RuntimeError("No tiers in the database — seed them before importing clients.")

    resolver = Resolver(db, skip_lookups=skip_lookups)
    counts = {"created": 0, "updated": 0, "skipped": 0, "unresolved": 0, "blank": 0}

    # ── Pass one: match ──
    resolved: list[Resolved] = []
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
        supplied = lambda key: (row.get(key) or "").strip()  # noqa: E731
        resolved.append(
            Resolved(
                row=row,
                name=name,
                host=host,
                path_prefix=split_path_prefix(domain_raw)
                or normalize_path_prefix(row.get("path_prefix")),
                slug=slugify(row.get("slug") or name),
                tier_id=tier.id,
                ga4=(
                    Match(value=supplied("ga4_property_id"), how="csv")
                    if supplied("ga4_property_id")
                    else resolver.ga4_property(host, name)
                ),
                gsc=(
                    Match(value=supplied("gsc_site_url"), how="csv")
                    if supplied("gsc_site_url")
                    else resolver.gsc_site(host)
                ),
                ser=(
                    Match(value=supplied("seranking_project_id"), how="csv")
                    if supplied("seranking_project_id")
                    else resolver.seranking_project(host)
                ),
            )
        )

    # ── Two clients pointed at one property is the worst outcome here: both
    # read plausible and both are wrong, and a name-based GA4 match is exactly
    # how it would happen. Found across all rows, so neither is written. ──
    claimed: dict[tuple[str, str], str] = {}
    collisions: dict[tuple[str, str], list[str]] = {}
    for entry in resolved:
        for label, match in (("GA4", entry.ga4), ("GSC", entry.gsc), ("SE Ranking", entry.ser)):
            if not match.value:
                continue
            key = (label, match.value)
            owner = claimed.setdefault(key, entry.name)
            if owner != entry.name:
                collisions.setdefault(key, [owner]).append(entry.name)

    # ── Pass two: report, and write when asked ──
    logger.info("")
    logger.info(
        "%-26s %-22s %-36s %-12s", "Client", "GA4 property", "Search Console", "SE Ranking"
    )
    logger.info("%s", "-" * 100)

    for entry in resolved:
        # Identifiers print in full: a truncated property id cannot be checked,
        # and checking them is the entire point of the dry run.
        logger.info(
            "%-26s %s %-20s %s %-34s %s %-12s",
            entry.name[:26],
            entry.ga4.mark,
            entry.ga4.describe(),
            entry.gsc.mark,
            entry.gsc.describe(),
            entry.ser.mark,
            entry.ser.describe(),
        )
        # A name match is a guess. Printing the property's own name is what
        # makes it checkable — the id alone tells the reader nothing.
        if entry.ga4.how == "name" and entry.ga4.label:
            logger.info('    GA4 matched on name: "%s"', entry.ga4.label)
        for label, match in (("GA4", entry.ga4), ("GSC", entry.gsc), ("SE Ranking", entry.ser)):
            if match.how == "ambiguous":
                logger.warning(
                    "    %s ambiguous for %s, left empty: %s",
                    label,
                    entry.host,
                    ", ".join(match.candidates[:5]),
                )
        if any(m.how in {"none", "ambiguous"} for m in (entry.ga4, entry.gsc, entry.ser)):
            counts["unresolved"] += 1

        existing = db.query(Client).filter(Client.slug == entry.slug).one_or_none()
        counts["created" if existing is None else "updated"] += 1

        if not apply:
            continue

        row = entry.row
        client = existing or Client(slug=entry.slug)
        client.client_name = entry.name
        client.domain = entry.host
        client.path_prefix = entry.path_prefix
        client.tier_id = entry.tier_id
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

        def unique(label: str, match: Match) -> str | None:
            return None if (label, match.value) in collisions else match.value

        _upsert_integration(db, client.id, IntegrationProvider.GA4, unique("GA4", entry.ga4))
        _upsert_integration(db, client.id, IntegrationProvider.GSC, unique("GSC", entry.gsc))
        _upsert_integration(
            db, client.id, IntegrationProvider.SE_RANKING, unique("SE Ranking", entry.ser)
        )

        events = [e.strip() for e in (row.get("lead_events") or "").split(";") if e.strip()]
        _upsert_lead_events(db, client.id, events)

        # Sessions here run with autoflush off, so without this a later row
        # looking up the same slug would not see this one and would duplicate it.
        db.flush()

    for (label, value), names in sorted(collisions.items()):
        logger.error(
            "%s %s is claimed by %s — left empty on all of them",
            label,
            value,
            ", ".join(names),
        )
    counts["collisions"] = len(collisions)

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
