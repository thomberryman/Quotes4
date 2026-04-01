from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.modules.audit.schemas import AuditEventSummary


class AuditService:
    def record(
        self,
        session: Session,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        actor_id: str | None = None,
        project_id: str | None = None,
        summary: str | None = None,
        before: dict[str, object] | None = None,
        after: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditLog:
        event = AuditLog(
            actor_id=actor_id,
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            summary=summary,
            before_json=before,
            after_json=after,
            metadata_json=metadata,
            created_at=datetime.now(UTC),
        )
        session.add(event)
        session.flush()
        return event

    def list_events(
        self,
        session: Session,
        *,
        project_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEventSummary]:
        statement: Select[tuple[AuditLog, str | None]] = (
            select(AuditLog, User.email)
            .outerjoin(User, User.id == AuditLog.actor_id)
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
        if project_id is not None:
            statement = statement.where(AuditLog.project_id == project_id)
        if entity_type is not None:
            statement = statement.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            statement = statement.where(AuditLog.entity_id == entity_id)

        rows: Sequence[tuple[AuditLog, str | None]] = session.execute(statement).all()
        return [self._to_summary(event, actor_email) for event, actor_email in rows]

    def _to_summary(self, event: AuditLog, actor_email: str | None) -> AuditEventSummary:
        return AuditEventSummary(
            id=event.id,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor_id=event.actor_id,
            actor_email=actor_email,
            project_id=event.project_id,
            created_at=event.created_at,
            summary=event.summary,
            before=event.before_json,
            after=event.after_json,
            metadata=event.metadata_json,
        )


audit_service = AuditService()
