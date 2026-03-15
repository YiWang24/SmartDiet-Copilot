"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import sqlite3
import threading

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

settings = get_settings()


def _normalize_database_url(raw_url: str) -> str:
    """Normalize URLs to SQLAlchemy driver form."""

    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if raw_url in {"sqlite:///:memory:", "sqlite+pysqlite:///:memory:"}:
        return "sqlite://"
    return raw_url


def _default_database_url() -> str:
    """Resolve default SQLite URL when DATABASE_URL is not explicitly set."""

    if settings.sqlite_mode == "file":
        snapshot_path = Path(settings.sqlite_snapshot_path).expanduser()
        return f"sqlite:///{snapshot_path}"

    # Shared in-memory sqlite database (single-process local runtime).
    return "sqlite:///file:eco_health_runtime?mode=memory&cache=shared&uri=true"


DATABASE_URL = _normalize_database_url(settings.database_url) if settings.database_url else _default_database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")
IS_SQLITE_MEMORY = (
    DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}
    or ("mode=memory" in DATABASE_URL and DATABASE_URL.startswith("sqlite:///file:"))
)
SQLITE_SNAPSHOT_PATH = Path(settings.sqlite_snapshot_path).expanduser()
SQLITE_AUTO_SNAPSHOT = bool(settings.sqlite_auto_snapshot and IS_SQLITE_MEMORY)
_SNAPSHOT_LOCK = threading.Lock()


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


_ENGINE_KWARGS: dict = {"pool_pre_ping": True}

if IS_SQLITE:
    _ENGINE_KWARGS["connect_args"] = {"check_same_thread": False, "timeout": 30}
    if IS_SQLITE_MEMORY:
        _ENGINE_KWARGS["poolclass"] = StaticPool

engine = create_engine(DATABASE_URL, **_ENGINE_KWARGS)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, class_=Session
)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:  # noqa: ANN001, ARG001
    """Tune SQLite for local write contention (file mode) and retries."""

    if not IS_SQLITE:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA busy_timeout=30000")
    if not IS_SQLITE_MEMORY:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def _engine_sqlite_connection():
    """Return SQLAlchemy raw DB-API sqlite connection."""

    raw = engine.raw_connection()
    conn = getattr(raw, "driver_connection", None) or getattr(raw, "connection")
    return raw, conn


def restore_sqlite_snapshot() -> None:
    """Restore file snapshot into in-memory sqlite runtime."""

    if not SQLITE_AUTO_SNAPSHOT or not SQLITE_SNAPSHOT_PATH.exists():
        return

    src = sqlite3.connect(str(SQLITE_SNAPSHOT_PATH))
    raw, dest = _engine_sqlite_connection()
    try:
        src.backup(dest)
    finally:
        raw.close()
        src.close()


def persist_sqlite_snapshot() -> None:
    """Persist in-memory sqlite runtime to snapshot file."""

    if not SQLITE_AUTO_SNAPSHOT:
        return

    SQLITE_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _SNAPSHOT_LOCK:
        raw, src = _engine_sqlite_connection()
        dest = sqlite3.connect(str(SQLITE_SNAPSHOT_PATH))
        try:
            src.backup(dest)
        finally:
            dest.close()
            raw.close()


@event.listens_for(Session, "after_commit")
def _persist_snapshot_after_commit(session: Session) -> None:  # noqa: ARG001
    """Flush sqlite memory state to file after each successful commit."""

    persist_sqlite_snapshot()


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
        calendar_block,
        chat_message,
        chat_turn,
        cooking_task,
        feedback_event,
        goal,
        input_job,
        meal_log,
        pantry_item,
        plan_run,
        prep_window,
        profile,
        receipt_event,
        recommendation,
        user,
        user_memory_profile,
    )

    restore_sqlite_snapshot()
    Base.metadata.create_all(bind=engine)
    persist_sqlite_snapshot()
