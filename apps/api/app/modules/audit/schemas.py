from __future__ import annotations

from datetime import datetime

from app.core.schemas import BaseSchema


class AuditEventSummary(BaseSchema):
    id: str
    action: str
    entity_type: str
    entity_id: str
    actor_id: str | None = None
    actor_email: str | None = None
    project_id: str | None = None
    created_at: datetime
    summary: str | None = None
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    metadata: dict[str, object] | None = None


class AuditEventListResponse(BaseSchema):
    items: list[AuditEventSummary]
