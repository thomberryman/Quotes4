from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, require_permissions
from app.core.db import get_db_session
from app.core.errors import ApiProblemException
from app.core.schemas import BaseSchema
from app.models.enums import BackgroundJobStatus
from app.modules.jobs.service import JobListFilters, JobListSummary, JobRecord, job_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
JobsReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("jobs.read")),
]
StatusQuery = Annotated[BackgroundJobStatus | None, Query()]
QueueNameQuery = Annotated[str | None, Query(alias="queueName")]
RelatedEntityTypeQuery = Annotated[str | None, Query(alias="relatedEntityType")]
RelatedEntityIdQuery = Annotated[str | None, Query(alias="relatedEntityId")]
LimitQuery = Annotated[int, Query(ge=1, le=500)]


class JobListResponse(BaseSchema):
    items: list[JobRecord]
    summary: JobListSummary


@router.get("", response_model=JobListResponse)
def list_jobs(
    session: DbSession,
    _subject: JobsReadSubject,
    status: StatusQuery = None,
    queue_name: QueueNameQuery = None,
    related_entity_type: RelatedEntityTypeQuery = None,
    related_entity_id: RelatedEntityIdQuery = None,
    limit: LimitQuery = 100,
) -> JobListResponse:
    filters = JobListFilters(
        status=status,
        queue_name=queue_name,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    return JobListResponse(
        items=job_service.list(session, filters=filters, limit=limit),
        summary=job_service.summarize(session, filters=filters),
    )


@router.get("/{job_id}", response_model=JobRecord)
def get_job(
    job_id: str,
    session: DbSession,
    _subject: JobsReadSubject,
) -> JobRecord:
    job = job_service.get(session, job_id)
    if job is None:
        raise ApiProblemException(404, f"Job '{job_id}' was not found.", title="Job Not Found")
    return job
