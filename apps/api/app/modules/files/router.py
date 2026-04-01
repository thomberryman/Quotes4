from __future__ import annotations

from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, require_permissions
from app.core.db import get_db_session
from app.core.errors import ApiProblemException
from app.core.schemas import BaseSchema
from app.core.validation import (
    normalize_content_type,
    normalize_file_name,
    normalize_sha256_checksum,
    validate_storage_object_key,
)
from app.integrations.storage import object_storage_service
from app.models.enums import UploadedFileCategory
from app.modules.files.service import UploadedFileRead, files_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
FilesReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("files.read")),
]
FilesWriteSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("files.write")),
]


class PresignUploadRequest(BaseSchema):
    file_name: str
    content_type: str
    size_bytes: int = Field(gt=0)
    checksum_sha256: str
    file_category: UploadedFileCategory | None = None
    entity_type: str | None = None
    entity_id: str | None = None

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        return normalize_file_name(value)

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        return normalize_content_type(value)

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum_sha256(cls, value: str) -> str:
        return normalize_sha256_checksum(value)

    @model_validator(mode="after")
    def validate_target_pair(self) -> PresignUploadRequest:
        if bool(self.entity_type) != bool(self.entity_id):
            raise ValueError("entityType and entityId must be provided together.")
        return self


class PresignUploadResponse(BaseSchema):
    file_id: str
    bucket: str
    object_key: str
    upload_url: str
    download_url: str
    public_url: str
    expires_at: datetime
    required_headers: dict[str, str]


class FinalizeUploadRequest(BaseSchema):
    file_id: str
    object_key: str
    checksum_sha256: str

    @field_validator("object_key")
    @classmethod
    def validate_object_key(cls, value: str) -> str:
        return validate_storage_object_key(value)

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum_sha256(cls, value: str) -> str:
        return normalize_sha256_checksum(value)


class FinalizeUploadResponse(BaseSchema):
    file: UploadedFileRead


@router.post("/uploads/presign", response_model=PresignUploadResponse, status_code=201)
def create_upload_intent(
    payload: PresignUploadRequest,
    session: DbSession,
    subject: FilesWriteSubject,
) -> PresignUploadResponse:
    upload, upload_url, headers, expires_at = files_service.create_upload_intent(
        session,
        file_name=payload.file_name,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        checksum_sha256=payload.checksum_sha256,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        file_category=payload.file_category,
        actor_id=subject.user.id,
    )
    session.commit()
    return PresignUploadResponse(
        file_id=upload.file_id,
        bucket=object_storage_service.settings.s3_bucket,
        object_key=upload.object_key,
        upload_url=upload_url,
        download_url=upload.download_url,
        public_url=upload.public_url,
        expires_at=expires_at,
        required_headers=headers,
    )


@router.post("/uploads/finalize", response_model=FinalizeUploadResponse)
def finalize_upload(
    payload: FinalizeUploadRequest,
    session: DbSession,
    subject: FilesWriteSubject,
) -> FinalizeUploadResponse:
    upload = files_service.finalize_upload(
        session,
        file_id=payload.file_id,
        object_key=payload.object_key,
        checksum_sha256=payload.checksum_sha256,
        actor_id=subject.user.id,
    )
    session.commit()
    return FinalizeUploadResponse(file=upload)


@router.get("/{file_id}", response_model=UploadedFileRead)
def get_file(
    file_id: str,
    session: DbSession,
    _subject: FilesReadSubject,
) -> UploadedFileRead:
    upload = files_service.get(session, file_id)
    if upload is None:
        raise ApiProblemException(404, f"File '{file_id}' was not found.", title="File Not Found")
    return upload


@router.get("/{file_id}/download")
def download_file(
    file_id: str,
    session: DbSession,
    _subject: FilesReadSubject,
) -> Response:
    file_download = files_service.download(session, file_id)
    encoded_file_name = quote(file_download.file_name)
    return Response(
        content=file_download.body,
        media_type=file_download.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_file_name}",
            "Content-Length": str(len(file_download.body)),
            "Cache-Control": "private, no-store",
        },
    )
