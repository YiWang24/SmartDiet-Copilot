"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

DB_FILE = Path(__file__).resolve().parent / "test_backend.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["ENV"] = "development"
os.environ["ADK_ENABLED"] = "false"
os.environ["GEMINI_API_KEY"] = ""
os.environ["RECIPE_API_BASE_URL"] = ""

from app.core.database import Base, engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def database_lifecycle() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if DB_FILE.exists():
        DB_FILE.unlink()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
