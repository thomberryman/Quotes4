from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import require_permissions
from app.core.db import get_db_session
from app.modules.audit.schemas import AuditEventListResponse
from app.modules.audit.service import audit_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
AuditReadSubject = Annotated[object, Depends(require_permissions("audit.read"))]


@router.get("/events", response_model=AuditEventListResponse)
def list_audit_events(
    session: DbSession,
    _subject: AuditReadSubject,
    project_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> AuditEventListResponse:
    return AuditEventListResponse(
        items=audit_service.list_events(
            session,
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )
    )
