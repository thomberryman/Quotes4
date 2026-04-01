from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.core.schemas import BaseSchema
from app.models.enums import (
    ActualMappingApprovalAction,
    CetaImportCandidateDimension,
    CetaImportCoverageMode,
    CetaImportIssueSeverity,
    CetaImportStatus,
    CetaRowFinancialType,
    CetaRowStatus,
    MappingMethod,
)
from app.modules.files.service import UploadedFileRead


class CreateActualsImportBatchRequest(BaseSchema):
    uploaded_file_id: str
    coverage_mode: CetaImportCoverageMode = CetaImportCoverageMode.snapshot
    project_id: str | None = None
    source_system: str | None = "ceta"
    source_export_id: str | None = None
    source_exported_at: datetime | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    parser_profile_hint: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_coverage(self) -> CreateActualsImportBatchRequest:
        if self.coverage_start and self.coverage_end and self.coverage_start > self.coverage_end:
            raise ValueError("coverageStart must be on or before coverageEnd.")
        if self.coverage_mode == CetaImportCoverageMode.incremental and not (
            self.coverage_start and self.coverage_end
        ):
            raise ValueError(
                "Incremental imports must provide both coverageStart and coverageEnd."
            )
        return self


class ActualsImportReviewBucketRead(BaseSchema):
    key: str
    label: str
    count: int


class ActualsImportIssueRead(BaseSchema):
    id: str
    severity: CetaImportIssueSeverity
    issue_code: str
    field_name: str | None = None
    message: str
    details: dict[str, object] | None = None
    resolved_at: datetime | None = None


class ActualsImportCandidateRead(BaseSchema):
    id: str
    dimension: CetaImportCandidateDimension
    target_type: str
    target_key: str
    target_label: str
    candidate_source: str
    score: float
    explanation: str
    sort_order: int
    metadata: dict[str, object] | None = None


class ActualsImportDecisionRead(BaseSchema):
    id: str
    mapped_project_id: str | None = None
    mapped_project_name: str | None = None
    mapped_discipline_id: str | None = None
    mapped_discipline_name: str | None = None
    financial_type: CetaRowFinancialType | None = None
    cost_category_key: str | None = None
    revenue_category_key: str | None = None
    approval_action: ActualMappingApprovalAction
    mapping_method: MappingMethod
    matched_existing_actual_id: str | None = None
    confidence_score: float | None = None
    reviewer_note: str | None = None
    explanation: dict[str, object] | None = None
    created_rule_id: str | None = None
    created_alias_id: str | None = None
    created_external_reference_id: str | None = None
    created_at: datetime


class ActualsImportRowRead(BaseSchema):
    id: str
    row_number: int
    source_row_uid: str | None = None
    status: CetaRowStatus
    review_queue: str
    external_project_code: str | None = None
    work_date: date | None = None
    posting_date: date | None = None
    source_discipline_code: str | None = None
    description: str | None = None
    vendor_name: str | None = None
    amount: float
    currency_code: str
    financial_type: CetaRowFinancialType
    row_hash: str
    business_key_hash: str
    duplicate_group_key: str | None = None
    suggested_project_id: str | None = None
    suggested_project_name: str | None = None
    suggested_discipline_id: str | None = None
    suggested_discipline_name: str | None = None
    suggested_cost_category_key: str | None = None
    suggested_revenue_category_key: str | None = None
    matched_current_actual_id: str | None = None
    issues: list[ActualsImportIssueRead]
    candidates: list[ActualsImportCandidateRead]
    latest_decision: ActualsImportDecisionRead | None = None
    raw_payload: dict[str, object] | None = None


class ActualsImportRowListResponse(BaseSchema):
    items: list[ActualsImportRowRead]


class ActualsImportVarianceProjectRead(BaseSchema):
    project_id: str
    project_name: str
    import_amount: float
    current_quote_amount: float | None = None
    current_forecast_amount: float | None = None
    current_actual_amount: float | None = None
    import_vs_quote_variance: float | None = None
    import_vs_forecast_variance: float | None = None
    import_vs_current_actual_variance: float | None = None


class ActualsImportVarianceMonthRead(BaseSchema):
    month: str
    import_amount: float
    current_actual_amount: float


class SnapshotWithdrawalCandidateRead(BaseSchema):
    actual_id: str
    project_id: str
    project_name: str
    work_date: date | None = None
    description: str | None = None
    vendor_name: str | None = None
    amount: float
    currency_code: str
    financial_type: CetaRowFinancialType
    actual_business_key: str


class ActualsImportBatchSummaryRead(BaseSchema):
    id: str
    status: CetaImportStatus
    coverage_mode: CetaImportCoverageMode
    project_id: str | None = None
    project_name: str | None = None
    uploaded_file_id: str
    parser_profile_hint: str | None = None
    parser_profile_detected: str | None = None
    source_system: str | None = None
    source_export_id: str | None = None
    source_exported_at: datetime | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    row_count: int
    blocking_issue_count: int
    parse_summary: dict[str, object]
    review_summary: dict[str, object]
    uploaded_at: datetime
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None


class ActualsImportBatchDetailRead(ActualsImportBatchSummaryRead):
    file: UploadedFileRead
    notes: str | None = None
    review_buckets: list[ActualsImportReviewBucketRead]
    batch_issues: list[ActualsImportIssueRead]
    variance_projects: list[ActualsImportVarianceProjectRead]
    variance_months: list[ActualsImportVarianceMonthRead]
    snapshot_withdrawal_candidates: list[SnapshotWithdrawalCandidateRead]


class ActualsImportBatchListResponse(BaseSchema):
    items: list[ActualsImportBatchSummaryRead]


class UpdateActualsImportRowDecisionRequest(BaseSchema):
    mapped_project_id: str | None = None
    mapped_discipline_id: str | None = None
    financial_type: CetaRowFinancialType | None = None
    cost_category_key: str | None = None
    revenue_category_key: str | None = None
    approval_action: ActualMappingApprovalAction
    matched_existing_actual_id: str | None = None
    mapping_method: MappingMethod = MappingMethod.manual
    confidence_score: float | None = Field(default=None, ge=0, le=100)
    reviewer_note: str | None = None
    explanation: dict[str, object] | None = None
    save_project_external_reference: bool = False
    save_category_alias: bool = False
    save_rule: bool = False
    rule_name: str | None = None


class ApproveActualsImportBatchRequest(BaseSchema):
    withdraw_actual_ids: list[str] = Field(default_factory=list)

    @field_validator("withdraw_actual_ids")
    @classmethod
    def deduplicate_withdraw_actual_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item for item in value if item))


class RejectActualsImportBatchRequest(BaseSchema):
    reason: str | None = None


class ApproveActualsImportBatchResponse(BaseSchema):
    batch_id: str
    status: CetaImportStatus
    approved_actual_count: int
    linked_repeat_count: int
    superseded_actual_count: int
    withdrawn_actual_count: int
    affected_project_ids: list[str]


class RejectActualsImportBatchResponse(BaseSchema):
    batch_id: str
    status: CetaImportStatus
    reason: str | None = None


class WorkerActualsImportIssue(BaseSchema):
    severity: CetaImportIssueSeverity
    issue_code: str
    field_name: str | None = None
    message: str
    details: dict[str, object] | None = None


class WorkerActualsImportRow(BaseSchema):
    row_number: int = Field(gt=0)
    source_row_uid: str | None = None
    row_hash: str
    business_key_hash: str
    duplicate_group_key: str | None = None
    external_project_code: str | None = None
    normalized_project_code: str | None = None
    work_date: date | None = None
    posting_date: date | None = None
    source_discipline_code: str | None = None
    description: str | None = None
    normalized_description: str | None = None
    vendor_name: str | None = None
    normalized_vendor_name: str | None = None
    amount: float
    currency_code: str
    financial_type: CetaRowFinancialType
    raw_payload: dict[str, object] | None = None
    issues: list[WorkerActualsImportIssue] = Field(default_factory=list)

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code(cls, value: str) -> str:
        currency = value.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currencyCode must be a three-letter ISO currency code.")
        return currency

    @field_validator("row_hash", "business_key_hash")
    @classmethod
    def validate_hash_fields(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or len(normalized) > 128:
            raise ValueError("Hash fields must be between 1 and 128 characters.")
        return normalized


class WorkerActualsImportResultRequest(BaseSchema):
    job_id: str
    status: Literal["in_review", "failed"]
    parser_name: str | None = None
    parser_version: str | None = None
    parser_profile: str | None = None
    source_system: str | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    batch_issues: list[WorkerActualsImportIssue] = Field(default_factory=list)
    rows: list[WorkerActualsImportRow] = Field(default_factory=list)
    failure_code: str | None = None
    failure_message: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> WorkerActualsImportResultRequest:
        if self.status == "failed":
            if not self.failure_code:
                raise ValueError("failureCode is required when the worker result failed.")
            return self

        if self.status != "in_review":
            raise ValueError("status must be either 'in_review' or 'failed'.")
        row_numbers = {row.row_number for row in self.rows}
        if len(row_numbers) != len(self.rows):
            raise ValueError("Worker rows must have unique rowNumber values.")
        business_keys = {(row.row_hash, row.business_key_hash) for row in self.rows}
        if len(business_keys) != len(self.rows):
            raise ValueError("Worker rows must have unique rowHash and businessKeyHash pairs.")
        return self


class ProcessActualsBatchResponse(BaseSchema):
    batch_id: str
    job_id: str
    queue_name: str
    status: str
    traceability_mode: str
