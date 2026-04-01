from __future__ import annotations

import os
from pathlib import Path
from tempfile import gettempdir

import pytest
from fastapi.testclient import TestClient

TEST_DB_PATH = Path(gettempdir()) / "quotes4_api_tests.sqlite3"
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")
os.environ.setdefault("AUTH_INVITE_SECRET", "quotes4-test-secret")
os.environ.setdefault("DEV_ADMIN_EMAIL", "admin@quotes4.dev")
os.environ.setdefault("DEV_ADMIN_PASSWORD", "quotes4-admin-password")
os.environ.setdefault("WORKER_CALLBACK_TOKEN", "quotes4-test-worker-token")
os.environ.setdefault("S3_ENDPOINT", "http://storage.test")
os.environ.setdefault("S3_BUCKET", "quotes4-test-assets")
os.environ.setdefault("STORAGE_PUBLIC_BASE_URL", "http://storage.test/quotes4-test-assets")

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_engine, get_session_factory, reset_db_state  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import run_seed  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database() -> None:
    get_settings.cache_clear()
    reset_db_state()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    run_seed()
    app.openapi_schema = None
    yield
    reset_db_state()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    with get_session_factory()() as session:
        yield session
