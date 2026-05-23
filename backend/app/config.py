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
