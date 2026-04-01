from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.validation import validate_storage_object_key


class ObjectStorageService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def read_object_bytes(self, object_key: str) -> bytes:
        if object_key.startswith("/"):
            if self.settings.app_env != "test":
                raise ValueError("Absolute file paths are only permitted in test mode.")
            path = Path(object_key)
            if not path.exists():
                raise FileNotFoundError(f"Object path '{object_key}' was not found.")
            return path.read_bytes()

        validated_object_key = validate_storage_object_key(object_key)
        object_url = (
            f"{self.settings.s3_endpoint.rstrip('/')}"
            f"/{self.settings.s3_bucket}/{quote(validated_object_key.lstrip('/'), safe='/')}"
        )
        response = httpx.get(object_url, timeout=30.0)
        response.raise_for_status()
        return response.content


object_storage_service = ObjectStorageService()
