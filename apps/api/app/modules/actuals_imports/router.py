from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, require_permissions
from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.errors import ApiProblemException
from app.modules.actuals_imports.schemas import (
    ActualsImportBatchDetailRead,
    ActualsImportBatchListResponse,
    ActualsImportRowListResponse,
    ApproveActualsImportBatchRequest,
    ApproveActualsImportBatchResponse,
    CreateActualsImportBatchRequest,
    ProcessActualsBatchResponse,
    RejectActualsImportBatchRequest,
    RejectActualsImportBatchResponse,
    UpdateActualsImportRowDecisionRequest,
    WorkerActualsImportResultRequest,
)
from app.modules.actuals_imports.service import actuals_import_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
ActualsImportsReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("actuals_imports.read")),
]
ActualsImportsWriteSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("actuals_imports.write")),
]
ActualsImportsApproveSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("actuals_imports.approve")),
]


def require_worker_callback_token(
    worker_token: str | None = Header(default=None, alias="X-Worker-Token"),
) -> None:
    expected = get_settings().worker_callback_token
    if not worker_token or not secrets.compare_digest(worker_token, expected):
        raise ApiProblemException(
            401,
            "Worker callback authentication failed.",
            "Authentication Required",
        )


@router.get("/batches", response_model=ActualsImportBatchListResponse)
def list_actuals_import_batches(
    session: DbSession,
    _subject: ActualsImportsReadSubject,
) -> ActualsImportBatchListResponse:
    return actuals_import_service.list_batches(session)


@router.post("/batches", response_model=ActualsImportBatchDetailRead, status_code=201)
def create_actuals_import_batch(
    payload: CreateActualsImportBatchRequest,
    session: DbSession,
    subject: ActualsImportsWriteSubject,
) -> ActualsImportBatchDetailRead:
    batch = actuals_import_service.create_batch(
        session,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return batch


@router.get("/batches/{batch_id}", response_model=ActualsImportBatchDetailRead)
def get_actuals_import_batch(
    batch_id: str,
    session: DbSession,
    _subject: ActualsImportsReadSubject,
) -> ActualsImportBatchDetailRead:
    return actuals_import_service.get_batch(session, batch_id)


@router.get("/batches/{batch_id}/rows", response_model=ActualsImportRowListResponse)
def list_actuals_import_rows(
    batch_id: str,
    session: DbSession,
    _subject: ActualsImportsReadSubject,
    review_queue: str | None = Query(default=None),
) -> ActualsImportRowListResponse:
    return actuals_import_service.list_rows(session, batch_id, review_queue=review_queue)


@router.post(
    "/batches/{batch_id}/process",
    response_model=ProcessActualsBatchResponse,
    status_code=202,
)
def process_actuals_batch(
    batch_id: str,
    session: DbSession,
    _subject: ActualsImportsWriteSubject,
) -> ProcessActualsBatchResponse:
    job = actuals_import_service.build_process_job(session, batch_id)
    session.commit()
    return ProcessActualsBatchResponse(
        batch_id=batch_id,
        job_id=job.id,
        queue_name=job.queue_name,
        status=job.status,
        traceability_mode="source_row_to_approved_actual",
    )


@router.post("/batches/{batch_id}/worker-result", response_model=ActualsImportBatchDetailRead)
def apply_actuals_import_worker_result(
    batch_id: str,
    payload: WorkerActualsImportResultRequest,
    session: DbSession,
    _worker_auth: Annotated[None, Depends(require_worker_callback_token)],
) -> ActualsImportBatchDetailRead:
    result = actuals_import_service.apply_worker_result(session, batch_id, payload)
    session.commit()
    return result


@router.patch("/rows/{row_id}/decision", response_model=ActualsImportRowListResponse)
def update_actuals_import_row_decision(
    row_id: str,
    payload: UpdateActualsImportRowDecisionRequest,
    session: DbSession,
    subject: ActualsImportsWriteSubject,
) -> ActualsImportRowListResponse:
    row = actuals_import_service.update_row_decision(
        session,
        row_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return ActualsImportRowListResponse(items=[row])


@router.post("/batches/{batch_id}/approve", response_model=ApproveActualsImportBatchResponse)
def approve_actuals_import_batch(
    batch_id: str,
    payload: ApproveActualsImportBatchRequest,
    session: DbSession,
    subject: ActualsImportsApproveSubject,
) -> ApproveActualsImportBatchResponse:
    response = actuals_import_service.approve_batch(
        session,
        batch_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return response


@router.post("/batches/{batch_id}/reject", response_model=RejectActualsImportBatchResponse)
def reject_actuals_import_batch(
    batch_id: str,
    payload: RejectActualsImportBatchRequest,
    session: DbSession,
    subject: ActualsImportsApproveSubject,
) -> RejectActualsImportBatchResponse:
    response = actuals_import_service.reject_batch(
        session,
        batch_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return response
