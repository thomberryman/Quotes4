from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, require_permissions
from app.core.db import get_db_session
from app.modules.predictions.schemas import (
    PredictionOverridesPatchRequest,
    PredictionRunCreateRequest,
    PredictionRunDetailRead,
    PredictionRunListResponse,
    PredictionScenarioPromotionResponse,
    PredictionScenarioPromoteRequest,
    PredictionScenarioUpdateRequest,
    ProjectPredictiveGuidanceResponse,
)
from app.modules.predictions.service import prediction_service
from app.modules.projects.schemas import (
    ProjectActualsVsQuoteRead,
    ProjectContactsReplaceRequest,
    ProjectCreateRequest,
    ProjectDisciplinesReplaceRequest,
    ProjectListResponse,
    ProjectMetadataPutRequest,
    ProjectOutcomeCreateRequest,
    ProjectPartiesReplaceRequest,
    ProjectRead,
    ProjectScheduleRangesReplaceRequest,
    ProjectUpdateRequest,
)
from app.modules.projects.service import projects_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
ProjectsReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("projects.read")),
]
ProjectsWriteSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("projects.write")),
]


@router.get("", response_model=ProjectListResponse)
def list_projects(
    session: DbSession,
    _subject: ProjectsReadSubject,
) -> ProjectListResponse:
    return ProjectListResponse(items=projects_service.list_projects(session))


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(
    payload: ProjectCreateRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> ProjectRead:
    project = projects_service.create_project(session, payload, actor_id=subject.user.id)
    session.commit()
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    session: DbSession,
    _subject: ProjectsReadSubject,
) -> ProjectRead:
    return projects_service.get_project(session, project_id)


@router.get("/{project_id}/actuals-vs-quote", response_model=ProjectActualsVsQuoteRead)
def get_project_actuals_vs_quote(
    project_id: str,
    session: DbSession,
    _subject: ProjectsReadSubject,
) -> ProjectActualsVsQuoteRead:
    return projects_service.get_project_actuals_vs_quote(session, project_id)


@router.get(
    "/{project_id}/predictive-guidance",
    response_model=ProjectPredictiveGuidanceResponse,
)
def get_project_predictive_guidance(
    project_id: str,
    session: DbSession,
    _subject: ProjectsReadSubject,
    quote_version_id: str | None = Query(default=None, alias="quoteVersionId"),
    limit: int = Query(default=25, ge=1, le=25),
    discipline_id: str | None = Query(default=None, alias="disciplineId"),
) -> ProjectPredictiveGuidanceResponse:
    response = ProjectPredictiveGuidanceResponse.model_validate(
        prediction_service.get_project_predictive_guidance(
            session,
            project_id,
            quote_version_id=quote_version_id,
            limit=limit,
            discipline_id=discipline_id,
        )
    )
    session.commit()
    return response


@router.post(
    "/{project_id}/prediction-runs",
    response_model=PredictionRunDetailRead,
    status_code=201,
)
def create_prediction_run(
    project_id: str,
    payload: PredictionRunCreateRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> PredictionRunDetailRead:
    run = prediction_service.create_prediction_run(
        session,
        project_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return run


@router.get("/{project_id}/prediction-runs", response_model=PredictionRunListResponse)
def list_prediction_runs(
    project_id: str,
    session: DbSession,
    _subject: ProjectsReadSubject,
) -> PredictionRunListResponse:
    return prediction_service.list_prediction_runs(session, project_id)


@router.get(
    "/{project_id}/prediction-runs/{run_id}",
    response_model=PredictionRunDetailRead,
)
def get_prediction_run(
    project_id: str,
    run_id: str,
    session: DbSession,
    _subject: ProjectsReadSubject,
) -> PredictionRunDetailRead:
    return prediction_service.get_prediction_run(session, project_id, run_id)


@router.patch(
    "/{project_id}/prediction-runs/{run_id}/overrides",
    response_model=PredictionRunDetailRead,
)
def patch_prediction_overrides(
    project_id: str,
    run_id: str,
    payload: PredictionOverridesPatchRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> PredictionRunDetailRead:
    run = prediction_service.patch_overrides(
        session,
        project_id,
        run_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return run


@router.patch(
    "/{project_id}/prediction-runs/{run_id}/scenarios/{scenario_key}",
    response_model=PredictionRunDetailRead,
)
def update_prediction_scenario(
    project_id: str,
    run_id: str,
    scenario_key: str,
    payload: PredictionScenarioUpdateRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> PredictionRunDetailRead:
    run = prediction_service.update_scenario(
        session,
        project_id,
        run_id,
        scenario_key,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return run


@router.post(
    "/{project_id}/prediction-runs/{run_id}/promote-scenario",
    response_model=PredictionScenarioPromotionResponse,
)
def promote_prediction_scenario(
    project_id: str,
    run_id: str,
    payload: PredictionScenarioPromoteRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> PredictionScenarioPromotionResponse:
    response = prediction_service.promote_scenario(
        session,
        project_id,
        run_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return response


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> ProjectRead:
    project = projects_service.update_project(
        session,
        project_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return project


@router.put("/{project_id}/metadata", response_model=ProjectRead)
def put_project_metadata(
    project_id: str,
    payload: ProjectMetadataPutRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> ProjectRead:
    project = projects_service.put_metadata(session, project_id, payload, actor_id=subject.user.id)
    session.commit()
    return project


@router.put("/{project_id}/parties", response_model=ProjectRead)
def replace_project_parties(
    project_id: str,
    payload: ProjectPartiesReplaceRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> ProjectRead:
    project = projects_service.replace_parties(
        session,
        project_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return project


@router.put("/{project_id}/contacts", response_model=ProjectRead)
def replace_project_contacts(
    project_id: str,
    payload: ProjectContactsReplaceRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> ProjectRead:
    project = projects_service.replace_contacts(
        session,
        project_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return project


@router.put("/{project_id}/disciplines", response_model=ProjectRead)
def replace_project_disciplines(
    project_id: str,
    payload: ProjectDisciplinesReplaceRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> ProjectRead:
    project = projects_service.replace_disciplines(
        session,
        project_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return project


@router.put("/{project_id}/schedule-ranges", response_model=ProjectRead)
def replace_project_schedule_ranges(
    project_id: str,
    payload: ProjectScheduleRangesReplaceRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> ProjectRead:
    project = projects_service.replace_schedule_ranges(
        session,
        project_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return project


@router.post("/{project_id}/outcomes", response_model=ProjectRead, status_code=201)
def create_project_outcome(
    project_id: str,
    payload: ProjectOutcomeCreateRequest,
    session: DbSession,
    subject: ProjectsWriteSubject,
) -> ProjectRead:
    project = projects_service.add_outcome(session, project_id, payload, actor_id=subject.user.id)
    session.commit()
    return project
