import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, annotations, auth, clients, dashboard, decisions, integrations, jobs, oauth_google, seranking, watch_list
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

app = FastAPI(title="Organic IQ API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(integrations.router)
app.include_router(jobs.router)
app.include_router(admin.router)
app.include_router(oauth_google.router)
app.include_router(seranking.router)
app.include_router(watch_list.router)
app.include_router(dashboard.router)
app.include_router(decisions.router)
app.include_router(annotations.router)
