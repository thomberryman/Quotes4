from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import build_current_subject, get_user_with_access
from app.core.datetimes import same_timestamp
from app.core.errors import ApiProblemException
from app.core.normalization import normalize_email
from app.models import User
from app.modules.audit.service import audit_service
from app.modules.auth.service import auth_service
from app.modules.users.schemas import UserCreateRequest, UserRead, UserUpdateRequest


class UsersService:
    def list_users(self, session: Session) -> list[UserRead]:
        statement = select(User).order_by(User.last_name, User.first_name)
        users = list(session.scalars(statement))
        return [self._serialize(session, user) for user in users]

    def get_user(self, session: Session, user_id: str) -> UserRead:
        user = get_user_with_access(session, user_id)
        if user is None:
            raise ApiProblemException(404, f"User '{user_id}' was not found.", "User Not Found")
        return self._serialize_from_loaded_user(user)

    def create_user(
        self,
        session: Session,
        payload: UserCreateRequest,
        *,
        actor_id: str,
    ) -> UserRead:
        normalized_email = normalize_email(str(payload.email))
        existing = session.scalar(select(User).where(User.normalized_email == normalized_email))
        if existing is not None:
            raise ApiProblemException(409, "A user with that email already exists.", "User Exists")

        now = datetime.now(UTC)
        user = User(
            email=normalized_email,
            normalized_email=normalized_email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            display_name=payload.display_name,
            job_title=payload.job_title,
            is_active=payload.is_active,
            invited_at=now,
        )
        session.add(user)
        session.flush()
        auth_service.replace_user_roles(
            session,
            user=user,
            role_keys=payload.role_keys,
            assigned_by_id=actor_id,
        )
        loaded = get_user_with_access(session, user.id) or user
        audit_service.record(
            session,
            action="user.created",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            summary=f"Created user {user.email}.",
            after={"email": user.email, "roleKeys": payload.role_keys},
        )
        return self._serialize_from_loaded_user(loaded)

    def update_user(
        self,
        session: Session,
        user_id: str,
        payload: UserUpdateRequest,
        *,
        actor_id: str,
    ) -> UserRead:
        user = session.get(User, user_id)
        if user is None:
            raise ApiProblemException(404, f"User '{user_id}' was not found.", "User Not Found")
        self._assert_current(user.updated_at, payload.expected_updated_at)
        before = self._snapshot_basic_fields(user)
        if payload.first_name is not None:
            user.first_name = payload.first_name
        if payload.last_name is not None:
            user.last_name = payload.last_name
        if payload.display_name is not None:
            user.display_name = payload.display_name
        if payload.job_title is not None:
            user.job_title = payload.job_title
        if payload.is_active is not None:
            user.is_active = payload.is_active
        session.flush()
        loaded = get_user_with_access(session, user.id) or user
        audit_service.record(
            session,
            action="user.updated",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            summary=f"Updated user {user.email}.",
            before=before,
            after=self._snapshot_basic_fields(user),
        )
        return self._serialize_from_loaded_user(loaded)

    def replace_roles(
        self,
        session: Session,
        user_id: str,
        role_keys: list[str],
        *,
        actor_id: str,
    ) -> UserRead:
        user = session.get(User, user_id)
        if user is None:
            raise ApiProblemException(404, f"User '{user_id}' was not found.", "User Not Found")
        before = self._serialize(session, user).role_keys
        auth_service.replace_user_roles(
            session,
            user=user,
            role_keys=role_keys,
            assigned_by_id=actor_id,
        )
        loaded = get_user_with_access(session, user.id) or user
        after = self._serialize_from_loaded_user(loaded)
        audit_service.record(
            session,
            action="user.roles.replaced",
            entity_type="user",
            entity_id=user.id,
            actor_id=actor_id,
            summary=f"Replaced roles for {user.email}.",
            before={"roleKeys": before},
            after={"roleKeys": after.role_keys},
        )
        return after

    def _serialize(self, session: Session, user: User) -> UserRead:
        loaded = get_user_with_access(session, user.id)
        if loaded is None:
            raise ApiProblemException(404, f"User '{user.id}' was not found.", "User Not Found")
        return self._serialize_from_loaded_user(loaded)

    def _serialize_from_loaded_user(self, user: User) -> UserRead:
        subject = build_current_subject(user)
        return UserRead(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            display_name=user.display_name,
            job_title=user.job_title,
            is_active=user.is_active,
            role_keys=list(subject.role_keys),
            invited_at=user.invited_at,
            accepted_at=user.accepted_at,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    def _snapshot_basic_fields(self, user: User) -> dict[str, object]:
        return {
            "firstName": user.first_name,
            "lastName": user.last_name,
            "displayName": user.display_name,
            "jobTitle": user.job_title,
            "isActive": user.is_active,
        }

    def _assert_current(self, current: datetime, expected: datetime) -> None:
        if not same_timestamp(current, expected):
            raise ApiProblemException(
                409,
                "The user was modified by another request. Reload and retry.",
                "Stale Update",
            )


users_service = UsersService()
