import logging
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, auth, clients, decisions, integrations, jobs, oauth_google, seranking, v2_admin, v2_ads, v2_annotations, v2_ask, v2_bi, v2_connections, v2_content, v2_conversions, v2_ctr, v2_engine, v2_feeds, v2_focus, v2_inlinks, v2_llm, v2_optimizer, v2_review, v2_schema, v2_search_visibility, v2_site_health, v2_tasks, v2_watchlist
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


def _warm_text_model() -> None:
    """Load the text model now, so the first Inlink suggester visit does not wait for it."""
    try:
        from app.services import keyword_matcher

        keyword_matcher._model()
    except Exception:
        logger.warning("Could not load the text model at startup; it loads on first use.", exc_info=True)


if settings.is_production:
    threading.Thread(target=_warm_text_model, daemon=True, name="warm-text-model").start()


#: A request slower than this is named in the log, with the route it matched, so a slow screen can be found without guessing.
SLOW_REQUEST_SECONDS = 0.75


@app.middleware("http")
async def time_requests(request: Request, call_next):
    """Report how long the API itself took, in the response (`Server-Timing`) and, when slow, in the log.

    The web app's own wait on a screen is the API's time plus the network between them; this is the first of those, and the only one the API can see.
    """
    started = time.perf_counter()
    response = await call_next(request)
    took = time.perf_counter() - started
    response.headers["Server-Timing"] = f"api;dur={took * 1000:.0f}"
    if took >= SLOW_REQUEST_SECONDS and request.url.path != "/health":
        route = request.scope.get("route")
        logger.warning("Slow request: %s %s took %.2fs", request.method, getattr(route, "path", request.url.path), took)
    return response


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
app.include_router(decisions.router)
app.include_router(v2_watchlist.router)
app.include_router(v2_admin.router)
app.include_router(v2_ads.router)
app.include_router(v2_connections.router)
app.include_router(v2_conversions.router)
app.include_router(v2_engine.router)
app.include_router(v2_feeds.router)
app.include_router(v2_focus.router)
app.include_router(v2_llm.router)
app.include_router(v2_ask.router)
app.include_router(v2_bi.router)
app.include_router(v2_annotations.router)
app.include_router(v2_ctr.router)
app.include_router(v2_optimizer.router)
app.include_router(v2_content.router)
app.include_router(v2_inlinks.router)
app.include_router(v2_review.router)
app.include_router(v2_schema.router)
app.include_router(v2_search_visibility.router)
app.include_router(v2_site_health.router)
app.include_router(v2_tasks.router)
