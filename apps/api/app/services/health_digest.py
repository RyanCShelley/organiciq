"""The daily health email.

The platform failed quietly more than once — Search Console data stopped for
fifteen days, a client's GA4 job failed every morning for a week — and each
time a person found out by opening a page. This reads the job table the way
that person would and says it once a day, unprompted.

Only problems that are still true are listed: a failure a later success has
superseded is history, not a problem.
"""

from __future__ import annotations

import logging
import re
import smtplib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import unquote

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.client import WORKED_STATUSES, Client
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob, SyncJobStatus
from app.models.scheduler import SchedulerCheckpoint

logger = logging.getLogger("organiciq.health_digest")

HEALTH_CHECKPOINT = "health_digest"

#: Search Console runs about three days behind and the sync asks for a rolling
#: window, so four days without a success is a stall, not lag.
STALE_AFTER_DAYS = 4
#: A job still working after this long was lost (a deploy, a crash).
STUCK_AFTER_HOURS = 2
#: Failures are looked for this far back, then dropped if something later
#: succeeded for the same client and source.
LOOKBACK_DAYS = 3

_ACTIVE = (
    SyncJobStatus.QUEUED,
    SyncJobStatus.FETCHING,
    SyncJobStatus.STAGING,
    SyncJobStatus.NORMALIZING,
    SyncJobStatus.VALIDATING,
)
_SYNC_SOURCES = {
    IntegrationProvider.GSC: "gsc_pages",
    IntegrationProvider.GA4: "ga4",
}


#: What a person reads for each job source, in place of the internal key.
_LABELS = {
    "gsc_pages": "Search Console",
    "gsc_queries": "Search Console",
    "ga4": "Google Analytics",
    "se_ranking_ai": "SE Ranking AI",
    "site_crawl": "Site crawl",
}
_SITE = re.compile(r"/sites/([^/]+)/")


def label(source: str) -> str:
    return _LABELS.get(source, source.replace("_", " ").capitalize())


@dataclass
class Problem:
    client: str
    source: str  # a person's name for the data, e.g. "Search Console"
    state: str  # failing, stalled or stuck
    what: str  # what is wrong, in a sentence
    fix: str = ""  # what to do about it, when that is known
    history: str = ""  # "Never synced successfully." / "Last success 2026-11-01."


@dataclass
class Digest:
    problems: list[Problem] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not self.problems

    @property
    def count(self) -> int:
        return len(self.problems)


def explain(source: str, message: str | None) -> tuple[str, str] | None:
    """A raw job error as (what is wrong, what to do). None when the job only says a source was never set up: that is a setup task, not a fault."""
    text = (message or "").strip()
    lower = text.lower()
    if "no se ranking ai engines configured" in lower or "not configured" in lower:
        return None
    name = label(source)
    site = ""
    m = _SITE.search(text)
    if m:
        site = unquote(m.group(1)).replace("https://", "").replace("http://", "").strip("/")
    if "403" in text and name == "Search Console":
        return (
            f"Search Console has no access to {site or 'the property'}.",
            "Add the connected Google account as a user on that property in Search Console, or correct the property address in Integrations.",
        )
    if "404" in text and name == "Search Console":
        return (f"Search Console does not know the property {site or 'on file'}.", "Correct the property address in Integrations, or add the site in Search Console.")
    if "401" in text or "invalid_grant" in lower or "token has been expired" in lower:
        return (f"The {name} sign-in has expired.", "Reconnect the Google account in Integrations.")
    if "403" in text:
        return (f"{name} refused access.", "Check the connection and permissions in Integrations.")
    if "429" in text or "quota" in lower or "rate limit" in lower:
        return (f"{name} is rate limiting the sync.", "Nothing to do; it retries on the next run. If it repeats for days, look at the quota.")
    if re.search(r"\b5\d\d\b", text):
        return (f"{name} had a server error.", "Nothing to do unless it repeats for days.")
    first = text.splitlines()[0][:200] if text else "no message"
    return (f"{name} failed: {first}", "")


def build_digest(db: Session, *, now: datetime | None = None) -> Digest:
    now = now or datetime.now(timezone.utc)
    digest = Digest()
    clients = {c.id: c for c in db.query(Client).filter(Client.status.in_(WORKED_STATUSES))}
    if not clients:
        return digest

    # One problem per client and kind of data, whichever job or check found it.
    found: dict[tuple, Problem] = {}

    # Latest outcome per client+source, so a failure followed by a success
    # (someone re-ran it, or the next day's job passed) is not reported.
    recent = (
        db.query(SyncJob)
        .filter(
            SyncJob.client_id.in_(list(clients)),
            SyncJob.created_at > now - timedelta(days=LOOKBACK_DAYS),
            SyncJob.status.in_([SyncJobStatus.FAILED, SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL]),
        )
        .order_by(SyncJob.created_at.desc())
        .all()
    )
    seen: set[tuple] = set()
    for job in recent:
        key = (job.client_id, job.source)
        if key in seen:
            continue
        seen.add(key)
        if job.status != SyncJobStatus.FAILED:
            continue
        said = explain(job.source, job.error_message)
        if said is None:
            continue
        name = clients[job.client_id].client_name
        found.setdefault((job.client_id, label(job.source)), Problem(name, label(job.source), "failing", said[0], said[1]))

    # Stale: a connected source with no successful sync lately. Connected
    # means a property is mapped; an unmapped client is a setup task, not a
    # fault, and would otherwise drown the real ones.
    mapped = (
        db.query(Integration)
        .filter(
            Integration.client_id.in_(list(clients)),
            Integration.provider.in_(list(_SYNC_SOURCES)),
            Integration.external_property_id.isnot(None),
        )
        .all()
    )
    last_ok = {
        (client_id, source): finished
        for client_id, source, finished in db.query(SyncJob.client_id, SyncJob.source, func.max(SyncJob.completed_at))
        .filter(
            SyncJob.client_id.in_(list(clients)),
            SyncJob.source.in_(list(_SYNC_SOURCES.values())),
            SyncJob.status.in_([SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL]),
        )
        .group_by(SyncJob.client_id, SyncJob.source)
    }
    for integration in mapped:
        source = _SYNC_SOURCES[integration.provider]
        finished = last_ok.get((integration.client_id, source))
        if finished is not None and finished >= now - timedelta(days=STALE_AFTER_DAYS):
            continue
        history = f"Last success {finished:%Y-%m-%d}." if finished else "Never synced successfully."
        key = (integration.client_id, label(source))
        if key in found:
            found[key].history = history  # the same fault, told once
        else:
            found[key] = Problem(
                clients[integration.client_id].client_name, label(source), "stalled",
                f"{label(source)} has not synced in {STALE_AFTER_DAYS}+ days.", "Run a sync from the client's page, and check the connection if it fails.", history,
            )

    for job in db.query(SyncJob).filter(
        SyncJob.status.in_(_ACTIVE),
        SyncJob.created_at < now - timedelta(hours=STUCK_AFTER_HOURS),
        SyncJob.client_id.in_(list(clients)),
    ):
        found.setdefault(
            (job.client_id, label(job.source), "stuck"),
            Problem(clients[job.client_id].client_name, label(job.source), "stuck",
                    f"{label(job.source)} has been working since {job.created_at:%Y-%m-%d %H:%M} UTC.", "A deploy or crash probably lost it. Run it again."),
        )

    digest.problems = sorted(found.values(), key=lambda p: (p.client.lower(), p.source.lower()))
    return digest


def render(digest: Digest, *, today: date) -> tuple[str, str]:
    if digest.healthy:
        return (
            f"OrganicIQ health {today:%b %d}: all clear",
            "Every worked client's syncs are current and nothing is failing or stuck.",
        )
    n = digest.count
    lines = [f"{n} {'thing needs' if n == 1 else 'things need'} a look.", ""]
    by_client: dict[str, list[Problem]] = {}
    for problem in digest.problems:
        by_client.setdefault(problem.client, []).append(problem)
    for client, problems in by_client.items():
        lines.append(client)
        for p in problems:
            lines.append(f"  • {p.what}" + (f" {p.history}" if p.history else ""))
            if p.fix:
                lines.append(f"    To fix: {p.fix}")
        lines.append("")
    return (f"OrganicIQ health {today:%b %d}: {n} to look at", "\n".join(lines).rstrip())


def send_email(subject: str, body: str, to: list[str] | None = None) -> bool:
    """Send through the configured SMTP account. False when not configured.

    With no `to` it goes to the health digest recipients.
    """
    settings = get_settings()
    recipients = to if to is not None else [a.strip() for a in settings.health_digest_to.split(",") if a.strip()]
    if not (recipients and settings.smtp_host):
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = ", ".join(recipients)
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
    return True


def maybe_send_health_digest(db: Session) -> bool:
    """Once a day, after the morning sync has had time to finish.

    Quiet days are not emailed, except Mondays: a digest that only ever speaks
    when something is wrong cannot be told apart from one that has broken.
    """
    settings = get_settings()
    if not settings.health_digest_enabled:
        return False
    now = datetime.now(timezone.utc)
    if now.hour < settings.health_digest_hour_utc:
        return False

    checkpoint = (
        db.query(SchedulerCheckpoint)
        .filter(SchedulerCheckpoint.name == HEALTH_CHECKPOINT)
        .with_for_update()
        .one_or_none()
    )
    if checkpoint is None:
        checkpoint = SchedulerCheckpoint(name=HEALTH_CHECKPOINT, last_run_date=None)
        db.add(checkpoint)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return False
    today = now.date()
    if checkpoint.last_run_date == today:
        db.rollback()
        return False

    digest = build_digest(db, now=now)
    subject, body = render(digest, today=today)
    # Recorded before sending: a mail server that is down should not make the
    # worker retry every two seconds all afternoon.
    checkpoint.last_run_date = today
    checkpoint.updated_at = now
    db.commit()

    if digest.healthy and today.weekday() != 0:
        logger.info("Health digest: all clear, not sent")
        return True
    try:
        sent = send_email(subject, body)
    except Exception:  # noqa: BLE001 — a mail failure must not stop the worker
        logger.exception("Health digest could not be sent")
        sent = False
    logger.info("Health digest: %s — %s", subject, "sent" if sent else "not sent (email not configured)")
    if not sent:
        logger.info("Health digest body:\n%s", body)
    return True
