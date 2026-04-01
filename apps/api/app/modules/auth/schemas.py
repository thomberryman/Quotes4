from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.core.schemas import BaseSchema
from app.core.types import EmailAddress


class UserSummary(BaseSchema):
    id: str
    email: EmailAddress
    first_name: str
    last_name: str
    display_name: str | None = None
    job_title: str | None = None
    is_active: bool = True
    role_keys: list[str]


class InvitationRequest(BaseSchema):
    email: EmailAddress
    first_name: str
    last_name: str
    role_keys: list[str] = Field(default_factory=list, min_length=1)

    @field_validator("role_keys")
    @classmethod
    def validate_role_keys(cls, value: list[str]) -> list[str]:
        unique = sorted({item.strip() for item in value if item.strip()})
        if not unique:
            raise ValueError("At least one role key is required.")
        return unique


class InvitationResponse(BaseSchema):
    invitation_id: str
    email: EmailAddress
    invite_token: str
    expires_at: datetime
    role_keys: list[str]


class AcceptInvitationRequest(BaseSchema):
    invitation_token: str
    password: str = Field(min_length=12)


class AcceptInvitationResponse(BaseSchema):
    user: UserSummary


class LoginRequest(BaseSchema):
    email: EmailAddress
    password: str = Field(min_length=12)


class SessionResponse(BaseSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserSummary
    permissions: list[str]


class RefreshSessionRequest(BaseSchema):
    refresh_token: str | None = None


class LogoutResponse(BaseSchema):
    message: str
