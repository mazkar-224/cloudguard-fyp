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
    aws_default_region: str = "us-east-1"  # default to us-east-1 if not set

    # App
    secret_key: str
    debug: bool = False

    # SettingsConfigDict is the modern Pydantic v2 way to configure settings
    # (replaces the old inner `class Config` pattern)
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


# Create one shared instance — import `settings` wherever you need config values
settings = Settings()
