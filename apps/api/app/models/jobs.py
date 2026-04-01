from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentifierMixin, JsonObjectType, TimestampMixin
from app.models.enums import BackgroundJobStatus


class BackgroundJob(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "background_jobs"

    queue_name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[BackgroundJobStatus] = mapped_column(
        SqlEnum(BackgroundJobStatus, name="background_job_status", native_enum=False, length=32),
        default=BackgroundJobStatus.queued,
        index=True,
    )
    deduplication_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(JsonObjectType)
    related_entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer(), default=0)
    max_attempts: Mapped[int] = mapped_column(Integer(), default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)

    __table_args__ = (
        Index(
            "ix_background_jobs_queue_status_available_at",
            "queue_name",
            "status",
            "available_at",
        ),
        Index(
            "uq_background_jobs_active_deduplication_key",
            "deduplication_key",
            unique=True,
            sqlite_where=text(
                "deduplication_key IS NOT NULL AND status IN ('queued', 'running')"
            ),
            postgresql_where=text(
                "deduplication_key IS NOT NULL AND status IN ('queued', 'running')"
            ),
        ),
    )
