from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.core.schemas import BaseSchema
from app.core.types import EmailAddress
from app.modules.auth.schemas import UserSummary


class UserRead(UserSummary):
    invited_at: datetime | None = None
    accepted_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseSchema):
    items: list[UserRead]


class UserCreateRequest(BaseSchema):
    email: EmailAddress
    first_name: str
    last_name: str
    display_name: str | None = None
    job_title: str | None = None
    is_active: bool = True
    role_keys: list[str] = Field(default_factory=list)

    @field_validator("role_keys")
    @classmethod
    def normalize_roles(cls, value: list[str]) -> list[str]:
        return sorted({item.strip() for item in value if item.strip()})


class UserUpdateRequest(BaseSchema):
    expected_updated_at: datetime
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    job_title: str | None = None
    is_active: bool | None = None


class UserRolesUpdateRequest(BaseSchema):
    role_keys: list[str] = Field(default_factory=list)

    @field_validator("role_keys")
    @classmethod
    def normalize_roles(cls, value: list[str]) -> list[str]:
        return sorted({item.strip() for item in value if item.strip()})
