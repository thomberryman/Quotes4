from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _get_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default

    parsed = tuple(item.strip() for item in value.split(",") if item.strip())
    return parsed or default


def _get_text(value: str | None, default: str) -> str:
    if value is None:
        return default
    normalized = value.strip()
    return normalized or default


@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Quotes4 API"))
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "3001")))
    api_base_path: str = field(default_factory=lambda: os.getenv("API_BASE_PATH", "/api/v1"))
    app_base_url: str = field(
        default_factory=lambda: os.getenv("APP_BASE_URL", "http://localhost:3000")
    )
    api_base_url: str = field(
        default_factory=lambda: os.getenv("API_BASE_URL", "http://localhost:3001")
    )
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "postgresql+psycopg://quotes4:quotes4@localhost:5432/quotes4"
        )
    )
    auth_invite_secret: str = field(
        default_factory=lambda: os.getenv("AUTH_INVITE_SECRET", "replace-me")
    )
    auth_access_token_secret: str = field(
        default_factory=lambda: os.getenv(
            "AUTH_ACCESS_TOKEN_SECRET",
            os.getenv("AUTH_INVITE_SECRET", "replace-me"),
        )
    )
    auth_access_token_ttl_minutes: int = field(
        default_factory=lambda: int(os.getenv("AUTH_ACCESS_TOKEN_TTL_MINUTES", "15"))
    )
    auth_refresh_token_ttl_days: int = field(
        default_factory=lambda: int(os.getenv("AUTH_REFRESH_TOKEN_TTL_DAYS", "14"))
    )
    worker_callback_token: str = field(
        default_factory=lambda: os.getenv("WORKER_CALLBACK_TOKEN", "quotes4-worker-token")
    )
    web_origin: str = field(
        default_factory=lambda: os.getenv("WEB_ORIGIN", "http://localhost:3000")
    )
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: _get_csv(os.getenv("ALLOWED_ORIGINS"), ("http://localhost:3000",))
    )
    s3_endpoint: str = field(
        default_factory=lambda: os.getenv("S3_ENDPOINT", "http://localhost:9000")
    )
    s3_region: str = field(
        default_factory=lambda: os.getenv("S3_REGION", "eu-west-2")
    )
    s3_bucket: str = field(
        default_factory=lambda: os.getenv("S3_BUCKET", "quotes4-assets")
    )
    s3_access_key: str = field(
        default_factory=lambda: os.getenv("S3_ACCESS_KEY", "quotes4")
    )
    s3_secret_key: str = field(
        default_factory=lambda: os.getenv("S3_SECRET_KEY", "quotes4-secret")
    )
    storage_public_base_url: str = field(
        default_factory=lambda: os.getenv(
            "STORAGE_PUBLIC_BASE_URL", "http://localhost:9000/quotes4-assets"
        )
    )
    mailer_mode: str = field(default_factory=lambda: os.getenv("MAILER_MODE", "log"))
    mailer_from_address: str = field(
        default_factory=lambda: os.getenv("MAILER_FROM_ADDRESS", "no-reply@quotes4.local")
    )
    mailer_base_url: str = field(
        default_factory=lambda: os.getenv("MAILER_BASE_URL", "http://localhost:8025")
    )
    auth_access_cookie_name: str = field(
        default_factory=lambda: _get_text(
            os.getenv("AUTH_ACCESS_COOKIE_NAME"),
            "quotes4_access_token",
        )
    )
    auth_refresh_cookie_name: str = field(
        default_factory=lambda: _get_text(
            os.getenv("AUTH_REFRESH_COOKIE_NAME"),
            "quotes4_refresh_token",
        )
    )
    auth_csrf_cookie_name: str = field(
        default_factory=lambda: _get_text(
            os.getenv("AUTH_CSRF_COOKIE_NAME"),
            "quotes4_csrf_token",
        )
    )

    @property
    def use_secure_cookies(self) -> bool:
        return self.app_env not in {"development", "test"}

    @property
    def is_test_env(self) -> bool:
        return self.app_env == "test"

    @property
    def is_development_env(self) -> bool:
        return self.app_env == "development"

    def validate_runtime(self) -> None:
        if self.use_secure_cookies and (
            self.auth_invite_secret == "replace-me"
            or self.auth_access_token_secret == "replace-me"
            or self.worker_callback_token == "quotes4-worker-token"
        ):
            raise RuntimeError(
                "Production configuration requires non-default auth and worker secrets."
            )
        if "*" in self.allowed_origins and self.use_secure_cookies:
            raise RuntimeError(
                "Wildcard allowed origins are not permitted when secure cookies are enabled."
            )
        if len(
            {
                self.auth_access_cookie_name,
                self.auth_refresh_cookie_name,
                self.auth_csrf_cookie_name,
            }
        ) != 3:
            raise RuntimeError("Auth cookie names must be distinct for access, refresh, and CSRF.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
