from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.schemas import BaseSchema


class ForecastMonthlyAllocationRead(BaseSchema):
    month: str
    amount: float
    weighted_amount: float


class ForecastLineRead(BaseSchema):
    id: str
    source_line_id: str
    label: str
    total_amount: float
    weighted_total_amount: float
    currency_code: str
    allocation_method: str
    discipline_id: str | None = None
    schedule_range_id: str | None = None
    notes: str | None = None
    issues: list[str]
    allocations: list[ForecastMonthlyAllocationRead]


class ForecastDisciplineMonthlyRollupRead(BaseSchema):
    discipline_id: str | None = None
    month: str
    amount: float
    weighted_amount: float


class ForecastProjectMonthlyRollupRead(BaseSchema):
    month: str
    amount: float
    weighted_amount: float


class ForecastVersionSummaryRead(BaseSchema):
    id: str
    forecast_id: str
    version_number: int
    status: str
    title: str | None = None
    outcome_type_snapshot: str
    probability_percent: float
    total_amount: float
    weighted_total_amount: float
    source_quote_version_id: str | None = None
    is_source_quote_current: bool
    created_at: datetime
    updated_at: datetime


class ForecastVersionRead(ForecastVersionSummaryRead):
    notes_text: str | None = None
    revision_reason: str | None = None
    parent_version_id: str | None = None
    issues: list[str]
    lines: list[ForecastLineRead]
    discipline_monthly_rollups: list[ForecastDisciplineMonthlyRollupRead]
    project_monthly_rollups: list[ForecastProjectMonthlyRollupRead]


class ForecastDetailRead(BaseSchema):
    forecast_id: str
    project_id: str
    current_version_id: str | None = None
    versions: list[ForecastVersionSummaryRead]
    current_version: ForecastVersionRead | None = None


class ForecastVersionCreateRequest(BaseSchema):
    base_version_id: str | None = None
    title: str | None = None
    notes_text: str | None = None
    probability_percent: float | None = Field(default=None, ge=0, le=100)
    revision_reason: str | None = None


class ForecastVersionUpdateRequest(BaseSchema):
    expected_updated_at: datetime
    title: str | None = None
    notes_text: str | None = None
    probability_percent: float | None = Field(default=None, ge=0, le=100)
    revision_reason: str | None = None


class ForecastLineMonthAllocationWrite(BaseSchema):
    month: str
    amount: float


class ForecastLineAllocationsReplaceRequest(BaseSchema):
    expected_updated_at: datetime
    allocation_method: str
    allocations: list[ForecastLineMonthAllocationWrite] = Field(default_factory=list)
    reason: str | None = None
    schedule_range_id: str | None = None


class ForecastPolicySummary(BaseSchema):
    supported_methods: list[str]
    supported_outcomes: list[str]
    recalc_triggers: list[str]


class ForecastRecalculateResponse(BaseSchema):
    project_id: str
    job_id: str
    queue_name: str
    status: str
    forecast_version_id: str | None = None
    message: str
