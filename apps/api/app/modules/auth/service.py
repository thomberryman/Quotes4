from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, build_current_subject, get_user_with_access
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.errors import ApiProblemException
from app.core.normalization import normalize_email
from app.core.security import (
    build_password_hasher,
    create_access_token,
    create_refresh_token,
    hash_token,
)
from app.integrations.email import OutboundEmail, mailer
from app.models import AuthInvitation, RefreshSession, Role, User, UserRoleAssignment
from app.models.enums import AuthInvitationStatus
from app.modules.audit.service import audit_service
from app.modules.auth.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    InvitationRequest,
    InvitationResponse,
    LoginRequest,
    SessionResponse,
    UserSummary,
)

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self) -> None:
        self._password_hasher = build_password_hasher()

    def _utc_now(self) -> datetime:
        return datetime.now(UTC)

    def _coerce_utc(self, value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value
        return value.replace(tzinfo=UTC)

    def create_invitation(
        self,
        session: Session,
        payload: InvitationRequest,
        *,
        actor_id: str | None,
    ) -> InvitationResponse:
        normalized_email = normalize_email(str(payload.email))
        existing_user = session.scalar(
            select(User).where(User.normalized_email == normalized_email)
        )
        if existing_user is not None and existing_user.accepted_at is not None:
            raise ApiProblemException(409, "A user with that email already exists.", "User Exists")

        roles = self._get_roles(session, payload.role_keys)
        now = self._utc_now()
        raw_token = create_refresh_token()
        invitation = AuthInvitation(
            email=normalized_email,
            normalized_email=normalized_email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            token_hash=hash_token(raw_token),
            role_keys_json=[role.key for role in roles],
            status=AuthInvitationStatus.pending,
            expires_at=now + timedelta(days=7),
            created_by_id=actor_id,
            created_at=now,
        )
        session.add(invitation)
        session.flush()

        audit_service.record(
            session,
            action="auth.invitation.created",
            entity_type="auth_invitation",
            entity_id=invitation.id,
            actor_id=actor_id,
            summary=f"Created invitation for {normalized_email}.",
            after={"email": normalized_email, "roleKeys": invitation.role_keys_json},
        )

        mailer.send(
            OutboundEmail(
                to_address=normalized_email,
                subject="You have been invited to Quotes4",
                body="Use your invitation token to create your Quotes4 account.",
            )
        )

        return InvitationResponse(
            invitation_id=invitation.id,
            email=normalized_email,
            invite_token=raw_token,
            expires_at=invitation.expires_at,
            role_keys=list(invitation.role_keys_json),
        )

    def accept_invitation(
        self, session: Session, payload: AcceptInvitationRequest
    ) -> AcceptInvitationResponse:
        invitation = session.scalar(
            select(AuthInvitation).where(
                AuthInvitation.token_hash == hash_token(payload.invitation_token)
            )
        )
        if invitation is None:
            raise ApiProblemException(
                404,
                "Invitation token is invalid or expired.",
                "Invite Not Found",
            )
        if invitation.status != AuthInvitationStatus.pending:
            raise ApiProblemException(409, "Invitation is no longer pending.", "Invite Invalid")
        if self._coerce_utc(invitation.expires_at) < self._utc_now():
            raise ApiProblemException(410, "Invitation has expired.", "Invite Expired")

        user = session.scalar(
            select(User).where(User.normalized_email == invitation.normalized_email)
        )
        now = self._utc_now()
        password_hash = self._password_hasher.hash_password(payload.password)
        if user is None:
            user = User(
                email=invitation.email,
                normalized_email=invitation.normalized_email,
                first_name=invitation.first_name or "Invited",
                last_name=invitation.last_name or "User",
                display_name=(
                    f"{(invitation.first_name or '').strip()} "
                    f"{(invitation.last_name or '').strip()}".strip()
                    or None
                ),
                password_hash=password_hash,
                is_active=True,
                invited_at=invitation.created_at,
                accepted_at=now,
            )
            session.add(user)
            session.flush()
        else:
            user.first_name = invitation.first_name or user.first_name
            user.last_name = invitation.last_name or user.last_name
            user.display_name = user.display_name or f"{user.first_name} {user.last_name}".strip()
            user.password_hash = password_hash
            user.is_active = True
            user.invited_at = user.invited_at or invitation.created_at
            user.accepted_at = now

        self._replace_user_roles(
            session,
            user=user,
            role_keys=list(invitation.role_keys_json),
            assigned_by_id=invitation.created_by_id or user.id,
        )

        invitation.status = AuthInvitationStatus.accepted
        invitation.accepted_at = now
        session.execute(
            update(AuthInvitation)
            .where(
                AuthInvitation.normalized_email == invitation.normalized_email,
                AuthInvitation.id != invitation.id,
                AuthInvitation.status == AuthInvitationStatus.pending,
            )
            .values(status=AuthInvitationStatus.revoked, revoked_at=now)
        )

        audit_service.record(
            session,
            action="auth.invitation.accepted",
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
            summary=f"Accepted invitation for {user.email}.",
            after={"roleKeys": list(invitation.role_keys_json)},
        )
        subject = build_current_subject(get_user_with_access(session, user.id) or user)
        return AcceptInvitationResponse(user=self._build_user_summary(subject))

    def login(self, session: Session, payload: LoginRequest) -> SessionResponse:
        normalized_email = normalize_email(str(payload.email))
        user = session.scalar(select(User).where(User.normalized_email == normalized_email))
        if user is None or user.password_hash is None:
            self._record_auth_failure(
                session,
                email=normalized_email,
                reason="invalid_credentials",
            )
            raise ApiProblemException(401, "Invalid email or password.", "Authentication Failed")
        if not self._password_hasher.verify_password(payload.password, user.password_hash):
            self._record_auth_failure(
                session,
                email=normalized_email,
                reason="invalid_credentials",
                user_id=user.id,
            )
            raise ApiProblemException(401, "Invalid email or password.", "Authentication Failed")
        if not user.is_active:
            self._record_auth_failure(
                session,
                email=normalized_email,
                reason="inactive_user",
                user_id=user.id,
            )
            raise ApiProblemException(403, "User account is inactive.", "Inactive User")

        user.last_login_at = self._utc_now()
        subject = build_current_subject(get_user_with_access(session, user.id) or user)
        audit_service.record(
            session,
            action="auth.session.created",
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
            summary=f"Created session for {user.email}.",
        )
        return self._create_session_response(session, subject)

    def refresh(self, session: Session, refresh_token: str) -> SessionResponse:
        if not refresh_token:
            raise ApiProblemException(401, "Refresh token is required.", "Authentication Required")

        refresh_session = session.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == hash_token(refresh_token))
        )
        if refresh_session is None or refresh_session.revoked_at is not None:
            raise ApiProblemException(401, "Refresh token is invalid.", "Authentication Required")
        if self._coerce_utc(refresh_session.expires_at) < self._utc_now():
            raise ApiProblemException(401, "Refresh token has expired.", "Authentication Required")

        user = get_user_with_access(session, refresh_session.user_id)
        if user is None or not user.is_active:
            raise ApiProblemException(
                401,
                "Authenticated user was not found.",
                "Authentication Required",
            )

        replacement_token = create_refresh_token()
        refresh_session.token_hash = hash_token(replacement_token)
        refresh_session.last_used_at = self._utc_now()
        refresh_session.expires_at = self._refresh_expiry_at()
        subject = build_current_subject(user)
        audit_service.record(
            session,
            action="auth.session.refreshed",
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
            summary=f"Refreshed session for {user.email}.",
        )
        return self._build_session_response(subject, replacement_token)

    def logout(self, session: Session, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        refresh_session = session.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == hash_token(refresh_token))
        )
        if refresh_session is None:
            return
        refresh_session.revoked_at = self._utc_now()
        audit_service.record(
            session,
            action="auth.session.revoked",
            entity_type="refresh_session",
            entity_id=refresh_session.id,
            actor_id=refresh_session.user_id,
            summary="Revoked refresh session.",
        )

    def current_user(self, subject: CurrentSubject) -> UserSummary:
        return self._build_user_summary(subject)

    def current_permissions(self, subject: CurrentSubject) -> list[str]:
        return sorted(subject.permissions)

    def replace_user_roles(
        self,
        session: Session,
        *,
        user: User,
        role_keys: list[str],
        assigned_by_id: str | None,
    ) -> None:
        self._replace_user_roles(
            session,
            user=user,
            role_keys=role_keys,
            assigned_by_id=assigned_by_id,
        )

    def _get_roles(self, session: Session, role_keys: list[str]) -> list[Role]:
        roles = list(session.scalars(select(Role).where(Role.key.in_(role_keys))))
        found_keys = {role.key for role in roles}
        missing = sorted(set(role_keys) - found_keys)
        if missing:
            raise ApiProblemException(
                422,
                f"Unknown role keys: {', '.join(missing)}.",
                "Invalid Roles",
            )
        return sorted(roles, key=lambda role: role.key)

    def _replace_user_roles(
        self,
        session: Session,
        *,
        user: User,
        role_keys: list[str],
        assigned_by_id: str | None,
    ) -> None:
        roles = self._get_roles(session, role_keys)
        session.execute(delete(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id))
        now = self._utc_now()
        for role in roles:
            session.add(
                UserRoleAssignment(
                    user_id=user.id,
                    role_id=role.id,
                    assigned_by_id=assigned_by_id,
                    created_at=now,
                )
            )
        session.flush()
        session.expire(user, ["role_assignments"])

    def _create_session_response(
        self, session: Session, subject: CurrentSubject
    ) -> SessionResponse:
        refresh_token = create_refresh_token()
        session.add(
            RefreshSession(
                user_id=subject.user.id,
                token_hash=hash_token(refresh_token),
                expires_at=self._refresh_expiry_at(),
                created_at=self._utc_now(),
            )
        )
        return self._build_session_response(subject, refresh_token)

    def _build_session_response(
        self, subject: CurrentSubject, refresh_token: str
    ) -> SessionResponse:
        permissions = sorted(subject.permissions)
        access_token = create_access_token(subject.user.id, permissions)
        return SessionResponse(
            access_token=access_token.token,
            refresh_token=refresh_token,
            expires_at=access_token.expires_at,
            user=self._build_user_summary(subject),
            permissions=permissions,
        )

    def _build_user_summary(self, subject: CurrentSubject) -> UserSummary:
        user = subject.user
        return UserSummary(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            display_name=user.display_name,
            job_title=user.job_title,
            is_active=user.is_active,
            role_keys=list(subject.role_keys),
        )

    def _refresh_expiry_at(self) -> datetime:
        settings = get_settings()
        return self._utc_now() + timedelta(days=settings.auth_refresh_token_ttl_days)

    def _record_auth_failure(
        self,
        _session: Session,
        *,
        email: str,
        reason: str,
        user_id: str | None = None,
    ) -> None:
        logger.warning(
            "auth_session_failed",
            extra={"user_id": user_id, "email": email, "reason": reason},
        )
        try:
            with get_session_factory()() as audit_session:
                audit_service.record(
                    audit_session,
                    action="auth.session.failed",
                    entity_type="auth_attempt",
                    entity_id=uuid4().hex,
                    actor_id=user_id,
                    summary=f"Failed authentication attempt for {email}.",
                    metadata={"email": email, "reason": reason},
                )
                audit_session.commit()
        except Exception:
            logger.exception(
                "auth_session_failure_audit_write_failed",
                extra={"user_id": user_id, "email": email, "reason": reason},
            )


auth_service = AuthService()
