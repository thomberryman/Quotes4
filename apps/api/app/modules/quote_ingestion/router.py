from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, require_permissions
from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.errors import ApiProblemException
from app.modules.quote_ingestion.schemas import (
    ApproveQuoteIngestionRunRequest,
    CreateQuoteIngestionRunRequest,
    CreateQuoteIngestionUploadRequest,
    FinalizeQuoteIngestionUploadRequest,
    FinalizeQuoteIngestionUploadResponse,
    QuoteApprovalResponse,
    QuoteIngestionRunDetail,
    QuoteIngestionRunListResponse,
    QuoteIngestionUploadIntentResponse,
    QuoteParsePreviewResponse,
    RejectQuoteIngestionRunRequest,
    RerunQuoteIngestionRunRequest,
    UpdateQuoteIngestionReviewRequest,
    WorkerParseResultRequest,
)
from app.modules.quote_ingestion.service import quote_ingestion_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
QuotesReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("quotes.read")),
]
QuotesWriteSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("quotes.write")),
]
QuotesIssueSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("quotes.issue")),
]
FilesWriteSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("files.write")),
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


@router.post("/uploads/presign", response_model=QuoteIngestionUploadIntentResponse, status_code=201)
def create_quote_ingestion_upload_intent(
    payload: CreateQuoteIngestionUploadRequest,
    session: DbSession,
    subject: FilesWriteSubject,
) -> QuoteIngestionUploadIntentResponse:
    response = quote_ingestion_service.create_upload_intent(
        session,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return response


@router.post("/uploads/finalize", response_model=FinalizeQuoteIngestionUploadResponse)
def finalize_quote_ingestion_upload(
    payload: FinalizeQuoteIngestionUploadRequest,
    session: DbSession,
    subject: FilesWriteSubject,
) -> FinalizeQuoteIngestionUploadResponse:
    response = quote_ingestion_service.finalize_upload(
        session,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return response


@router.get("/runs", response_model=QuoteIngestionRunListResponse)
def list_quote_ingestion_runs(
    session: DbSession,
    _subject: QuotesReadSubject,
) -> QuoteIngestionRunListResponse:
    return quote_ingestion_service.list_runs(session)


@router.post("/runs", response_model=QuoteIngestionRunDetail, status_code=201)
def create_quote_ingestion_run(
    payload: CreateQuoteIngestionRunRequest,
    session: DbSession,
    subject: QuotesWriteSubject,
) -> QuoteIngestionRunDetail:
    run = quote_ingestion_service.create_run(
        session,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return run


@router.get("/runs/{run_id}", response_model=QuoteIngestionRunDetail)
def get_quote_ingestion_run(
    run_id: str,
    session: DbSession,
    _subject: QuotesReadSubject,
) -> QuoteIngestionRunDetail:
    return quote_ingestion_service.get_run(session, run_id)


@router.patch("/runs/{run_id}/review", response_model=QuoteIngestionRunDetail)
def update_quote_ingestion_review(
    run_id: str,
    payload: UpdateQuoteIngestionReviewRequest,
    session: DbSession,
    subject: QuotesWriteSubject,
) -> QuoteIngestionRunDetail:
    run = quote_ingestion_service.update_review(
        session,
        run_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return run


@router.post("/runs/{run_id}/approve", response_model=QuoteApprovalResponse)
def approve_quote_ingestion_run(
    run_id: str,
    payload: ApproveQuoteIngestionRunRequest,
    session: DbSession,
    subject: QuotesIssueSubject,
) -> QuoteApprovalResponse:
    response = quote_ingestion_service.approve_run(
        session,
        run_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return response


@router.post("/runs/{run_id}/rerun", response_model=QuoteIngestionRunDetail, status_code=201)
def rerun_quote_ingestion_run(
    run_id: str,
    payload: RerunQuoteIngestionRunRequest,
    session: DbSession,
    subject: QuotesWriteSubject,
) -> QuoteIngestionRunDetail:
    run = quote_ingestion_service.rerun(
        session,
        run_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return run


@router.post("/runs/{run_id}/reject", response_model=QuoteIngestionRunDetail)
def reject_quote_ingestion_run(
    run_id: str,
    payload: RejectQuoteIngestionRunRequest,
    session: DbSession,
    subject: QuotesWriteSubject,
) -> QuoteIngestionRunDetail:
    run = quote_ingestion_service.reject_run(
        session,
        run_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return run


@router.get("/preview", response_model=QuoteParsePreviewResponse)
def preview_quote_parse(
    object_key: str,
    session: DbSession,
    _subject: QuotesReadSubject,
) -> QuoteParsePreviewResponse:
    return quote_ingestion_service.preview(session, object_key)


@router.post("/runs/{run_id}/worker-result", response_model=QuoteIngestionRunDetail)
def apply_worker_parse_result(
    run_id: str,
    payload: WorkerParseResultRequest,
    session: DbSession,
    _worker_auth: Annotated[None, Depends(require_worker_callback_token)],
) -> QuoteIngestionRunDetail:
    run = quote_ingestion_service.apply_worker_result(session, run_id, payload)
    session.commit()
    return run
