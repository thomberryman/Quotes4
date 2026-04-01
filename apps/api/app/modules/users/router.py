from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, get_current_subject, require_permissions
from app.core.db import get_db_session
from app.core.errors import ApiProblemException
from app.modules.users.schemas import (
    UserCreateRequest,
    UserListResponse,
    UserRead,
    UserRolesUpdateRequest,
    UserUpdateRequest,
)
from app.modules.users.service import users_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
CurrentSubjectDependency = Annotated[CurrentSubject, Depends(get_current_subject)]
UsersReadSubject = Annotated[CurrentSubject, Depends(require_permissions("users.read"))]
UsersWriteSubject = Annotated[CurrentSubject, Depends(require_permissions("users.write"))]
RolesAssignSubject = Annotated[CurrentSubject, Depends(require_permissions("roles.assign"))]


@router.get("/me", response_model=UserRead)
def get_me(
    session: DbSession,
    subject: CurrentSubjectDependency,
) -> UserRead:
    return users_service.get_user(session, subject.user.id)


@router.get("", response_model=UserListResponse)
def list_users(
    session: DbSession,
    _subject: UsersReadSubject,
) -> UserListResponse:
    return UserListResponse(items=users_service.list_users(session))


@router.post("", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreateRequest,
    session: DbSession,
    subject: UsersWriteSubject,
) -> UserRead:
    user = users_service.create_user(session, payload, actor_id=subject.user.id)
    session.commit()
    return user


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: str,
    session: DbSession,
    subject: CurrentSubjectDependency,
) -> UserRead:
    if user_id != subject.user.id and not subject.has_permission("users.read"):
        raise ApiProblemException(
            403,
            "You do not have permission to read that user.",
            "Permission Denied",
        )
    if user_id == subject.user.id and not (
        subject.has_permission("users.read") or subject.has_permission("users.read_self")
    ):
        raise ApiProblemException(
            403,
            "You do not have permission to read your user profile.",
            "Permission Denied",
        )
    return users_service.get_user(session, user_id)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    session: DbSession,
    subject: UsersWriteSubject,
) -> UserRead:
    user = users_service.update_user(session, user_id, payload, actor_id=subject.user.id)
    session.commit()
    return user


@router.put("/{user_id}/roles", response_model=UserRead)
def replace_user_roles(
    user_id: str,
    payload: UserRolesUpdateRequest,
    session: DbSession,
    subject: RolesAssignSubject,
) -> UserRead:
    user = users_service.replace_roles(
        session,
        user_id,
        payload.role_keys,
        actor_id=subject.user.id,
    )
    session.commit()
    return user
