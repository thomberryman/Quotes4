from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.core.schemas import BaseSchema
from app.models.enums import QuoteLineItemType, QuoteVersionStatus


class QuoteLineItemRead(BaseSchema):
    id: str
    sort_order: int
    line_type: QuoteLineItemType
    discipline_id: str | None = None
    subcategory_key: str | None = None
    revenue_category_key: str | None = None
    description: str
    quantity: float
    unit: str
    rate: float
    amount: float
    notes: str | None = None


class QuoteLineItemWrite(BaseSchema):
    sort_order: int
    line_type: QuoteLineItemType = QuoteLineItemType.service
    discipline_id: str | None = None
    subcategory_key: str | None = None
    revenue_category_key: str | None = None
    description: str
    quantity: float = 1
    unit: str
    rate: float = 0
    amount: float = 0
    notes: str | None = None


class QuoteSectionRead(BaseSchema):
    id: str
    name: str
    sort_order: int
    subtotal_amount: float
    line_items: list[QuoteLineItemRead]


class QuoteSectionWrite(BaseSchema):
    name: str
    sort_order: int
    subtotal_amount: float = 0
    line_items: list[QuoteLineItemWrite] = Field(default_factory=list)


class QuoteVersionSummary(BaseSchema):
    id: str
    quote_id: str
    parent_version_id: str | None = None
    version_number: int
    status: QuoteVersionStatus
    title: str | None = None
    currency_code: str
    valid_until: date | None = None
    issued_at: datetime | None = None
    subtotal_amount: float
    tax_amount: float
    total_amount: float
    created_at: datetime
    updated_at: datetime


class QuoteVersionRead(QuoteVersionSummary):
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    client_facing_notes: str | None = None
    internal_notes: str | None = None
    source_document_date: date | None = None
    source_version_label: str | None = None
    pricing_context: dict[str, object] | None = None
    sections: list[QuoteSectionRead]


class QuoteSummary(BaseSchema):
    id: str
    project_id: str
    quote_number: str | None = None
    title: str | None = None
    current_version_id: str | None = None
    current_version_status: QuoteVersionStatus | None = None
    updated_at: datetime


class QuoteListResponse(BaseSchema):
    items: list[QuoteSummary]


class QuoteRead(QuoteSummary):
    created_at: datetime
    versions: list[QuoteVersionSummary]


class QuoteCreateRequest(BaseSchema):
    project_id: str
    quote_number: str | None = None
    title: str | None = None


class QuoteUpdateRequest(BaseSchema):
    expected_updated_at: datetime
    quote_number: str | None = None
    title: str | None = None
    current_version_id: str | None = None


class QuoteVersionCreateRequest(BaseSchema):
    base_version_id: str | None = None
    title: str | None = None
    currency_code: str
    valid_until: date | None = None
    client_facing_notes: str | None = None
    internal_notes: str | None = None
    source_document_date: date | None = None
    source_version_label: str | None = None
    pricing_context: dict[str, object] | None = None
    subtotal_amount: float
    tax_amount: float = 0
    total_amount: float
    sections: list[QuoteSectionWrite] = Field(default_factory=list)


class QuoteVersionUpdateRequest(BaseSchema):
    expected_updated_at: datetime
    title: str | None = None
    currency_code: str | None = None
    valid_until: date | None = None
    client_facing_notes: str | None = None
    internal_notes: str | None = None
    source_document_date: date | None = None
    source_version_label: str | None = None
    pricing_context: dict[str, object] | None = None
    subtotal_amount: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    sections: list[QuoteSectionWrite] | None = None
