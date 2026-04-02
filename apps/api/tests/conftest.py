from __future__ import annotations

import os
from pathlib import Path
from tempfile import gettempdir

import pytest
from fastapi.testclient import TestClient

DEFAULT_TEST_DB_PATH = Path(gettempdir()) / f"quotes4_api_tests_{os.getpid()}.sqlite3"
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{DEFAULT_TEST_DB_PATH}"
os.environ["AUTH_INVITE_SECRET"] = "quotes4-test-secret"
os.environ["DEV_ADMIN_EMAIL"] = "admin@quotes4.dev"
os.environ["DEV_ADMIN_PASSWORD"] = "quotes4-admin-password"
os.environ["WORKER_CALLBACK_TOKEN"] = "quotes4-test-worker-token"
os.environ["S3_ENDPOINT"] = "http://storage.test"
os.environ["S3_BUCKET"] = "quotes4-test-assets"
os.environ["STORAGE_PUBLIC_BASE_URL"] = "http://storage.test/quotes4-test-assets"


def _resolve_test_db_path() -> Path:
    database_url = os.environ.get("DATABASE_URL", "")
    sqlite_prefix = "sqlite:///"
    if database_url.startswith(sqlite_prefix):
        return Path(database_url.removeprefix(sqlite_prefix))
    return DEFAULT_TEST_DB_PATH

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_engine, get_session_factory, reset_db_state  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import run_seed  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_database() -> None:
    test_db_path = _resolve_test_db_path()
    get_settings.cache_clear()
    reset_db_state()
    if test_db_path.exists():
        test_db_path.unlink()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    run_seed()
    app.openapi_schema = None
    yield
    reset_db_state()
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    with get_session_factory()() as session:
        yield session
