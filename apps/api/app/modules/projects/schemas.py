from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.core.schemas import BaseSchema
from app.models.enums import (
    ProjectOutcomeType,
    ProjectPartyRole,
    ProjectStatus,
    RevenueAllocationMethod,
)
from app.modules.comparables.schemas import BenchmarkSummary


class ProjectMetadataRead(BaseSchema):
    content_type: str | None = None
    content_subtype: str | None = None
    genre: str | None = None
    format_type: str | None = None
    project_format_key: str | None = None
    runtime_minutes: int | None = None
    duration_weeks: int | None = None
    episode_count: int | None = None
    territory: str | None = None
    language: str | None = None
    budget_target: float | None = None
    metadata: dict[str, object] | None = None


class ProjectPartyRead(BaseSchema):
    id: str
    company_id: str
    company_name: str
    role: ProjectPartyRole
    is_primary: bool
    notes: str | None = None


class ProjectContactRead(BaseSchema):
    id: str
    contact_id: str
    contact_name: str
    company_id: str | None = None
    company_name: str | None = None
    contact_role_id: str | None = None
    contact_role_label: str | None = None
    job_title: str | None = None
    is_primary: bool
    notes: str | None = None


class ProjectDisciplineRead(BaseSchema):
    id: str
    discipline_id: str
    discipline_code: str
    discipline_name: str
    is_primary: bool


class ProjectScheduleRangeRead(BaseSchema):
    id: str
    discipline_id: str | None = None
    discipline_name: str | None = None
    label: str
    start_date: date
    end_date: date
    allocation_percent: float | None = None
    notes: str | None = None


class ProjectOutcomeRead(BaseSchema):
    id: str
    outcome_type: ProjectOutcomeType
    effective_at: datetime
    competitor_company_id: str | None = None
    competitor_company_name: str | None = None
    loss_reason_id: str | None = None
    notes: str | None = None
    recorded_by_id: str | None = None
    created_at: datetime


class ProjectSummary(BaseSchema):
    id: str
    code: str | None = None
    name: str
    status: ProjectStatus
    pipeline_stage_key: str | None = None
    primary_client_name: str | None = None
    quote_currency_code: str | None = None
    updated_at: datetime


class ProjectListResponse(BaseSchema):
    items: list[ProjectSummary]


class ProjectRead(BaseSchema):
    id: str
    code: str | None = None
    name: str
    status: ProjectStatus
    pipeline_stage_key: str | None = None
    bid_owner_user_id: str | None = None
    strategic_account_flag: bool = False
    description: str | None = None
    quote_currency_code: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    bid_due_date: date | None = None
    estimated_execution_start_date: date | None = None
    estimated_execution_end_date: date | None = None
    revenue_allocation_method: RevenueAllocationMethod = (
        RevenueAllocationMethod.cadence_profile
    )
    cadence_profile_type: str | None = None
    cadence_profile_data: dict[str, object] | None = None
    bid_submitted_at: datetime | None = None
    awarded_at: datetime | None = None
    lost_at: datetime | None = None
    active_at: datetime | None = None
    completed_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    metadata: ProjectMetadataRead | None = None
    parties: list[ProjectPartyRead]
    contacts: list[ProjectContactRead]
    disciplines: list[ProjectDisciplineRead]
    schedule_ranges: list[ProjectScheduleRangeRead]
    outcomes: list[ProjectOutcomeRead]


class ProjectActualsVsQuoteRead(BaseSchema):
    project_id: str
    project_name: str
    benchmark_summary: BenchmarkSummary | None = None


class ProjectCreateRequest(BaseSchema):
    code: str | None = None
    name: str
    status: ProjectStatus = ProjectStatus.bid
    pipeline_stage_key: str | None = None
    bid_owner_user_id: str | None = None
    strategic_account_flag: bool = False
    description: str | None = None
    quote_currency_code: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    bid_due_date: date | None = None
    estimated_execution_start_date: date | None = None
    estimated_execution_end_date: date | None = None
    revenue_allocation_method: RevenueAllocationMethod = (
        RevenueAllocationMethod.cadence_profile
    )
    cadence_profile_type: str | None = None
    cadence_profile_data: dict[str, object] | None = None


class ProjectUpdateRequest(BaseSchema):
    expected_updated_at: datetime
    code: str | None = None
    name: str | None = None
    status: ProjectStatus | None = None
    pipeline_stage_key: str | None = None
    bid_owner_user_id: str | None = None
    strategic_account_flag: bool | None = None
    description: str | None = None
    quote_currency_code: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    bid_due_date: date | None = None
    estimated_execution_start_date: date | None = None
    estimated_execution_end_date: date | None = None
    revenue_allocation_method: RevenueAllocationMethod | None = None
    cadence_profile_type: str | None = None
    cadence_profile_data: dict[str, object] | None = None
    bid_submitted_at: datetime | None = None
    awarded_at: datetime | None = None
    lost_at: datetime | None = None
    active_at: datetime | None = None
    completed_at: datetime | None = None
    archived_at: datetime | None = None


class ProjectMetadataPutRequest(BaseSchema):
    expected_updated_at: datetime
    content_type: str | None = None
    content_subtype: str | None = None
    genre: str | None = None
    format_type: str | None = None
    project_format_key: str | None = None
    runtime_minutes: int | None = None
    duration_weeks: int | None = None
    episode_count: int | None = None
    territory: str | None = None
    language: str | None = None
    budget_target: float | None = None
    metadata: dict[str, object] | None = None


class ProjectPartiesReplaceItem(BaseSchema):
    company_id: str
    role: ProjectPartyRole
    is_primary: bool = False
    notes: str | None = None


class ProjectPartiesReplaceRequest(BaseSchema):
    expected_updated_at: datetime
    items: list[ProjectPartiesReplaceItem] = Field(default_factory=list)


class ProjectContactsReplaceItem(BaseSchema):
    contact_id: str
    company_id: str | None = None
    contact_role_id: str | None = None
    job_title: str | None = None
    is_primary: bool = False
    notes: str | None = None


class ProjectContactsReplaceRequest(BaseSchema):
    expected_updated_at: datetime
    items: list[ProjectContactsReplaceItem] = Field(default_factory=list)


class ProjectDisciplinesReplaceItem(BaseSchema):
    discipline_id: str
    is_primary: bool = False


class ProjectDisciplinesReplaceRequest(BaseSchema):
    expected_updated_at: datetime
    items: list[ProjectDisciplinesReplaceItem] = Field(default_factory=list)


class ProjectScheduleRangeWrite(BaseSchema):
    discipline_id: str | None = None
    label: str
    start_date: date
    end_date: date
    allocation_percent: float | None = None
    notes: str | None = None


class ProjectScheduleRangesReplaceRequest(BaseSchema):
    expected_updated_at: datetime
    items: list[ProjectScheduleRangeWrite] = Field(default_factory=list)


class ProjectOutcomeCreateRequest(BaseSchema):
    outcome_type: ProjectOutcomeType
    effective_at: datetime
    competitor_company_id: str | None = None
    loss_reason_id: str | None = None
    notes: str | None = None
