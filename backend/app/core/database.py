"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


def _normalize_database_url(raw_url: str) -> str:
    """Normalize URLs to SQLAlchemy driver form."""

    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw_url


DATABASE_URL = _normalize_database_url(settings.database_url) if settings.database_url else "sqlite:///./eco_health.db"


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for request scope."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables for MVP runtime."""

    from app.models import (  # noqa: F401
        chat_message,
        goal,
        input_job,
        meal_log,
        pantry_item,
        profile,
        receipt_event,
        recommendation,
        user,
    )

    Base.metadata.create_all(bind=engine)
