from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, require_permissions
from app.core.db import get_db_session
from app.modules.comparables.schemas import (
    ComparableSelectionUpdateRequest,
    ComparableSelectionUpdateResponse,
    ProjectComparablesResponse,
    ProjectRecommendationsResponse,
)
from app.modules.comparables.service import comparable_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
ComparablesReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("projects.read")),
]
ComparablesWriteSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("projects.write")),
]


@router.get(
    "/{project_id}/comparables",
    response_model=ProjectComparablesResponse,
)
def get_project_comparables(
    project_id: str,
    session: DbSession,
    _subject: ComparablesReadSubject,
    quote_version_id: str | None = Query(default=None, alias="quoteVersionId"),
    limit: int = Query(default=10, ge=1, le=25),
    discipline_id: str | None = Query(default=None, alias="disciplineId"),
    include_pinned: bool = Query(default=True, alias="includePinned"),
) -> ProjectComparablesResponse:
    return ProjectComparablesResponse.model_validate(
        comparable_service.get_comparables(
            session,
            project_id,
            quote_version_id=quote_version_id,
            limit=limit,
            discipline_id=discipline_id,
            include_pinned=include_pinned,
        )
    )


@router.get(
    "/{project_id}/recommendations",
    response_model=ProjectRecommendationsResponse,
)
def get_project_recommendations(
    project_id: str,
    session: DbSession,
    _subject: ComparablesReadSubject,
    quote_version_id: str | None = Query(default=None, alias="quoteVersionId"),
    limit: int = Query(default=10, ge=1, le=25),
    discipline_id: str | None = Query(default=None, alias="disciplineId"),
) -> ProjectRecommendationsResponse:
    return ProjectRecommendationsResponse.model_validate(
        comparable_service.get_recommendations(
            session,
            project_id,
            quote_version_id=quote_version_id,
            limit=limit,
            discipline_id=discipline_id,
        )
    )


@router.put(
    "/{project_id}/comparable-selection",
    response_model=ComparableSelectionUpdateResponse,
    status_code=status.HTTP_200_OK,
)
def update_project_comparable_selection(
    project_id: str,
    payload: ComparableSelectionUpdateRequest,
    session: DbSession,
    subject: ComparablesWriteSubject,
) -> ComparableSelectionUpdateResponse:
    response = ComparableSelectionUpdateResponse.model_validate(
        comparable_service.update_selection(
            session,
            project_id,
            pinned_project_ids=payload.pinned_project_ids,
            excluded_project_ids=payload.excluded_project_ids,
            note=payload.note,
            actor_id=subject.user.id,
        )
    )
    session.commit()
    return response
