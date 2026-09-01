from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, auth, clients, dashboard, decisions, integrations, jobs, oauth_google, seranking, watch_list
from app.core.settings import get_settings

settings = get_settings()

app = FastAPI(title="Organic IQ API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
