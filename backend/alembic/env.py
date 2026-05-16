import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Our app imports ───────────────────────────────────────────────────────────

from app.config import settings
from app.db.base import Base
import app.models  # noqa: F401 — registers all models in Base.metadata

# ── Alembic config ────────────────────────────────────────────────────────────

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic compares Base.metadata (our models) against the real database
# to figure out what SQL to generate.
target_metadata = Base.metadata

# Build async URL from DATABASE_URL in .env.
# "postgresql://"  → sync (psycopg2) — Alembic offline mode
# "postgresql+asyncpg://" → async  — Alembic online mode + FastAPI app
ASYNC_URL = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


# ── Offline mode ─────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Offline mode: generate SQL to stdout without connecting to a database.
    Useful for reviewing what a migration will do before running it.
    Run with: alembic upgrade head --sql
    """
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ───────────────────────────────────────────────────────────────

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Online mode: connect to the real database and apply migrations.
    This is the mode used by `alembic upgrade head`.
    """
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = ASYNC_URL

    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # don't pool connections during migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# ── Entry point ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
