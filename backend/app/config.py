from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration comes from environment variables (or the .env file).
    pydantic-settings reads the .env file automatically and validates types.
    If a required variable is missing, the app will refuse to start and
    tell you exactly which variable is missing — very helpful during dev.
    """

    # Database
    database_url: str

    # AWS
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "us-east-1"  # which AWS region to use by default

    # App
    secret_key: str
    debug: bool = False
    environment: str = "development"  # development | staging | production
    log_level: str = "INFO"           # DEBUG | INFO | WARNING | ERROR

    # Auth (Phase 6.1) — JWT signing.
    # access_token_secret signs the login tokens. It defaults to empty and
    # falls back to secret_key (see auth_service), so the app still boots if you
    # haven't set a dedicated value — but PRODUCTION should set a long random
    # ACCESS_TOKEN_SECRET distinct from SECRET_KEY.
    access_token_secret: str = ""
    access_token_expire_minutes: int = 60 * 24  # 24h — how long a login lasts

    # Background scheduler (APScheduler) toggle. The scheduler runs IN-PROCESS
    # inside the uvicorn app, so with more than one uvicorn worker it would start
    # once per worker and fire each job N times. Keep it on with a single worker
    # (the default deployment), or set ENABLE_SCHEDULER=false on extra workers /
    # replicas and run it on exactly one instance.
    enable_scheduler: bool = True

    # Encryption (Phase 6.2) — symmetric key for encrypting users' AWS secrets
    # at rest with Fernet. MUST be a urlsafe-base64 32-byte key, generated with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Defaults to empty so the test suite and credential-free dev can still boot;
    # the crypto service raises a clear error if you try to use it while unset.
    encryption_key: str = ""

    # CORS — comma-separated browser origins allowed to call the API
    # cross-origin. In production the SPA is served same-origin through nginx
    # (/api proxy), so this is usually empty; set it only if the frontend is
    # ever hosted on a different origin than the API.
    cors_allow_origins: str = ""

    # SendGrid — email alerts for detected anomalies.
    # All three default to empty so the test suite (which doesn't need real
    # email) starts cleanly.  The sync job skips notifications if any are blank.
    sendgrid_api_key: str = ""
    alert_sender_email: str = ""      # MUST be a SendGrid verified single sender
    alert_recipient_email: str = ""   # where anomaly alerts are delivered

    # SettingsConfigDict is the modern Pydantic v2 way to configure settings
    # (replaces the old inner `class Config` pattern)
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


# Create one shared instance — import `settings` wherever you need config values
settings = Settings()
