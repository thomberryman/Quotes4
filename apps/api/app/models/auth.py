from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentifierMixin, JsonObjectType, TimestampMixin
from app.models.enums import AuthInvitationStatus


class User(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True)
    normalized_email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role_assignments: Mapped[list[UserRoleAssignment]] = relationship(
        back_populates="user",
        foreign_keys="UserRoleAssignment.user_id",
        cascade="all, delete-orphan",
    )
    assigned_role_assignments: Mapped[list[UserRoleAssignment]] = relationship(
        back_populates="assigned_by",
        foreign_keys="UserRoleAssignment.assigned_by_id",
    )
    refresh_sessions: Mapped[list[RefreshSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    created_invitations: Mapped[list[AuthInvitation]] = relationship(
        back_populates="created_by", foreign_keys="AuthInvitation.created_by_id"
    )


class Role(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(100), unique=True)
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    permission_links: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )
    user_assignments: Mapped[list[UserRoleAssignment]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class Permission(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(120), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    role_links: Mapped[list[RolePermission]] = relationship(
        back_populates="permission", cascade="all, delete-orphan"
    )


class RolePermission(IdentifierMixin, Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[str] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE")
    )

    role: Mapped[Role] = relationship(back_populates="permission_links")
    permission: Mapped[Permission] = relationship(back_populates="role_links")

    __table_args__ = (
        Index("ix_role_permissions_role_id", "role_id"),
        Index("ix_role_permissions_permission_id", "permission_id"),
        Index("ix_role_permissions_role_permission", "role_id", "permission_id", unique=True),
    )


class UserRoleAssignment(IdentifierMixin, Base):
    __tablename__ = "user_role_assignments"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    assigned_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(
        back_populates="role_assignments", foreign_keys=[user_id]
    )
    role: Mapped[Role] = relationship(back_populates="user_assignments")
    assigned_by: Mapped[User | None] = relationship(
        back_populates="assigned_role_assignments", foreign_keys=[assigned_by_id]
    )

    __table_args__ = (
        Index("ix_user_role_assignments_role_id", "role_id"),
        Index("ix_user_role_assignments_assigned_by_id", "assigned_by_id"),
        Index("ix_user_role_assignments_user_role", "user_id", "role_id", unique=True),
    )


class AuthInvitation(IdentifierMixin, Base):
    __tablename__ = "auth_invitations"

    email: Mapped[str] = mapped_column(String(255))
    normalized_email: Mapped[str] = mapped_column(String(255), index=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_hash: Mapped[str] = mapped_column(Text())
    role_keys_json: Mapped[list[str]] = mapped_column(JsonObjectType)
    status: Mapped[AuthInvitationStatus] = mapped_column(
        String(30), default=AuthInvitationStatus.pending
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[User | None] = relationship(
        back_populates="created_invitations", foreign_keys=[created_by_id]
    )


class RefreshSession(IdentifierMixin, Base):
    __tablename__ = "refresh_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(Text(), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="refresh_sessions")
