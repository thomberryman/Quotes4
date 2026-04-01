from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentifierMixin, JsonObjectType

if TYPE_CHECKING:
    from app.models.projects import Project


class AuditLog(IdentifierMixin, Base):
    __tablename__ = "audit_logs"

    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    before_json: Mapped[dict[str, object] | None] = mapped_column(
        JsonObjectType, nullable=True
    )
    after_json: Mapped[dict[str, object] | None] = mapped_column(
        JsonObjectType, nullable=True
    )
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JsonObjectType, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project | None] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_entity_created_at", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_logs_project_created_at", "project_id", "created_at"),
        Index("ix_audit_logs_actor_created_at", "actor_id", "created_at"),
    )
