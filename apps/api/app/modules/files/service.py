from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiProblemException
from app.core.schemas import BaseSchema
from app.core.validation import validate_storage_object_key, validate_upload_metadata
from app.integrations.storage import object_storage_service
from app.models import Project, ProjectFile, QuoteVersion, QuoteVersionFile, UploadedFile
from app.models.enums import UploadedFileCategory, UploadedFileStatus
from app.modules.audit.service import audit_service


class UploadedFileRead(BaseSchema):
    file_id: str
    object_key: str
    file_name: str
    content_type: str
    size_bytes: int
    checksum_sha256: str | None = None
    file_category: UploadedFileCategory
    status: UploadedFileStatus
    download_url: str
    public_url: str
    entity_type: str | None = None
    entity_id: str | None = None
    created_at: datetime
    uploaded_at: datetime | None = None


@dataclass(frozen=True)
class FileDownload:
    file_name: str
    content_type: str
    body: bytes


class FilesService:
    def create_upload_intent(
        self,
        session: Session,
        *,
        file_name: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
        entity_type: str | None,
        entity_id: str | None,
        file_category: UploadedFileCategory | None,
        actor_id: str,
    ) -> tuple[UploadedFileRead, str, dict[str, str], datetime]:
        self._validate_target(session, entity_type, entity_id)
        try:
            file_name, content_type, checksum_sha256 = validate_upload_metadata(
                file_name=file_name,
                content_type=content_type,
                size_bytes=size_bytes,
                checksum_sha256=checksum_sha256,
                file_category=file_category,
            )
        except ValueError as exc:
            raise ApiProblemException(422, str(exc), "Invalid Upload Request") from exc
        upload = object_storage_service.create_presigned_upload(
            file_name=file_name,
            content_type=content_type,
            checksum_sha256=checksum_sha256,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        record = UploadedFile(
            id=upload.file_id,
            storage_key=upload.object_key,
            original_filename=file_name,
            mime_type=content_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            file_category=file_category
            or self._infer_category(file_name, content_type, entity_type),
            status=UploadedFileStatus.awaiting_upload,
            uploaded_by_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            created_at=datetime.now(UTC),
        )
        session.add(record)
        session.flush()
        audit_service.record(
            session,
            action="file.upload.presigned",
            entity_type="uploaded_file",
            entity_id=record.id,
            actor_id=actor_id,
            summary=f"Created upload intent for {file_name}.",
            project_id=entity_id if entity_type == "project" else None,
        )
        return (
            self._serialize(record),
            upload.upload_url,
            upload.headers,
            upload.expires_at,
        )

    def finalize_upload(
        self,
        session: Session,
        *,
        file_id: str,
        object_key: str,
        checksum_sha256: str,
        actor_id: str,
    ) -> UploadedFileRead:
        record = session.get(UploadedFile, file_id)
        if record is None:
            raise ApiProblemException(404, f"File '{file_id}' was not found.", "File Not Found")
        if record.uploaded_by_id is not None and record.uploaded_by_id != actor_id:
            raise ApiProblemException(
                403,
                "Only the user who created the upload intent can finalize this upload.",
                "Upload Forbidden",
            )
        if record.status != UploadedFileStatus.awaiting_upload:
            raise ApiProblemException(
                409,
                "This upload intent has already been finalized.",
                "Upload Already Finalized",
            )
        try:
            validate_storage_object_key(object_key)
        except ValueError as exc:
            raise ApiProblemException(422, str(exc), "Invalid Upload Request") from exc
        if record.storage_key != object_key:
            raise ApiProblemException(
                409,
                "The provided object key does not match the registered upload intent.",
                "Upload Mismatch",
            )
        if record.checksum_sha256 != checksum_sha256:
            raise ApiProblemException(
                409,
                "The provided checksum does not match the registered upload intent.",
                "Upload Mismatch",
            )
        record.status = UploadedFileStatus.uploaded
        record.uploaded_at = datetime.now(UTC)
        self._ensure_link(session, record)
        session.flush()
        audit_service.record(
            session,
            action="file.upload.finalized",
            entity_type="uploaded_file",
            entity_id=record.id,
            actor_id=actor_id,
            summary=f"Finalized upload for {record.original_filename}.",
            project_id=record.entity_id if record.entity_type == "project" else None,
        )
        return self._serialize(record)

    def get(self, session: Session, file_id: str) -> UploadedFileRead | None:
        record = session.get(UploadedFile, file_id)
        return self._serialize(record) if record is not None else None

    def download(self, session: Session, file_id: str) -> FileDownload:
        record = session.get(UploadedFile, file_id)
        if record is None:
            raise ApiProblemException(404, f"File '{file_id}' was not found.", "File Not Found")
        if record.status != UploadedFileStatus.uploaded:
            raise ApiProblemException(
                409,
                "Only finalized uploaded files can be downloaded.",
                "File Not Available",
            )
        try:
            body = object_storage_service.read_object_bytes(record.storage_key)
        except FileNotFoundError as exc:
            raise ApiProblemException(
                404,
                "The stored file content could not be found.",
                "Stored File Not Found",
            ) from exc
        except ValueError as exc:
            raise ApiProblemException(422, str(exc), "Invalid Stored File") from exc
        except httpx.HTTPError as exc:
            raise ApiProblemException(
                502,
                "The file storage service is unavailable.",
                "Storage Error",
            ) from exc

        return FileDownload(
            file_name=record.original_filename,
            content_type=record.mime_type,
            body=body,
        )

    def _ensure_link(self, session: Session, record: UploadedFile) -> None:
        if record.entity_type == "project" and record.entity_id is not None:
            existing = session.scalar(
                select(ProjectFile).where(
                    ProjectFile.project_id == record.entity_id,
                    ProjectFile.uploaded_file_id == record.id,
                )
            )
            if existing is None:
                session.add(
                    ProjectFile(
                        project_id=record.entity_id,
                        uploaded_file_id=record.id,
                        label=record.original_filename,
                        created_at=datetime.now(UTC),
                    )
                )
        if record.entity_type == "quote_version" and record.entity_id is not None:
            existing = session.scalar(
                select(QuoteVersionFile).where(
                    QuoteVersionFile.quote_version_id == record.entity_id,
                    QuoteVersionFile.uploaded_file_id == record.id,
                )
            )
            if existing is None:
                session.add(
                    QuoteVersionFile(
                        quote_version_id=record.entity_id,
                        uploaded_file_id=record.id,
                        label=record.original_filename,
                        created_at=datetime.now(UTC),
                    )
                )

    def _validate_target(
        self,
        session: Session,
        entity_type: str | None,
        entity_id: str | None,
    ) -> None:
        if entity_type is None and entity_id is None:
            return
        if entity_type is None or entity_id is None:
            raise ApiProblemException(
                422,
                "File uploads must provide entity type and entity id together.",
                "Invalid File Target",
            )
        if entity_type == "project" and session.get(Project, entity_id) is None:
            raise ApiProblemException(
                422,
                f"Project '{entity_id}' was not found.",
                "Invalid File Target",
            )
        if entity_type == "quote_version" and session.get(QuoteVersion, entity_id) is None:
            raise ApiProblemException(
                422,
                f"Quote version '{entity_id}' was not found.",
                "Invalid File Target",
            )
        if entity_type not in {"project", "quote_version"}:
            raise ApiProblemException(
                422,
                f"Entity type '{entity_type}' is not supported for file uploads.",
                "Invalid File Target",
            )

    def _infer_category(
        self, file_name: str, content_type: str, entity_type: str | None
    ) -> UploadedFileCategory:
        lower_name = file_name.lower()
        lower_entity = (entity_type or "").lower()
        if content_type == "application/pdf" and "quote" in f"{lower_name} {lower_entity}":
            return UploadedFileCategory.quote_pdf
        if "forecast" in lower_entity:
            return UploadedFileCategory.forecast_attachment
        if entity_type == "project":
            return UploadedFileCategory.project_attachment
        return UploadedFileCategory.other

    def _serialize(self, record: UploadedFile) -> UploadedFileRead:
        download_url = self._build_download_url(record.id)
        return UploadedFileRead(
            file_id=record.id,
            object_key=record.storage_key,
            file_name=record.original_filename,
            content_type=record.mime_type,
            size_bytes=record.size_bytes,
            checksum_sha256=record.checksum_sha256,
            file_category=record.file_category,
            status=record.status,
            download_url=download_url,
            public_url=download_url,
            entity_type=record.entity_type,
            entity_id=record.entity_id,
            created_at=record.created_at,
            uploaded_at=record.uploaded_at,
        )

    def _build_download_url(self, file_id: str) -> str:
        settings = get_settings()
        return (
            f"{settings.api_base_url.rstrip('/')}"
            f"{settings.api_base_path}/files/{file_id}/download"
        )


files_service = FilesService()
