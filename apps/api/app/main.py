import logging

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, annotations, auth, clients, dashboard, decisions, integrations, jobs, oauth_google, seranking, site_crawl, watch_list
from app.core.settings import get_settings

logger = logging.getLogger("organiciq.api")

settings = get_settings()

# State the security posture on every boot. The hardening shipped inert once
# because APP_ENV was never set and nothing said so; silence is not evidence
# the guard passed.
if settings.is_production:
    logger.warning("Security posture: PRODUCTION — secret validation active.")
else:
    logger.warning(
        "Security posture: NON-PRODUCTION (app_env=%r) — secret validation is OFF "
        "and /auth/upsert is unauthenticated. Set APP_ENV=production for a live deploy.",
        settings.app_env,
    )

# The interactive docs list every route, parameter and schema to anyone who can
# reach the API, so they are served outside production only.
app = FastAPI(
    title="Organic IQ API",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _migration_state() -> tuple[str, str | None]:
    """Whether this boot's migrations applied, and why not.

    start-api.sh no longer exits when a migration fails, so the failure has to
    be visible somewhere other than a boot log. It is reported here rather than
    by failing the healthcheck, because a failing healthcheck restarts the
    service — which is the outage this exists to avoid.
    """
    state_file = os.environ.get("MIGRATION_STATE_FILE")
    if not state_file:
        return "unknown", None
    try:
        state = Path(state_file).read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown", None
    if state != "failed":
        return state or "unknown", None
    log = os.environ.get("MIGRATION_LOG")
    detail = None
    if log:
        try:
            detail = Path(log).read_text(encoding="utf-8").strip().splitlines()[-1]
        except (OSError, IndexError):
            detail = None
    return "failed", detail


@app.get("/health")
def health() -> dict[str, str]:
    state, detail = _migration_state()
    if state == "failed":
        logger.error("Serving with failed migrations: %s", detail or "see the boot log")
        # The last line of the Alembic error names tables and SQL, and this
        # route is unauthenticated. It is in the log above.
        return {"status": "degraded", "migrations": "failed"}
    return {"status": "ok", "migrations": state}


app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(integrations.router)
app.include_router(jobs.router)
app.include_router(admin.router)
app.include_router(oauth_google.router)
app.include_router(seranking.router)
app.include_router(watch_list.router)
app.include_router(site_crawl.router)
app.include_router(dashboard.router)
app.include_router(decisions.router)
app.include_router(annotations.router)
