from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_role_permission_map, require_permissions
from app.core.db import get_db_session
from app.core.schemas import BaseSchema
from app.models import Permission

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
RolesAssignSubject = Annotated[object, Depends(require_permissions("roles.assign"))]


class RoleSummary(BaseSchema):
    key: str
    permission_keys: list[str]


class PermissionSummary(BaseSchema):
    key: str
    label: str
    description: str | None = None


class RoleListResponse(BaseSchema):
    items: list[RoleSummary]


class PermissionListResponse(BaseSchema):
    items: list[PermissionSummary]


@router.get("/roles", response_model=RoleListResponse)
def list_roles(
    session: DbSession,
    _subject: RolesAssignSubject,
) -> RoleListResponse:
    role_map = get_role_permission_map(session)
    items = [
        RoleSummary(key=key, permission_keys=value)
        for key, value in sorted(role_map.items(), key=lambda item: item[0])
    ]
    return RoleListResponse(items=items)


@router.get("/permissions", response_model=PermissionListResponse)
def list_permissions(
    session: DbSession,
    _subject: RolesAssignSubject,
) -> PermissionListResponse:
    permissions = list(session.scalars(select(Permission).order_by(Permission.key)))
    items = [
        PermissionSummary(
            key=permission.key,
            label=permission.label,
            description=permission.description,
        )
        for permission in permissions
    ]
    return PermissionListResponse(items=items)
