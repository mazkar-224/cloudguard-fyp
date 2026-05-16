from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Every SQLAlchemy model in this project inherits from this class.

    SQLAlchemy uses Base.metadata to keep a registry of all tables.
    Alembic reads Base.metadata to know which tables exist and generate
    migration files automatically.
    """
    pass
