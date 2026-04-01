from __future__ import annotations

from dataclasses import dataclass
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.errors import ApiProblemException
from app.core.security import decode_access_token
from app.models import Permission, Role, RolePermission, User, UserRoleAssignment

bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
DbSession = Annotated[Session, Depends(get_db_session)]
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


@dataclass(frozen=True)
class CurrentSubject:
    user: User
    role_keys: list[str]
    permissions: frozenset[str]

    def has_permission(self, permission_key: str) -> bool:
        return permission_key in self.permissions


_USER_ACCESS_OPTIONS = (
    selectinload(User.role_assignments)
    .selectinload(UserRoleAssignment.role)
    .selectinload(Role.permission_links)
    .selectinload(RolePermission.permission),
)


def get_user_with_access(session: Session, user_id: str) -> User | None:
    statement = select(User).options(*_USER_ACCESS_OPTIONS).where(User.id == user_id)
    return session.scalar(statement)


def build_current_subject(user: User) -> CurrentSubject:
    role_keys = sorted(
        {
            assignment.role.key
            for assignment in user.role_assignments
            if assignment.role is not None
        }
    )
    permissions = frozenset(
        permission.key
        for assignment in user.role_assignments
        if assignment.role
        for link in assignment.role.permission_links
        if link.permission
        for permission in [link.permission]
    )
    return CurrentSubject(user=user, role_keys=role_keys, permissions=permissions)


def validate_csrf_request(request: Request, csrf_cookie_token: str | None) -> None:
    if request.method.upper() in SAFE_HTTP_METHODS:
        return

    csrf_header_token = request.headers.get(CSRF_HEADER_NAME)
    if not csrf_cookie_token or not csrf_header_token:
        raise ApiProblemException(
            403,
            "A valid CSRF token is required for this request.",
            "CSRF Validation Failed",
        )
    if not compare_digest(csrf_cookie_token, csrf_header_token):
        raise ApiProblemException(
            403,
            "The CSRF token is invalid.",
            "CSRF Validation Failed",
        )


def get_current_subject(
    credentials: BearerCredentials,
    session: DbSession,
    request: Request,
) -> CurrentSubject:
    settings = get_settings()
    cookie_access_token = request.cookies.get(settings.auth_access_cookie_name)
    cookie_csrf_token = request.cookies.get(settings.auth_csrf_cookie_name)
    token = None
    using_cookie_auth = False
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif cookie_access_token:
        token = cookie_access_token
        using_cookie_auth = True

    if token is None:
        raise ApiProblemException(401, "Authentication is required.", "Authentication Required")

    if using_cookie_auth:
        validate_csrf_request(request, cookie_csrf_token)

    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise ApiProblemException(401, str(exc), "Authentication Required") from exc

    user = get_user_with_access(session, str(payload["sub"]))
    if user is None:
        raise ApiProblemException(
            401,
            "Authenticated user was not found.",
            "Authentication Required",
        )
    if not user.is_active:
        raise ApiProblemException(403, "User account is inactive.", "Inactive User")

    return build_current_subject(user)


def require_permissions(*permission_keys: str):
    required = tuple(permission_keys)

    def dependency(
        subject: Annotated[CurrentSubject, Depends(get_current_subject)],
    ) -> CurrentSubject:
        missing = [permission for permission in required if permission not in subject.permissions]
        if missing:
            raise ApiProblemException(
                403,
                f"Missing required permissions: {', '.join(missing)}.",
                "Permission Denied",
            )
        return subject

    return dependency


def get_role_permission_map(session: Session) -> dict[str, list[str]]:
    statement = (
        select(Role.key, Permission.key)
        .select_from(Role)
        .join(RolePermission, RolePermission.role_id == Role.id, isouter=True)
        .join(Permission, Permission.id == RolePermission.permission_id, isouter=True)
        .order_by(Role.key, Permission.key)
    )
    role_permissions: dict[str, list[str]] = {}
    for role_key, permission_key in session.execute(statement):
        role_permissions.setdefault(str(role_key), [])
        if permission_key is not None:
            role_permissions[str(role_key)].append(str(permission_key))
    return role_permissions
