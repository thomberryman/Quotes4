from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.core.schemas import BaseSchema
from app.core.validation import (
    normalize_content_type,
    normalize_file_name,
    normalize_sha256_checksum,
    validate_storage_object_key,
)
from app.models.enums import QuoteLineItemType


class QuoteIngestionFileSummary(BaseSchema):
    file_id: str
    file_name: str
    object_key: str
    file_category: str
    status: str
    download_url: str
    public_url: str


class ExtractionWarning(BaseSchema):
    code: str
    message: str
    severity: str
    blocking: bool = False


class ConfidenceSummary(BaseSchema):
    high: int
    medium: int
    low: int


class MatchSuggestion(BaseSchema):
    id: str
    entity_type: str
    entity_id: str
    label: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    rank: int
    is_selected: bool = False


class FieldCandidate(BaseSchema):
    id: str
    field_path: str
    occurrence_index: int
    raw_value: str | None = None
    normalized_text: str | None = None
    normalized_amount: float | None = None
    normalized_date: date | None = None
    confidence_score: float | None = None
    confidence_flag: Literal["high", "medium", "low"] | None = None
    page_number: int | None = None
    review_status: str = "pending"
    reviewer_note: str | None = None
    source_snippet: str | None = None
    source_bounds: dict[str, object] | None = None


class FieldDecision(BaseSchema):
    id: str
    field_path: str
    selected_result_id: str | None = None
    reviewed_text: str | None = None
    reviewed_amount: float | None = None
    reviewed_date: date | None = None
    review_status: str = "pending"
    reviewer_note: str | None = None


class LineItemCandidate(BaseSchema):
    id: str
    sort_order: int
    section_label: str | None = None
    line_type: str = "service"
    description: str
    quantity: float
    unit: str
    rate: float
    amount: float
    currency_code: str | None = None
    confidence_score: float | None = None
    confidence_flag: Literal["high", "medium", "low"] | None = None
    page_number: int | None = None
    review_status: str = "pending"
    source_snippet: str | None = None
    source_bounds: dict[str, object] | None = None


class LineItemDecision(BaseSchema):
    id: str
    sort_order: int
    source_result_id: str | None = None
    section_label: str
    line_type: str = "service"
    description: str
    quantity: float
    unit: str
    rate: float
    amount: float
    review_status: str = "pending"
    reviewer_note: str | None = None


class ApprovalBlocker(BaseSchema):
    code: str
    message: str


class ApprovalPreview(BaseSchema):
    project_id: str | None = None
    quote_id: str | None = None
    target_mode: str | None = None
    next_version_number: int | None = None
    title: str | None = None
    source_version_label: str | None = None
    total_amount: float | None = None


class QuoteIngestionRunSummary(BaseSchema):
    id: str
    status: str
    uploaded_file_id: str
    file_name: str | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    parser_profile: str | None = None
    page_count: int | None = Field(default=None, gt=0)
    text_page_count: int | None = Field(default=None, ge=0)
    failure_code: str | None = None
    failure_message: str | None = None
    selected_project_id: str | None = None
    selected_quote_id: str | None = None
    selected_target_mode: str | None = None
    approved_quote_id: str | None = None
    approved_quote_version_id: str | None = None
    job_id: str
    queue_name: str
    review_mode: str = "mandatory_human_review"
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class QuoteIngestionRunDetail(QuoteIngestionRunSummary):
    file: QuoteIngestionFileSummary
    raw_text: str | None = None
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    confidence_summary: ConfidenceSummary
    match_suggestions: list[MatchSuggestion] = Field(default_factory=list)
    field_candidates: list[FieldCandidate] = Field(default_factory=list)
    field_decisions: list[FieldDecision] = Field(default_factory=list)
    line_item_candidates: list[LineItemCandidate] = Field(default_factory=list)
    line_item_decisions: list[LineItemDecision] = Field(default_factory=list)
    approval_blockers: list[ApprovalBlocker] = Field(default_factory=list)
    approval_preview: ApprovalPreview
    acknowledged_warning_codes: list[str] = Field(default_factory=list)


class QuoteIngestionRunListResponse(BaseSchema):
    items: list[QuoteIngestionRunSummary]


class CreateQuoteIngestionUploadRequest(BaseSchema):
    file_name: str
    content_type: str
    size_bytes: int = Field(gt=0)
    checksum_sha256: str

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        return normalize_file_name(value)

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        return normalize_content_type(value)

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum_sha256(cls, value: str) -> str:
        return normalize_sha256_checksum(value)


class QuoteIngestionUploadIntentResponse(BaseSchema):
    file: QuoteIngestionFileSummary
    bucket: str
    upload_url: str
    expires_at: datetime
    required_headers: dict[str, str]


class FinalizeQuoteIngestionUploadRequest(BaseSchema):
    file_id: str
    object_key: str
    checksum_sha256: str

    @field_validator("object_key")
    @classmethod
    def validate_object_key(cls, value: str) -> str:
        return validate_storage_object_key(value)

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum_sha256(cls, value: str) -> str:
        return normalize_sha256_checksum(value)


class FinalizeQuoteIngestionUploadResponse(BaseSchema):
    file: QuoteIngestionFileSummary


class CreateQuoteIngestionRunRequest(BaseSchema):
    uploaded_file_id: str
    project_id: str | None = None
    parser_profile: str | None = None


class FieldDecisionInput(BaseSchema):
    field_path: str
    selected_result_id: str | None = None
    reviewed_text: str | None = None
    reviewed_amount: float | None = None
    reviewed_date: date | None = None
    review_status: str
    reviewer_note: str | None = None


class LineItemDecisionInput(BaseSchema):
    sort_order: int
    source_result_id: str | None = None
    section_label: str
    line_type: str = "service"
    description: str
    quantity: float
    unit: str
    rate: float
    amount: float
    review_status: str
    reviewer_note: str | None = None


class UpdateQuoteIngestionReviewRequest(BaseSchema):
    selected_project_id: str | None = None
    selected_quote_id: str | None = None
    selected_target_mode: Literal["new_quote", "new_version"] | None = None
    acknowledged_warning_codes: list[str] = Field(default_factory=list)
    field_decisions: list[FieldDecisionInput] = Field(default_factory=list)
    line_item_decisions: list[LineItemDecisionInput] = Field(default_factory=list)


class ApproveQuoteIngestionRunRequest(BaseSchema):
    pass


class QuoteApprovalResponse(BaseSchema):
    run_id: str
    status: str
    approved_quote_id: str
    approved_quote_version_id: str
    approval_summary: str


class RerunQuoteIngestionRunRequest(BaseSchema):
    parser_profile: str | None = None


class RejectQuoteIngestionRunRequest(BaseSchema):
    reason: str


class QuoteParsePreviewResponse(BaseSchema):
    object_key: str
    parser_name: str
    parser_version: str
    text_page_count: int
    warnings: list[str]
    candidate_count: int


class WorkerParseWarningInput(BaseSchema):
    code: str
    message: str
    severity: str
    blocking: bool = False


class WorkerFieldCandidateInput(BaseSchema):
    field_path: str
    occurrence_index: int = 0
    raw_value: str | None = None
    normalized_text: str | None = None
    normalized_amount: float | None = None
    normalized_date: date | None = None
    confidence_score: float | None = None
    page_number: int | None = Field(default=None, gt=0)
    source_snippet: str | None = None
    source_bounds: dict[str, object] | None = None

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence_score(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("confidenceScore must be between 0 and 1.")
        return value


class WorkerLineItemCandidateInput(BaseSchema):
    sort_order: int = Field(gt=0)
    section_label: str | None = None
    line_type: str = "service"
    description: str
    quantity: float
    unit: str
    rate: float
    amount: float
    currency_code: str | None = None
    confidence_score: float | None = None
    page_number: int | None = Field(default=None, gt=0)
    source_snippet: str | None = None
    source_bounds: dict[str, object] | None = None

    @field_validator("line_type")
    @classmethod
    def validate_line_type(cls, value: str) -> str:
        allowed = {item.value for item in QuoteLineItemType}
        if value not in allowed:
            raise ValueError(f"lineType must be one of: {', '.join(sorted(allowed))}.")
        return value

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence_score(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("confidenceScore must be between 0 and 1.")
        return value


class WorkerParseResultRequest(BaseSchema):
    job_id: str
    status: Literal["in_review", "failed"]
    parser_name: str | None = None
    parser_version: str | None = None
    parser_profile: str | None = None
    page_count: int | None = None
    text_page_count: int | None = None
    raw_text: str | None = None
    warnings: list[WorkerParseWarningInput] = Field(default_factory=list)
    field_candidates: list[WorkerFieldCandidateInput] = Field(default_factory=list)
    line_item_candidates: list[WorkerLineItemCandidateInput] = Field(default_factory=list)
    failure_code: str | None = None
    failure_message: str | None = None
    project_id: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> WorkerParseResultRequest:
        if self.status == "failed":
            if not self.failure_code:
                raise ValueError("failureCode is required when the worker result failed.")
            return self

        required_fields = {
            "parserName": self.parser_name,
            "parserVersion": self.parser_version,
            "pageCount": self.page_count,
            "textPageCount": self.text_page_count,
            "rawText": self.raw_text,
        }
        missing = [key for key, value in required_fields.items() if value in {None, ""}]
        if missing:
            raise ValueError(
                f"Successful worker results must include: {', '.join(sorted(missing))}."
            )
        if self.page_count is not None and self.text_page_count is not None:
            if self.text_page_count > self.page_count:
                raise ValueError("textPageCount cannot exceed pageCount.")
        field_keys = {(item.field_path, item.occurrence_index) for item in self.field_candidates}
        if len(field_keys) != len(self.field_candidates):
            raise ValueError(
                "Worker field candidates must be unique by fieldPath and occurrenceIndex."
            )
        line_item_keys = {item.sort_order for item in self.line_item_candidates}
        if len(line_item_keys) != len(self.line_item_candidates):
            raise ValueError("Worker line item candidates must have unique sortOrder values.")
        return self
