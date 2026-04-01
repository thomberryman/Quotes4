from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, require_permissions
from app.core.db import get_db_session
from app.modules.quotes.schemas import (
    QuoteCreateRequest,
    QuoteListResponse,
    QuoteRead,
    QuoteUpdateRequest,
    QuoteVersionCreateRequest,
    QuoteVersionRead,
    QuoteVersionSummary,
    QuoteVersionUpdateRequest,
)
from app.modules.quotes.service import quotes_service

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


@router.get("", response_model=QuoteListResponse)
def list_quotes(
    session: DbSession,
    _subject: QuotesReadSubject,
    project_id: str | None = Query(default=None, alias="projectId"),
) -> QuoteListResponse:
    return QuoteListResponse(items=quotes_service.list_quotes(session, project_id=project_id))


@router.post("", response_model=QuoteRead, status_code=201)
def create_quote(
    payload: QuoteCreateRequest,
    session: DbSession,
    subject: QuotesWriteSubject,
) -> QuoteRead:
    quote = quotes_service.create_quote(session, payload, actor_id=subject.user.id)
    session.commit()
    return quote


@router.get("/{quote_id}", response_model=QuoteRead)
def get_quote(
    quote_id: str,
    session: DbSession,
    _subject: QuotesReadSubject,
) -> QuoteRead:
    return quotes_service.get_quote(session, quote_id)


@router.patch("/{quote_id}", response_model=QuoteRead)
def update_quote(
    quote_id: str,
    payload: QuoteUpdateRequest,
    session: DbSession,
    subject: QuotesWriteSubject,
) -> QuoteRead:
    quote = quotes_service.update_quote(
        session,
        quote_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return quote


@router.get("/{quote_id}/versions", response_model=list[QuoteVersionSummary])
def list_quote_versions(
    quote_id: str,
    session: DbSession,
    _subject: QuotesReadSubject,
) -> list[QuoteVersionSummary]:
    return quotes_service.list_versions(session, quote_id)


@router.post("/{quote_id}/versions", response_model=QuoteVersionRead, status_code=201)
def create_quote_version(
    quote_id: str,
    payload: QuoteVersionCreateRequest,
    session: DbSession,
    subject: QuotesWriteSubject,
) -> QuoteVersionRead:
    version = quotes_service.create_version(
        session,
        quote_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return version


@router.get("/versions/{version_id}", response_model=QuoteVersionRead)
def get_quote_version(
    version_id: str,
    session: DbSession,
    _subject: QuotesReadSubject,
) -> QuoteVersionRead:
    return quotes_service.get_version(session, version_id)


@router.patch("/versions/{version_id}", response_model=QuoteVersionRead)
def update_quote_version(
    version_id: str,
    payload: QuoteVersionUpdateRequest,
    session: DbSession,
    subject: QuotesWriteSubject,
) -> QuoteVersionRead:
    version = quotes_service.update_version(
        session,
        version_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return version


@router.post("/versions/{version_id}/issue", response_model=QuoteVersionRead)
def issue_quote_version(
    version_id: str,
    session: DbSession,
    subject: QuotesIssueSubject,
) -> QuoteVersionRead:
    version = quotes_service.issue_version(
        session,
        version_id,
        actor_id=subject.user.id,
    )
    session.commit()
    return version
