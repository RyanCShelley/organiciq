from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Values shipped in the repo and docker-compose. Safe locally, fatal in production.
INSECURE_AUTH_SECRET = "dev-auth-secret-change-me"
INSECURE_TOKEN_KEY = "dev-integration-token-key-32bytes!!"
MIN_SECRET_LENGTH = 32


def normalize_database_url(url: str) -> str:
    """Railway/Postgres URLs are often postgresql://; we require the psycopg driver."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://organiciq:organiciq@localhost:5432/organiciq"
    auth_secret: str = INSECURE_AUTH_SECRET
    sma_admin_emails: str = ""
    sma_google_hosted_domain: str = "smamarketing.net"
    integration_token_key: str = INSECURE_TOKEN_KEY
    # Shared secret the web app presents to POST /auth/upsert. Required in production.
    internal_api_secret: str = ""
    allowed_origins: str = "http://localhost:3000"
    worker_poll_interval_seconds: float = 2.0
    google_data_oauth_client_id: str = ""
    google_data_oauth_client_secret: str = ""
    google_data_oauth_redirect_uri: str = "http://127.0.0.1:8000/oauth/google/callback"
    web_app_url: str = "http://127.0.0.1:3000"
    decision_engine_enabled: bool = True
    se_ranking_api_key: str = ""
    # Daily refresh for mapped client integrations (UTC hour, overlapping lookback window).
    daily_sync_enabled: bool = True
    daily_sync_hour_utc: int = 11  # ~07:00 America/New_York (EST)
    daily_sync_lookback_days: int = 3

    def model_post_init(self, __context) -> None:
        object.__setattr__(self, "database_url", normalize_database_url(self.database_url))
        if self.is_production:
            self._assert_production_secrets()

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    def _assert_production_secrets(self) -> None:
        """
        Fail fast rather than boot with a publicly known secret.

        A missing AUTH_SECRET lets anyone forge an admin JWT; a missing
        INTEGRATION_TOKEN_KEY makes every stored Google refresh token
        decryptable with a value published in this repo.
        """
        problems: list[str] = []

        if self.auth_secret == INSECURE_AUTH_SECRET:
            problems.append("AUTH_SECRET is still the development default")
        elif len(self.auth_secret) < MIN_SECRET_LENGTH:
            problems.append(f"AUTH_SECRET must be at least {MIN_SECRET_LENGTH} characters")

        if self.integration_token_key == INSECURE_TOKEN_KEY:
            problems.append("INTEGRATION_TOKEN_KEY is still the development default")
        elif len(self.integration_token_key) < MIN_SECRET_LENGTH:
            problems.append(
                f"INTEGRATION_TOKEN_KEY must be at least {MIN_SECRET_LENGTH} characters"
            )

        if not self.internal_api_secret:
            problems.append("INTERNAL_API_SECRET must be set (guards POST /auth/upsert)")
        elif len(self.internal_api_secret) < MIN_SECRET_LENGTH:
            problems.append(
                f"INTERNAL_API_SECRET must be at least {MIN_SECRET_LENGTH} characters"
            )

        if "*" in self.cors_origins:
            problems.append("ALLOWED_ORIGINS must not be '*' while credentials are allowed")

        if problems:
            raise RuntimeError(
                "Refusing to start with APP_ENV=production: "
                + "; ".join(problems)
                + ". Generate secrets with: python -c \"import secrets;print(secrets.token_urlsafe(48))\""
            )

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.sma_admin_emails.split(",") if e.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
