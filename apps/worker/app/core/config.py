from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _get_psycopg_database_url(database_url: str | None) -> str:
    normalized = database_url or "postgresql://quotes4:quotes4@localhost:5432/quotes4"
    if normalized.startswith("postgresql+psycopg://"):
        return normalized.replace("postgresql+psycopg://", "postgresql://", 1)
    return normalized


@dataclass(frozen=True)
class WorkerSettings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    worker_name: str = field(default_factory=lambda: os.getenv("WORKER_NAME", "quotes4-worker"))
    database_url: str = field(
        default_factory=lambda: _get_psycopg_database_url(os.getenv("DATABASE_URL"))
    )
    api_base_url: str = field(default_factory=lambda: os.getenv("API_BASE_URL", "http://localhost:3001"))
    api_base_path: str = field(default_factory=lambda: os.getenv("API_BASE_PATH", "/api/v1"))
    worker_callback_token: str = field(
        default_factory=lambda: os.getenv("WORKER_CALLBACK_TOKEN", "quotes4-worker-token")
    )
    s3_endpoint: str = field(default_factory=lambda: os.getenv("S3_ENDPOINT", "http://localhost:9000"))
    s3_bucket: str = field(default_factory=lambda: os.getenv("S3_BUCKET", "quotes4-assets"))
    api_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("WORKER_API_TIMEOUT_SECONDS", "15"))
    )
    poll_interval_seconds: float = field(
        default_factory=lambda: float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "5"))
    )
    run_forever: bool = field(
        default_factory=lambda: os.getenv("WORKER_RUN_FOREVER", "true").lower() == "true"
    )


@lru_cache(maxsize=1)
def get_settings() -> WorkerSettings:
    return WorkerSettings()
