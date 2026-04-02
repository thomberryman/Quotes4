from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, require_permissions
from app.core.db import get_db_session
from app.modules.forecasts.schemas import (
    ForecastAccuracySummaryRead,
    ForecastDetailRead,
    ForecastPhasingDraftRead,
    ForecastPhasingDraftUpsertRequest,
    ForecastLineAllocationsReplaceRequest,
    ForecastPhasingPreviewRead,
    ForecastPhasingPreviewRequest,
    ForecastPhasingRowUpdateRequest,
    ForecastPhasingWorkspaceRead,
    ForecastPolicySummary,
    ForecastRecalculateResponse,
    ForecastVersionCreateRequest,
    ForecastVersionRead,
    ForecastVersionUpdateRequest,
)
from app.modules.forecasts.service import forecast_service
from app.modules.jobs.service import job_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
ForecastsReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("forecasts.read")),
]
ForecastsWriteSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("forecasts.write")),
]
ForecastsLockSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("forecasts.lock")),
]


@router.get("/policy", response_model=ForecastPolicySummary)
def get_forecast_policy(
    session: DbSession,
    _subject: ForecastsReadSubject,
) -> ForecastPolicySummary:
    return forecast_service.get_policy(session)


@router.get("/accuracy", response_model=ForecastAccuracySummaryRead)
def get_forecast_accuracy_summary(
    session: DbSession,
    _subject: ForecastsReadSubject,
) -> ForecastAccuracySummaryRead:
    return forecast_service.get_accuracy_summary(session)


@router.get("/projects/{project_id}", response_model=ForecastDetailRead)
def get_project_forecast(
    project_id: str,
    session: DbSession,
    _subject: ForecastsReadSubject,
) -> ForecastDetailRead:
    forecast = forecast_service.get_project_forecast(session, project_id)
    session.commit()
    return forecast


@router.get("/phasing-workspace", response_model=ForecastPhasingWorkspaceRead)
def get_forecast_phasing_workspace(
    session: DbSession,
    _subject: ForecastsReadSubject,
    from_month: str | None = Query(default=None, alias="fromMonth"),
    to_month: str | None = Query(default=None, alias="toMonth"),
    client_id: str | None = Query(default=None, alias="clientId"),
    project_id: str | None = Query(default=None, alias="projectId"),
    discipline_id: str | None = Query(default=None, alias="disciplineId"),
    status: str | None = Query(default=None),
    scenario_key: str | None = Query(default=None, alias="scenarioKey"),
    row_mode: str = Query(default="project", alias="rowMode"),
) -> ForecastPhasingWorkspaceRead:
    return forecast_service.get_phasing_workspace(
        session,
        from_month=from_month,
        to_month=to_month,
        client_id=client_id,
        project_id=project_id,
        discipline_id=discipline_id,
        status=status,
        scenario_key=scenario_key,
        row_mode=row_mode,
    )


@router.post("/phasing-workspace/preview", response_model=ForecastPhasingPreviewRead)
def preview_forecast_phasing_action(
    payload: ForecastPhasingPreviewRequest,
    session: DbSession,
    _subject: ForecastsReadSubject,
) -> ForecastPhasingPreviewRead:
    return forecast_service.preview_phasing_action(session, payload)


@router.put("/projects/{project_id}/phasing-draft", response_model=ForecastPhasingDraftRead)
def update_project_forecast_phasing_draft(
    project_id: str,
    payload: ForecastPhasingDraftUpsertRequest,
    session: DbSession,
    subject: ForecastsWriteSubject,
) -> ForecastPhasingDraftRead:
    draft = forecast_service.upsert_phasing_draft(
        session,
        project_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return draft


@router.delete("/projects/{project_id}/phasing-draft", response_model=ForecastPhasingWorkspaceRead)
def discard_project_forecast_phasing_draft(
    project_id: str,
    session: DbSession,
    subject: ForecastsWriteSubject,
    forecast_version_id: str | None = Query(default=None, alias="forecastVersionId"),
    row_mode: str = Query(alias="rowMode"),
    discipline_id: str | None = Query(default=None, alias="disciplineId"),
) -> ForecastPhasingWorkspaceRead:
    workspace = forecast_service.discard_phasing_draft(
        session,
        project_id,
        forecast_version_id=forecast_version_id,
        row_mode=row_mode,
        discipline_id=discipline_id,
        actor_id=subject.user.id,
    )
    session.commit()
    return workspace


@router.post("/projects/{project_id}/versions", response_model=ForecastVersionRead, status_code=201)
def create_or_clone_forecast_version(
    project_id: str,
    payload: ForecastVersionCreateRequest,
    session: DbSession,
    subject: ForecastsWriteSubject,
) -> ForecastVersionRead:
    version = forecast_service.create_or_clone_version(
        session,
        project_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return version


@router.put("/projects/{project_id}/phasing", response_model=ForecastPhasingWorkspaceRead)
def update_project_forecast_phasing(
    project_id: str,
    payload: ForecastPhasingRowUpdateRequest,
    session: DbSession,
    subject: ForecastsWriteSubject,
) -> ForecastPhasingWorkspaceRead:
    workspace = forecast_service.update_phasing_row(
        session,
        project_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return workspace


@router.get("/versions/{version_id}", response_model=ForecastVersionRead)
def get_forecast_version(
    version_id: str,
    session: DbSession,
    _subject: ForecastsReadSubject,
) -> ForecastVersionRead:
    return forecast_service.get_version(session, version_id)


@router.patch("/versions/{version_id}", response_model=ForecastVersionRead)
def update_forecast_version(
    version_id: str,
    payload: ForecastVersionUpdateRequest,
    session: DbSession,
    subject: ForecastsWriteSubject,
) -> ForecastVersionRead:
    version = forecast_service.update_version(
        session,
        version_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return version


@router.put("/lines/{line_id}/allocations", response_model=ForecastVersionRead)
def replace_forecast_line_allocations(
    line_id: str,
    payload: ForecastLineAllocationsReplaceRequest,
    session: DbSession,
    subject: ForecastsWriteSubject,
) -> ForecastVersionRead:
    version = forecast_service.replace_line_allocations(
        session,
        line_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return version


@router.post("/versions/{version_id}/submit", response_model=ForecastVersionRead)
def submit_forecast_version(
    version_id: str,
    session: DbSession,
    subject: ForecastsLockSubject,
) -> ForecastVersionRead:
    version = forecast_service.submit_version(
        session,
        version_id,
        actor_id=subject.user.id,
    )
    session.commit()
    return version


@router.post("/versions/{version_id}/lock", response_model=ForecastVersionRead)
def lock_forecast_version(
    version_id: str,
    session: DbSession,
    subject: ForecastsLockSubject,
) -> ForecastVersionRead:
    version = forecast_service.lock_version(
        session,
        version_id,
        actor_id=subject.user.id,
    )
    session.commit()
    return version


@router.post(
    "/projects/{project_id}/recalculate",
    response_model=ForecastRecalculateResponse,
    status_code=202,
)
def recalculate_forecast(
    project_id: str,
    session: DbSession,
    subject: ForecastsWriteSubject,
) -> ForecastRecalculateResponse:
    recalculated_version, message = forecast_service.recalculate_project(
        session,
        project_id,
        actor_id=subject.user.id,
    )
    forecast_service.record_recalculation_request(
        session,
        project_id,
        actor_id=subject.user.id,
    )
    job = job_service.enqueue(
        session,
        queue_name="forecast_recalc",
        payload={"projectId": project_id},
        related_entity_type="project",
        related_entity_id=project_id,
        deduplication_key=job_service.build_deduplication_key(
            queue_name="forecast_recalc",
            related_entity_type="project",
            related_entity_id=project_id,
        ),
    )
    session.commit()
    return ForecastRecalculateResponse(
        project_id=project_id,
        job_id=job.id,
        queue_name=job.queue_name,
        status=job.status,
        forecast_version_id=recalculated_version.id if recalculated_version is not None else None,
        message=message,
    )
