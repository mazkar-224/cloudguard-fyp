from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings


# The engine is the core SQLAlchemy object that manages the connection pool.
# `create_engine` does NOT open a connection immediately — it's lazy.
engine = create_engine(
    settings.database_url,
    # echo=True prints every SQL query to the console — useful for debugging.
    # Set to False in production so logs aren't flooded.
    echo=settings.debug,
)

# A SessionLocal is a factory that creates new database sessions.
# Each request gets its own session so transactions stay isolated.
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,  # we control when to commit
    autoflush=False,   # don't flush changes until we say so
)


class Base(DeclarativeBase):
    """
    All SQLAlchemy models will inherit from this Base class.
    SQLAlchemy uses it to track which tables belong to this project.
    """
    pass


def get_db():
    """
    FastAPI dependency that provides a database session to a route handler.

    Usage in a route:
        from fastapi import Depends
        from app.database import get_db

        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...

    The `yield` means FastAPI will close the session automatically
    after the request finishes — even if an error occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
