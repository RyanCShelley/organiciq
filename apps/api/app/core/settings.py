from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Railway/Postgres URLs are often postgresql://; we require the psycopg driver."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://organiciq:organiciq@localhost:5432/organiciq"
    auth_secret: str = "dev-auth-secret-change-me"
    sma_admin_emails: str = ""
    sma_google_hosted_domain: str = "smamarketing.net"
    integration_token_key: str = "dev-integration-token-key-32bytes!!"
    allowed_origins: str = "http://localhost:3000"
    worker_poll_interval_seconds: float = 2.0
    google_data_oauth_client_id: str = ""
    google_data_oauth_client_secret: str = ""
    google_data_oauth_redirect_uri: str = "http://127.0.0.1:8000/oauth/google/callback"
    web_app_url: str = "http://127.0.0.1:3000"
    decision_engine_enabled: bool = True
    se_ranking_api_key: str = ""

    def model_post_init(self, __context) -> None:
        object.__setattr__(self, "database_url", normalize_database_url(self.database_url))

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.sma_admin_emails.split(",") if e.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
