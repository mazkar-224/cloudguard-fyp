from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings


# SQLAlchemy needs a different URL prefix for async connections.
# "postgresql://"  → sync driver (psycopg2) — used by Alembic migrations
# "postgresql+asyncpg://" → async driver — used by the running FastAPI app
#
# We build the async URL from DATABASE_URL so there's only one value in .env.
ASYNC_DATABASE_URL = settings.database_url.replace(
    "postgresql://", "postgresql+asyncpg://", 1
)

# The async engine manages the connection pool for the whole app.
# echo=True logs every SQL query — useful during development.
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=settings.debug,
)

# async_sessionmaker creates new AsyncSession objects on demand.
# expire_on_commit=False means we can still read object attributes
# after committing without triggering another database query.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides an async database session per request.

    Usage in a route:
        from fastapi import Depends
        from app.db.session import get_db

        @router.get("/costs")
        async def list_costs(db: AsyncSession = Depends(get_db)):
            ...

    The `async with` block guarantees the session is closed after every
    request, even if an exception occurs mid-way through.
    """
    async with AsyncSessionLocal() as session:
        yield session
