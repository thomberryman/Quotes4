from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    from argon2 import PasswordHasher as Argon2PasswordHasher
    from argon2 import Type as Argon2Type
except ImportError:  # pragma: no cover - environment dependent fallback
    Argon2PasswordHasher = None
    Argon2Type = None

from app.core.config import get_settings


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_at: datetime


class PasswordHasher:
    def __init__(self) -> None:
        settings = get_settings()
        self._hasher = (
            Argon2PasswordHasher(
                type=Argon2Type.ID,
                time_cost=3,
                memory_cost=65536,
                parallelism=4,
            )
            if Argon2PasswordHasher and Argon2Type
            else None
        )
        if self._hasher is None and settings.app_env not in {"development", "test"}:
            raise RuntimeError("Argon2 password hashing support is required outside development.")

    @property
    def available(self) -> bool:
        return self._hasher is not None

    def hash_password(self, plain_password: str) -> str:
        if self._hasher is None:
            digest = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
            return f"fallback-sha256${digest}"

        return self._hasher.hash(plain_password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        if hashed_password.startswith("fallback-sha256$"):
            digest = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
            return hmac.compare_digest(hashed_password, f"fallback-sha256${digest}")

        if self._hasher is None:
            return hashed_password == self.hash_password(plain_password)

        try:
            return bool(self._hasher.verify(hashed_password, plain_password))
        except Exception:  # pragma: no cover - argon2 implementation specific
            return False


def build_password_hasher() -> PasswordHasher:
    return PasswordHasher()


def create_access_token(subject: str, permissions: list[str]) -> AccessToken:
    settings = get_settings()
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.auth_access_token_ttl_minutes)
    payload = {
        "sub": subject,
        "permissions": permissions,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded_payload = urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.auth_access_token_secret.encode("utf-8"),
        encoded_payload,
        hashlib.sha256,
    ).hexdigest()
    token = f"{encoded_payload.decode('utf-8')}.{signature}"
    return AccessToken(token=token, expires_at=expires_at)


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        encoded_payload, supplied_signature = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise ValueError("Malformed access token.") from exc
    expected_signature = hmac.new(
        settings.auth_access_token_secret.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise ValueError("Invalid access token signature.")

    try:
        raw_payload = urlsafe_b64decode(encoded_payload.encode("utf-8"))
        payload = json.loads(raw_payload.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Malformed access token payload.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Malformed access token payload.")

    subject = payload.get("sub")
    expires_at = payload.get("exp")
    if not isinstance(subject, str) or not subject:
        raise ValueError("Malformed access token subject.")
    if not isinstance(expires_at, int):
        raise ValueError("Malformed access token expiry.")
    if expires_at < int(datetime.now(UTC).timestamp()):
        raise ValueError("Access token expired.")
    return payload
