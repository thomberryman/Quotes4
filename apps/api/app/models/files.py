from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentifierMixin
from app.models.enums import UploadedFileCategory, UploadedFileStatus

if TYPE_CHECKING:
    from app.models.ingestion import CetaImport, PdfExtractionRun
    from app.models.projects import Project
    from app.models.quotes import QuoteVersion


class UploadedFile(IdentifierMixin, Base):
    __tablename__ = "uploaded_files"

    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer())
    checksum_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_category: Mapped[UploadedFileCategory] = mapped_column(
        SqlEnum(UploadedFileCategory, name="uploaded_file_category", native_enum=False, length=32)
    )
    status: Mapped[UploadedFileStatus] = mapped_column(
        SqlEnum(UploadedFileStatus, name="uploaded_file_status", native_enum=False, length=32),
        default=UploadedFileStatus.awaiting_upload,
    )
    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project_links: Mapped[list[ProjectFile]] = relationship(
        back_populates="uploaded_file", cascade="all, delete-orphan"
    )
    quote_version_links: Mapped[list[QuoteVersionFile]] = relationship(
        back_populates="uploaded_file", cascade="all, delete-orphan"
    )
    pdf_extraction_runs: Mapped[list[PdfExtractionRun]] = relationship(
        back_populates="uploaded_file", cascade="all, delete-orphan"
    )
    ceta_imports: Mapped[list[CetaImport]] = relationship(
        back_populates="uploaded_file", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_uploaded_files_category_uploaded_at", "file_category", "uploaded_at"),
        Index("ix_uploaded_files_checksum_sha256", "checksum_sha256"),
    )


class ProjectFile(IdentifierMixin, Base):
    __tablename__ = "project_files"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    uploaded_file_id: Mapped[str] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="CASCADE")
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="files")
    uploaded_file: Mapped[UploadedFile] = relationship(back_populates="project_links")

    __table_args__ = (
        Index("ix_project_files_project_id_is_primary", "project_id", "is_primary"),
        Index(
            "ix_project_files_project_uploaded_file",
            "project_id",
            "uploaded_file_id",
            unique=True,
        ),
    )


class QuoteVersionFile(IdentifierMixin, Base):
    __tablename__ = "quote_version_files"

    quote_version_id: Mapped[str] = mapped_column(
        ForeignKey("quote_versions.id", ondelete="CASCADE")
    )
    uploaded_file_id: Mapped[str] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="CASCADE")
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    quote_version: Mapped[QuoteVersion] = relationship(back_populates="files")
    uploaded_file: Mapped[UploadedFile] = relationship(back_populates="quote_version_links")

    __table_args__ = (
        Index(
            "ix_quote_version_files_quote_version_uploaded_file",
            "quote_version_id",
            "uploaded_file_id",
            unique=True,
        ),
    )
