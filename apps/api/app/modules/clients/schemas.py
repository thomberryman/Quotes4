from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.core.schemas import BaseSchema
from app.core.types import EmailAddress
from app.models.enums import CompanyClassificationType


class CounterpartyRead(BaseSchema):
    id: str
    name: str
    legal_name: str | None = None
    website_url: str | None = None
    default_currency_code: str | None = None
    notes: str | None = None
    is_active: bool
    classifications: list[CompanyClassificationType]
    created_at: datetime
    updated_at: datetime


class CounterpartyListResponse(BaseSchema):
    items: list[CounterpartyRead]


class CounterpartyCreateRequest(BaseSchema):
    name: str
    legal_name: str | None = None
    website_url: str | None = None
    default_currency_code: str | None = None
    notes: str | None = None
    is_active: bool = True
    classifications: list[CompanyClassificationType] = Field(default_factory=list)

    @field_validator("classifications")
    @classmethod
    def normalize_classifications(
        cls, value: list[CompanyClassificationType]
    ) -> list[CompanyClassificationType]:
        return sorted(set(value), key=lambda item: item.value)


class CounterpartyUpdateRequest(BaseSchema):
    expected_updated_at: datetime
    name: str | None = None
    legal_name: str | None = None
    website_url: str | None = None
    default_currency_code: str | None = None
    notes: str | None = None
    is_active: bool | None = None
    classifications: list[CompanyClassificationType] | None = None

    @field_validator("classifications")
    @classmethod
    def normalize_classifications(
        cls, value: list[CompanyClassificationType] | None
    ) -> list[CompanyClassificationType] | None:
        if value is None:
            return None
        return sorted(set(value), key=lambda item: item.value)


class ContactRead(BaseSchema):
    id: str
    first_name: str
    last_name: str
    full_name: str
    email: EmailAddress | None = None
    phone: str | None = None
    mobile: str | None = None
    notes: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ContactListResponse(BaseSchema):
    items: list[ContactRead]


class ContactCreateRequest(BaseSchema):
    first_name: str
    last_name: str
    email: EmailAddress | None = None
    phone: str | None = None
    mobile: str | None = None
    notes: str | None = None
    is_active: bool = True


class ContactUpdateRequest(BaseSchema):
    expected_updated_at: datetime
    first_name: str | None = None
    last_name: str | None = None
    email: EmailAddress | None = None
    phone: str | None = None
    mobile: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class DisciplineRead(BaseSchema):
    id: str
    code: str
    name: str
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DisciplineListResponse(BaseSchema):
    items: list[DisciplineRead]


class DisciplineCreateRequest(BaseSchema):
    code: str
    name: str
    sort_order: int = 0
    is_active: bool = True


class DisciplineUpdateRequest(BaseSchema):
    expected_updated_at: datetime
    code: str | None = None
    name: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
