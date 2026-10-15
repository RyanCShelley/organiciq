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
import smtplib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage

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


@dataclass
class Problem:
    client: str
    what: str
    detail: str = ""


@dataclass
class Digest:
    failures: list[Problem] = field(default_factory=list)
    stale: list[Problem] = field(default_factory=list)
    stuck: list[Problem] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not (self.failures or self.stale or self.stuck)

    @property
    def count(self) -> int:
        return len(self.failures) + len(self.stale) + len(self.stuck)


def build_digest(db: Session, *, now: datetime | None = None) -> Digest:
    now = now or datetime.now(timezone.utc)
    digest = Digest()
    clients = {c.id: c for c in db.query(Client).filter(Client.status.in_(WORKED_STATUSES))}
    if not clients:
        return digest

    # Latest outcome per client+source, so a failure followed by a success
    # (someone re-ran it, or the next day's job passed) is not reported.
    recent = (
        db.query(SyncJob)
        .filter(
            SyncJob.client_id.in_(list(clients)),
            SyncJob.created_at > now - timedelta(days=LOOKBACK_DAYS),
            SyncJob.status.in_(
                [SyncJobStatus.FAILED, SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL]
            ),
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
        if job.status == SyncJobStatus.FAILED:
            digest.failures.append(
                Problem(
                    clients[job.client_id].client_name,
                    f"{job.source} failed",
                    (job.error_message or "no message")[:240],
                )
            )

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
        for client_id, source, finished in db.query(
            SyncJob.client_id, SyncJob.source, func.max(SyncJob.completed_at)
        )
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
        if finished is None or finished < now - timedelta(days=STALE_AFTER_DAYS):
            digest.stale.append(
                Problem(
                    clients[integration.client_id].client_name,
                    f"{source} has no successful sync in {STALE_AFTER_DAYS}+ days",
                    f"last success {finished:%Y-%m-%d}" if finished else "never succeeded",
                )
            )

    for job in db.query(SyncJob).filter(
        SyncJob.status.in_(_ACTIVE),
        SyncJob.created_at < now - timedelta(hours=STUCK_AFTER_HOURS),
        SyncJob.client_id.in_(list(clients)),
    ):
        digest.stuck.append(
            Problem(
                clients[job.client_id].client_name,
                f"{job.source} stuck in {job.status.value}",
                f"since {job.created_at:%Y-%m-%d %H:%M} UTC",
            )
        )

    for group in (digest.failures, digest.stale, digest.stuck):
        group.sort(key=lambda p: (p.client.lower(), p.what))
    return digest


def render(digest: Digest, *, today: date) -> tuple[str, str]:
    if digest.healthy:
        return (
            f"OrganicIQ health {today:%b %d}: all clear",
            "Every worked client's syncs are current and nothing is failing or stuck.",
        )
    lines = [f"{digest.count} thing(s) need a look.", ""]
    for title, group in (
        ("Failed and not yet recovered", digest.failures),
        ("Gone stale", digest.stale),
        ("Stuck", digest.stuck),
    ):
        if not group:
            continue
        lines.append(f"{title} ({len(group)})")
        for problem in group:
            tail = f" — {problem.detail}" if problem.detail else ""
            lines.append(f"  • {problem.client}: {problem.what}{tail}")
        lines.append("")
    return (f"OrganicIQ health {today:%b %d}: {digest.count} to look at", "\n".join(lines).rstrip())


def send_email(subject: str, body: str) -> bool:
    """Send through the configured SMTP account. False when not configured."""
    settings = get_settings()
    recipients = [a.strip() for a in settings.health_digest_to.split(",") if a.strip()]
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
