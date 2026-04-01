from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.core.validation import validate_storage_object_key


@dataclass(frozen=True)
class PresignedUpload:
    file_id: str
    object_key: str
    upload_url: str
    public_url: str
    expires_at: datetime
    headers: dict[str, str]


class ObjectStorageService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def create_presigned_upload(
        self,
        *,
        file_name: str,
        content_type: str,
        checksum_sha256: str,
        entity_type: str | None,
        entity_id: str | None,
    ) -> PresignedUpload:
        suffix = Path(file_name).suffix.lower()
        file_id = uuid4().hex
        entity_segment = entity_type or "unscoped"
        object_key = "/".join(
            part
            for part in [entity_segment, entity_id or file_id, f"{file_id}{suffix}"]
            if part
        )
        upload_url = (
            f"{self.settings.s3_endpoint.rstrip('/')}/{self.settings.s3_bucket}/{object_key}"
            "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=development&X-Amz-Signature=stub"
        )
        public_url = f"{self.settings.storage_public_base_url.rstrip('/')}/{object_key}"
        headers = {
            "Content-Type": content_type,
            "x-amz-checksum-sha256": checksum_sha256,
        }
        expires_at = datetime.now(UTC) + timedelta(minutes=15)

        return PresignedUpload(
            file_id=file_id,
            object_key=object_key,
            upload_url=upload_url,
            public_url=public_url,
            expires_at=expires_at,
            headers=headers,
        )

    def read_object_bytes(self, object_key: str) -> bytes:
        if object_key.startswith("/"):
            if not self.settings.is_test_env:
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
