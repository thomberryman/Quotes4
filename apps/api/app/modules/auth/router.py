from __future__ import annotations

from secrets import token_urlsafe
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentSubject,
    get_current_subject,
    require_permissions,
    validate_csrf_request,
)
from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.errors import ApiProblemException
from app.modules.auth.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    InvitationRequest,
    InvitationResponse,
    LoginRequest,
    LogoutResponse,
    RefreshSessionRequest,
    SessionResponse,
    UserSummary,
)
from app.modules.auth.service import auth_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
CurrentSubjectDependency = Annotated[CurrentSubject, Depends(get_current_subject)]
RolesAssignSubject = Annotated[CurrentSubject, Depends(require_permissions("roles.assign"))]


def _set_access_cookie(response: Response, access_token: str, *, max_age_seconds: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_access_cookie_name,
        value=access_token,
        httponly=True,
        secure=settings.use_secure_cookies,
        samesite="lax",
        max_age=max_age_seconds,
        path="/",
    )


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.use_secure_cookies,
        samesite="lax",
        max_age=settings.auth_refresh_token_ttl_days * 24 * 60 * 60,
        path=f"{settings.api_base_path}/auth",
    )


def _set_csrf_cookie(response: Response, csrf_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.use_secure_cookies,
        samesite="lax",
        max_age=settings.auth_refresh_token_ttl_days * 24 * 60 * 60,
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.auth_access_cookie_name, path="/")
    response.delete_cookie(
        settings.auth_refresh_cookie_name,
        path=f"{settings.api_base_path}/auth",
    )
    response.delete_cookie(settings.auth_csrf_cookie_name, path="/")


def _set_session_cookies(
    response: Response,
    auth_session: SessionResponse,
    *,
    csrf_token: str,
) -> None:
    settings = get_settings()
    max_age_seconds = settings.auth_access_token_ttl_minutes * 60
    _set_access_cookie(response, auth_session.access_token, max_age_seconds=max_age_seconds)
    _set_refresh_cookie(response, auth_session.refresh_token)
    _set_csrf_cookie(response, csrf_token)
    response.headers["Cache-Control"] = "no-store"


@router.post("/invitations", response_model=InvitationResponse, status_code=201)
def create_invitation(
    payload: InvitationRequest,
    session: DbSession,
    subject: RolesAssignSubject,
) -> InvitationResponse:
    invitation = auth_service.create_invitation(
        session,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return invitation


@router.post("/invitations/accept", response_model=AcceptInvitationResponse)
def accept_invitation(
    payload: AcceptInvitationRequest,
    session: DbSession,
) -> AcceptInvitationResponse:
    accepted = auth_service.accept_invitation(session, payload)
    session.commit()
    return accepted


@router.post("/session", response_model=SessionResponse)
def create_session(
    payload: LoginRequest,
    response: Response,
    session: DbSession,
) -> SessionResponse:
    auth_session = auth_service.login(session, payload)
    session.commit()
    _set_session_cookies(response, auth_session, csrf_token=token_urlsafe(32))
    return auth_session


@router.post("/session/refresh", response_model=SessionResponse)
def refresh_session(
    payload: RefreshSessionRequest,
    request: Request,
    response: Response,
    session: DbSession,
) -> SessionResponse:
    settings = get_settings()
    cookie_refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
    cookie_csrf_token = request.cookies.get(settings.auth_csrf_cookie_name)
    refresh_token = payload.refresh_token or cookie_refresh_token
    if refresh_token is None:
        raise ApiProblemException(401, "Refresh token is missing.", "Authentication Required")
    if payload.refresh_token is None and cookie_refresh_token is not None:
        validate_csrf_request(request, cookie_csrf_token)

    auth_session = auth_service.refresh(session, refresh_token)
    session.commit()
    _set_session_cookies(response, auth_session, csrf_token=token_urlsafe(32))
    return auth_session


@router.delete("/session", response_model=LogoutResponse)
def destroy_session(
    request: Request,
    response: Response,
    session: DbSession,
) -> LogoutResponse:
    settings = get_settings()
    cookie_refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
    cookie_csrf_token = request.cookies.get(settings.auth_csrf_cookie_name)
    if cookie_refresh_token is not None:
        validate_csrf_request(request, cookie_csrf_token)
    auth_service.logout(session, cookie_refresh_token)
    session.commit()
    _clear_session_cookies(response)
    response.headers["Cache-Control"] = "no-store"
    return LogoutResponse(message="Session cleared.")


@router.get("/me", response_model=UserSummary)
def get_current_user(subject: CurrentSubjectDependency) -> UserSummary:
    return auth_service.current_user(subject)
