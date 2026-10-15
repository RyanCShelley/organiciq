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


#: The only values that relax the production checks.
DEVELOPMENT_ENVIRONMENTS = frozenset({"development", "dev", "test", "local"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    #: Production unless somebody says otherwise. This used to default to
    #: "development" and detect production from Railway's environment name, so
    #: the secret checks were on only because one environment happened to be
    #: called "production". A "staging" or preview environment on real data
    #: would have booted with the signing secret and encryption key published
    #: in this repo. Now the safe state is the default, and relaxing it takes
    #: an explicit APP_ENV=development (or dev / test / local).
    app_env: str = "production"
    database_url: str = "postgresql+psycopg://organiciq:organiciq@localhost:5432/organiciq"
    auth_secret: str = INSECURE_AUTH_SECRET
    sma_admin_emails: str = ""
    # Comma-separated. Both are accepted through the .com migration; existing
    # staff accounts and Google Workspace aliases are still on .net.
    sma_google_hosted_domain: str = "smamarketing.com,smamarketing.net"
    # Domains that are the same company, for matching a person across
    # systems. Deliberately not the login setting above: that one answers
    # "who may sign in" and gets narrowed, and narrowing it should not make
    # beth@smamarketing.com a different person from beth@smamarketing.net
    # while the move from .net to .com is half done.
    identity_domains: str = "smamarketing.com,smamarketing.net"
    integration_token_key: str = INSECURE_TOKEN_KEY
    # Set only while rotating; see app/rotate_integration_key.py.
    integration_token_key_previous: str = ""
    # Shared secret the web app presents to POST /auth/upsert. Required in production.
    internal_api_secret: str = ""
    allowed_origins: str = "http://localhost:3000"
    worker_poll_interval_seconds: float = 2.0
    google_data_oauth_client_id: str = ""
    google_data_oauth_client_secret: str = ""
    google_data_oauth_redirect_uri: str = "http://127.0.0.1:8000/oauth/google/callback"
    web_app_url: str = "http://127.0.0.1:3000"
    se_ranking_api_key: str = ""
    # Daily refresh for mapped client integrations (UTC hour, overlapping lookback window).
    daily_sync_enabled: bool = True
    daily_sync_hour_utc: int = 11  # ~07:00 America/New_York (EST)
    #: Full site crawl, staggered across clients by the scheduler.
    site_crawl_enabled: bool = True
    #: Which crawl the Decision Engine reads: "site_crawl" (ours) or
    #: "se_ranking_audit". Both keep writing; this only chooses the reader, so a
    #: bad crawl can be backed out by flipping one variable.
    crawl_facts_source: str = "site_crawl"
    daily_sync_lookback_days: int = 3
    #: Judge the actions whose check date has arrived, once a day. Later than
    #: the sync hour so the day's facts have landed before anything is judged
    #: on them.
    results_check_enabled: bool = True
    results_check_hour_utc: int = 14
    #: The SERP feature pull. Monthly, because every query is a billed call
    #: and a reading stays usable for 45 days.
    serp_pull_enabled: bool = True
    serp_pull_hour_utc: int = 15
    #: Terms per client per month. The cost is this times the number of
    #: clients whose Search Console data makes the result actionable.
    serp_pull_limit: int = 20
    #: The monthly engine run. On this day of the month it runs the month
    #: before — Search Console lags about three days, so by the fifth the
    #: previous month has closed out.
    monthly_run_enabled: bool = True
    monthly_run_day: int = 5
    monthly_run_hour_utc: int = 12

    def model_post_init(self, __context) -> None:
        object.__setattr__(self, "database_url", normalize_database_url(self.database_url))
        if self.is_production:
            self._assert_production_secrets()

    @property
    def is_production(self) -> bool:
        """
        True unless APP_ENV explicitly names a development environment.

        An unset value, "production", and anything unrecognised ("staging",
        a typo) are all treated as production: the checks that refuse default
        secrets are the thing to fail towards.
        """
        return self.app_env.strip().lower() not in DEVELOPMENT_ENVIRONMENTS

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
    def hosted_domains(self) -> set[str]:
        return {
            d.strip().lower().lstrip("@")
            for d in self.sma_google_hosted_domain.split(",")
            if d.strip()
        }

    def is_workspace_email(self, email: str) -> bool:
        domain = email.strip().lower().rpartition("@")[2]
        return bool(domain) and domain in self.hosted_domains

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.sma_admin_emails.split(",") if e.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
