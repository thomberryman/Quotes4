from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentifierMixin, JsonObjectType, TimestampMixin
from app.models.enums import (
    ActualMappingApprovalAction,
    ActualMappingDecisionStatus,
    CetaImportCandidateDimension,
    CetaImportCoverageMode,
    CetaImportIssueSeverity,
    CetaImportStatus,
    CetaRowFinancialType,
    CetaRowStatus,
    MappedActualChangeType,
    MappingMethod,
    PdfExtractionConfidenceFlag,
    PdfExtractionResultSource,
    PdfExtractionReviewStatus,
    PdfExtractionRunStatus,
    PdfExtractionTargetMode,
    QuoteLineItemType,
)

if TYPE_CHECKING:
    from app.models.auth import User
    from app.models.files import UploadedFile
    from app.models.jobs import BackgroundJob
    from app.models.projects import Project
    from app.models.quotes import Quote, QuoteVersion
    from app.models.reference import Discipline


class PdfExtractionRun(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "pdf_extraction_runs"

    uploaded_file_id: Mapped[str] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="CASCADE")
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="SET NULL"), nullable=True
    )
    queue_name: Mapped[str] = mapped_column(String(100), default="pdf_parse")
    status: Mapped[PdfExtractionRunStatus] = mapped_column(
        SqlEnum(
            PdfExtractionRunStatus,
            name="pdf_extraction_run_status",
            native_enum=False,
            length=32,
        ),
        default=PdfExtractionRunStatus.queued,
    )
    parser_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parser_profile: Mapped[str | None] = mapped_column(String(120), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    text_page_count: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    warnings_json: Mapped[list[dict[str, object]]] = mapped_column(
        "warnings",
        JsonObjectType,
        default=list,
    )
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    selected_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    selected_quote_id: Mapped[str | None] = mapped_column(
        ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True
    )
    selected_target_mode: Mapped[PdfExtractionTargetMode | None] = mapped_column(
        SqlEnum(
            PdfExtractionTargetMode,
            name="pdf_extraction_target_mode",
            native_enum=False,
            length=32,
        ),
        nullable=True,
    )
    review_mode: Mapped[str] = mapped_column(String(64), default="mandatory_human_review")
    acknowledged_warning_codes_json: Mapped[list[str]] = mapped_column(
        "acknowledged_warning_codes",
        JsonObjectType,
        default=list,
    )
    match_suggestions_json: Mapped[list[dict[str, object]]] = mapped_column(
        "match_suggestions",
        JsonObjectType,
        default=list,
    )
    approved_quote_id: Mapped[str | None] = mapped_column(
        ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True
    )
    approved_quote_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("quote_versions.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rejected_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    uploaded_file: Mapped[UploadedFile] = relationship(back_populates="pdf_extraction_runs")
    job: Mapped[BackgroundJob | None] = relationship()
    selected_project: Mapped[Project | None] = relationship(foreign_keys=[selected_project_id])
    selected_quote: Mapped[Quote | None] = relationship(foreign_keys=[selected_quote_id])
    approved_quote: Mapped[Quote | None] = relationship(foreign_keys=[approved_quote_id])
    approved_quote_version: Mapped[QuoteVersion | None] = relationship(
        foreign_keys=[approved_quote_version_id]
    )
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id])
    rejected_by: Mapped[User | None] = relationship(foreign_keys=[rejected_by_id])
    field_results: Mapped[list[PdfExtractionFieldResult]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    line_item_results: Mapped[list[PdfExtractionLineItemResult]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_pdf_extraction_runs_status_created_at", "status", "created_at"),
        Index("ix_pdf_extraction_runs_uploaded_file_id", "uploaded_file_id"),
        Index("ix_pdf_extraction_runs_selected_project_id", "selected_project_id"),
    )


class PdfExtractionFieldResult(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "pdf_extraction_field_results"

    run_id: Mapped[str] = mapped_column(ForeignKey("pdf_extraction_runs.id", ondelete="CASCADE"))
    source_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("pdf_extraction_field_results.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_source: Mapped[PdfExtractionResultSource] = mapped_column(
        SqlEnum(
            PdfExtractionResultSource,
            name="pdf_extraction_result_source",
            native_enum=False,
            length=32,
        ),
        default=PdfExtractionResultSource.parser,
    )
    field_path: Mapped[str] = mapped_column(String(200))
    occurrence_index: Mapped[int] = mapped_column(Integer(), default=0)
    raw_value: Mapped[str | None] = mapped_column(Text(), nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    normalized_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    normalized_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    confidence_flag: Mapped[PdfExtractionConfidenceFlag] = mapped_column(
        SqlEnum(
            PdfExtractionConfidenceFlag,
            name="pdf_extraction_confidence_flag",
            native_enum=False,
            length=16,
        )
    )
    page_number: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    source_snippet: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source_bounds: Mapped[dict[str, object] | None] = mapped_column(JsonObjectType, nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean(), default=False)
    review_status: Mapped[PdfExtractionReviewStatus] = mapped_column(
        SqlEnum(
            PdfExtractionReviewStatus,
            name="pdf_extraction_review_status",
            native_enum=False,
            length=32,
        ),
        default=PdfExtractionReviewStatus.pending,
    )
    reviewed_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reviewed_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    reviewed_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text(), nullable=True)

    run: Mapped[PdfExtractionRun] = relationship(back_populates="field_results")
    source_result: Mapped[PdfExtractionFieldResult | None] = relationship(
        remote_side="PdfExtractionFieldResult.id"
    )

    __table_args__ = (
        Index("ix_pdf_extraction_field_results_run_field_path", "run_id", "field_path"),
        Index(
            "ix_pdf_extraction_field_results_run_selected",
            "run_id",
            "field_path",
            "is_selected",
        ),
    )


class PdfExtractionLineItemResult(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "pdf_extraction_line_item_results"

    run_id: Mapped[str] = mapped_column(ForeignKey("pdf_extraction_runs.id", ondelete="CASCADE"))
    source_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("pdf_extraction_line_item_results.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_source: Mapped[PdfExtractionResultSource] = mapped_column(
        SqlEnum(
            PdfExtractionResultSource,
            name="pdf_extraction_result_source",
            native_enum=False,
            length=32,
        ),
        default=PdfExtractionResultSource.parser,
    )
    sort_order: Mapped[int] = mapped_column(Integer())
    section_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    line_type: Mapped[QuoteLineItemType] = mapped_column(
        SqlEnum(
            QuoteLineItemType,
            name="quote_line_item_type",
            native_enum=False,
            length=32,
        ),
        default=QuoteLineItemType.service,
    )
    description: Mapped[str] = mapped_column(Text())
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=1)
    unit: Mapped[str] = mapped_column(String(50))
    rate: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    confidence_flag: Mapped[PdfExtractionConfidenceFlag] = mapped_column(
        SqlEnum(
            PdfExtractionConfidenceFlag,
            name="pdf_extraction_confidence_flag",
            native_enum=False,
            length=16,
        )
    )
    page_number: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    source_snippet: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source_bounds: Mapped[dict[str, object] | None] = mapped_column(JsonObjectType, nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean(), default=True)
    review_status: Mapped[PdfExtractionReviewStatus] = mapped_column(
        SqlEnum(
            PdfExtractionReviewStatus,
            name="pdf_extraction_review_status",
            native_enum=False,
            length=32,
        ),
        default=PdfExtractionReviewStatus.pending,
    )
    reviewed_section_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_line_type: Mapped[QuoteLineItemType | None] = mapped_column(
        SqlEnum(
            QuoteLineItemType,
            name="quote_line_item_type",
            native_enum=False,
            length=32,
        ),
        nullable=True,
    )
    reviewed_description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reviewed_quantity: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    reviewed_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    reviewed_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text(), nullable=True)

    run: Mapped[PdfExtractionRun] = relationship(back_populates="line_item_results")
    source_result: Mapped[PdfExtractionLineItemResult | None] = relationship(
        remote_side="PdfExtractionLineItemResult.id"
    )

    __table_args__ = (
        Index("ix_pdf_extraction_line_item_results_run_sort_order", "run_id", "sort_order"),
        Index(
            "ix_pdf_extraction_line_item_results_run_selected",
            "run_id",
            "sort_order",
            "is_selected",
        ),
    )


class CetaImport(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "ceta_imports"

    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_file_id: Mapped[str] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="CASCADE")
    )
    source_system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_export_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    coverage_mode: Mapped[CetaImportCoverageMode] = mapped_column(
        SqlEnum(
            CetaImportCoverageMode,
            name="ceta_import_coverage_mode",
            native_enum=False,
            length=32,
        ),
        default=CetaImportCoverageMode.snapshot,
    )
    coverage_start: Mapped[date | None] = mapped_column(Date(), nullable=True)
    coverage_end: Mapped[date | None] = mapped_column(Date(), nullable=True)
    parser_profile_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parser_profile_detected: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[CetaImportStatus] = mapped_column(
        SqlEnum(CetaImportStatus, name="ceta_import_status", native_enum=False, length=32),
        default=CetaImportStatus.uploaded,
    )
    parse_summary_json: Mapped[dict[str, object]] = mapped_column(
        "parse_summary",
        JsonObjectType,
        default=dict,
    )
    review_summary_json: Mapped[dict[str, object]] = mapped_column(
        "review_summary",
        JsonObjectType,
        default=dict,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project | None] = relationship(foreign_keys=[project_id])
    uploaded_file: Mapped[UploadedFile] = relationship(back_populates="ceta_imports")
    uploaded_by: Mapped[User | None] = relationship(foreign_keys=[uploaded_by_id])
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id])
    rows: Mapped[list[CetaImportRow]] = relationship(
        back_populates="ceta_import",
        cascade="all, delete-orphan",
    )
    issues: Mapped[list[CetaImportRowIssue]] = relationship(
        back_populates="ceta_import",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_ceta_imports_status_uploaded_at", "status", "uploaded_at"),
        Index("ix_ceta_imports_project_status", "project_id", "status"),
    )


class CetaImportRow(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "ceta_import_rows"

    ceta_import_id: Mapped[str] = mapped_column(ForeignKey("ceta_imports.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer())
    source_row_uid: Mapped[str | None] = mapped_column(String(120), nullable=True)
    row_hash: Mapped[str] = mapped_column(String(64))
    business_key_hash: Mapped[str] = mapped_column(String(64))
    duplicate_group_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_project_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    normalized_project_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    work_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    posting_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    source_discipline_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    normalized_description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency_code: Mapped[str] = mapped_column(String(3))
    financial_type: Mapped[CetaRowFinancialType] = mapped_column(
        SqlEnum(
            CetaRowFinancialType,
            name="ceta_row_financial_type",
            native_enum=False,
            length=32,
        ),
        default=CetaRowFinancialType.review_required,
    )
    status: Mapped[CetaRowStatus] = mapped_column(
        SqlEnum(CetaRowStatus, name="ceta_row_status", native_enum=False, length=32),
        default=CetaRowStatus.unmatched,
    )
    suggested_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    suggested_discipline_id: Mapped[str | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="SET NULL"), nullable=True
    )
    suggested_cost_category_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suggested_revenue_category_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    matched_current_actual_id: Mapped[str | None] = mapped_column(
        ForeignKey("mapped_actuals.id", ondelete="SET NULL"), nullable=True
    )
    raw_payload_json: Mapped[dict[str, object] | None] = mapped_column(
        "raw_payload",
        JsonObjectType,
        nullable=True,
    )

    ceta_import: Mapped[CetaImport] = relationship(back_populates="rows")
    suggested_project: Mapped[Project | None] = relationship(foreign_keys=[suggested_project_id])
    suggested_discipline: Mapped[Discipline | None] = relationship(
        foreign_keys=[suggested_discipline_id]
    )
    matched_current_actual: Mapped[MappedActual | None] = relationship(
        foreign_keys=[matched_current_actual_id]
    )
    issues: Mapped[list[CetaImportRowIssue]] = relationship(
        back_populates="ceta_import_row",
        cascade="all, delete-orphan",
    )
    candidates: Mapped[list[CetaImportRowCandidate]] = relationship(
        back_populates="ceta_import_row",
        cascade="all, delete-orphan",
    )
    mapping_decisions: Mapped[list[ActualMappingDecision]] = relationship(
        back_populates="ceta_import_row",
        cascade="all, delete-orphan",
    )
    mapped_actuals: Mapped[list[MappedActual]] = relationship(
        back_populates="source_ceta_import_row",
        foreign_keys="MappedActual.source_ceta_import_row_id",
    )

    __table_args__ = (
        Index("ix_ceta_import_rows_import_row_number", "ceta_import_id", "row_number", unique=True),
        Index("ix_ceta_import_rows_status_work_date", "status", "work_date"),
        Index("ix_ceta_import_rows_external_project_code", "external_project_code"),
        Index("ix_ceta_import_rows_business_key_hash", "business_key_hash"),
        Index("ix_ceta_import_rows_row_hash", "row_hash"),
    )


class CetaImportRowIssue(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "ceta_import_row_issues"

    ceta_import_id: Mapped[str] = mapped_column(ForeignKey("ceta_imports.id", ondelete="CASCADE"))
    ceta_import_row_id: Mapped[str | None] = mapped_column(
        ForeignKey("ceta_import_rows.id", ondelete="CASCADE"),
        nullable=True,
    )
    severity: Mapped[CetaImportIssueSeverity] = mapped_column(
        SqlEnum(
            CetaImportIssueSeverity,
            name="ceta_import_issue_severity",
            native_enum=False,
            length=16,
        )
    )
    issue_code: Mapped[str] = mapped_column(String(120))
    field_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    message: Mapped[str] = mapped_column(Text())
    details_json: Mapped[dict[str, object] | None] = mapped_column(
        "details",
        JsonObjectType,
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    ceta_import: Mapped[CetaImport] = relationship(back_populates="issues")
    ceta_import_row: Mapped[CetaImportRow | None] = relationship(back_populates="issues")
    resolved_by: Mapped[User | None] = relationship(foreign_keys=[resolved_by_id])

    __table_args__ = (
        Index("ix_ceta_import_row_issues_import_row", "ceta_import_id", "ceta_import_row_id"),
        Index("ix_ceta_import_row_issues_severity_issue_code", "severity", "issue_code"),
    )


class CetaImportRowCandidate(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "ceta_import_row_candidates"

    ceta_import_row_id: Mapped[str] = mapped_column(
        ForeignKey("ceta_import_rows.id", ondelete="CASCADE")
    )
    dimension: Mapped[CetaImportCandidateDimension] = mapped_column(
        SqlEnum(
            CetaImportCandidateDimension,
            name="ceta_import_candidate_dimension",
            native_enum=False,
            length=32,
        )
    )
    target_type: Mapped[str] = mapped_column(String(80))
    target_key: Mapped[str] = mapped_column(String(120))
    target_label: Mapped[str] = mapped_column(String(255))
    candidate_source: Mapped[str] = mapped_column(String(80))
    score: Mapped[float] = mapped_column(Numeric(5, 2))
    explanation: Mapped[str] = mapped_column(Text())
    sort_order: Mapped[int] = mapped_column(Integer(), default=0)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JsonObjectType,
        nullable=True,
    )

    ceta_import_row: Mapped[CetaImportRow] = relationship(back_populates="candidates")

    __table_args__ = (
        Index(
            "ix_ceta_import_row_candidates_row_dimension_sort",
            "ceta_import_row_id",
            "dimension",
            "sort_order",
        ),
    )


class ProjectExternalReference(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "project_external_references"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    source_system: Mapped[str] = mapped_column(String(100))
    external_value: Mapped[str] = mapped_column(String(255))
    normalized_external_value: Mapped[str] = mapped_column(String(255))
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    project: Mapped[Project] = relationship(foreign_keys=[project_id])
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])

    __table_args__ = (
        Index(
            "ix_project_external_references_source_value",
            "source_system",
            "normalized_external_value",
        ),
        Index(
            "ix_project_external_references_project_source_value",
            "project_id",
            "source_system",
            "normalized_external_value",
            unique=True,
        ),
    )


class ReferenceTermAlias(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "reference_term_aliases"

    category: Mapped[str] = mapped_column(String(100))
    alias_text: Mapped[str] = mapped_column(String(255))
    normalized_alias_text: Mapped[str] = mapped_column(String(255))
    canonical_key: Mapped[str] = mapped_column(String(100))
    source_system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_field_path: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence_hint: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])

    __table_args__ = (
        Index(
            "ix_reference_term_aliases_category_alias",
            "category",
            "normalized_alias_text",
        ),
        Index(
            "ix_reference_term_aliases_category_source_field_alias",
            "category",
            "source_system",
            "source_field_path",
            "normalized_alias_text",
            unique=True,
        ),
    )


class ActualMappingRule(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "actual_mapping_rules"

    source_system: Mapped[str] = mapped_column(String(100))
    scope_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_name: Mapped[str] = mapped_column(String(255))
    financial_type: Mapped[CetaRowFinancialType | None] = mapped_column(
        SqlEnum(
            CetaRowFinancialType,
            name="ceta_row_financial_type",
            native_enum=False,
            length=32,
        ),
        nullable=True,
    )
    vendor_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_project_code_pattern: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    source_discipline_code_pattern: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    target_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_discipline_id: Mapped[str | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="SET NULL"),
        nullable=True,
    )
    cost_category_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revenue_category_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    scope_project: Mapped[Project | None] = relationship(foreign_keys=[scope_project_id])
    target_project: Mapped[Project | None] = relationship(foreign_keys=[target_project_id])
    target_discipline: Mapped[Discipline | None] = relationship(foreign_keys=[target_discipline_id])
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_actual_mapping_rules_source_system_active", "source_system", "is_active"),
        Index("ix_actual_mapping_rules_scope_project", "scope_project_id"),
    )


class ActualMappingDecision(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "actual_mapping_decisions"

    ceta_import_row_id: Mapped[str] = mapped_column(
        ForeignKey("ceta_import_rows.id", ondelete="CASCADE")
    )
    mapped_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    mapped_discipline_id: Mapped[str | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="SET NULL"),
        nullable=True,
    )
    financial_type: Mapped[CetaRowFinancialType | None] = mapped_column(
        SqlEnum(
            CetaRowFinancialType,
            name="ceta_row_financial_type",
            native_enum=False,
            length=32,
        ),
        nullable=True,
    )
    cost_category_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revenue_category_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approval_action: Mapped[ActualMappingApprovalAction] = mapped_column(
        SqlEnum(
            ActualMappingApprovalAction,
            name="actual_mapping_approval_action",
            native_enum=False,
            length=32,
        )
    )
    decision_status: Mapped[ActualMappingDecisionStatus] = mapped_column(
        SqlEnum(
            ActualMappingDecisionStatus,
            name="actual_mapping_decision_status",
            native_enum=False,
            length=32,
        ),
        default=ActualMappingDecisionStatus.approved,
    )
    mapping_method: Mapped[MappingMethod] = mapped_column(
        SqlEnum(MappingMethod, name="mapping_method", native_enum=False, length=32),
        default=MappingMethod.manual,
    )
    matched_existing_actual_id: Mapped[str | None] = mapped_column(
        ForeignKey("mapped_actuals.id", ondelete="SET NULL"),
        nullable=True,
    )
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    explanation_json: Mapped[dict[str, object] | None] = mapped_column(
        "explanation",
        JsonObjectType,
        nullable=True,
    )
    created_rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("actual_mapping_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_alias_id: Mapped[str | None] = mapped_column(
        ForeignKey("reference_term_aliases.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_external_reference_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_external_references.id", ondelete="SET NULL"),
        nullable=True,
    )
    mapped_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    ceta_import_row: Mapped[CetaImportRow] = relationship(back_populates="mapping_decisions")
    mapped_project: Mapped[Project | None] = relationship(foreign_keys=[mapped_project_id])
    mapped_discipline: Mapped[Discipline | None] = relationship(foreign_keys=[mapped_discipline_id])
    matched_existing_actual: Mapped[MappedActual | None] = relationship(
        foreign_keys=[matched_existing_actual_id]
    )
    created_rule: Mapped[ActualMappingRule | None] = relationship(foreign_keys=[created_rule_id])
    created_alias: Mapped[ReferenceTermAlias | None] = relationship(foreign_keys=[created_alias_id])
    created_external_reference: Mapped[ProjectExternalReference | None] = relationship(
        foreign_keys=[created_external_reference_id]
    )
    mapped_by: Mapped[User | None] = relationship(foreign_keys=[mapped_by_id])
    approved_mapped_actuals: Mapped[list[MappedActual]] = relationship(
        back_populates="mapping_decision",
        foreign_keys="MappedActual.mapping_decision_id",
    )

    __table_args__ = (
        Index("ix_actual_mapping_decisions_row_created_at", "ceta_import_row_id", "created_at"),
        Index("ix_actual_mapping_decisions_project_created_at", "mapped_project_id", "created_at"),
    )


class MappedActual(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "mapped_actuals"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    discipline_id: Mapped[str | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_ceta_import_id: Mapped[str | None] = mapped_column(
        ForeignKey("ceta_imports.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_ceta_import_row_id: Mapped[str | None] = mapped_column(
        ForeignKey("ceta_import_rows.id", ondelete="SET NULL"),
        nullable=True,
    )
    mapping_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("actual_mapping_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    work_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    posting_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency_code: Mapped[str] = mapped_column(String(3))
    financial_type: Mapped[CetaRowFinancialType] = mapped_column(
        SqlEnum(
            CetaRowFinancialType,
            name="ceta_row_financial_type",
            native_enum=False,
            length=32,
        )
    )
    cost_category_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revenue_category_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actual_business_key: Mapped[str] = mapped_column(String(64))
    supersedes_mapped_actual_id: Mapped[str | None] = mapped_column(
        ForeignKey("mapped_actuals.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_current: Mapped[bool] = mapped_column(Boolean(), default=True)
    change_type: Mapped[MappedActualChangeType] = mapped_column(
        SqlEnum(
            MappedActualChangeType,
            name="mapped_actual_change_type",
            native_enum=False,
            length=32,
        ),
        default=MappedActualChangeType.new,
    )
    mapped_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    mapped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(foreign_keys=[project_id])
    discipline: Mapped[Discipline | None] = relationship(foreign_keys=[discipline_id])
    source_ceta_import: Mapped[CetaImport | None] = relationship(
        foreign_keys=[source_ceta_import_id]
    )
    source_ceta_import_row: Mapped[CetaImportRow | None] = relationship(
        back_populates="mapped_actuals",
        foreign_keys=[source_ceta_import_row_id],
    )
    mapping_decision: Mapped[ActualMappingDecision | None] = relationship(
        back_populates="approved_mapped_actuals",
        foreign_keys=[mapping_decision_id],
    )
    supersedes_mapped_actual: Mapped[MappedActual | None] = relationship(
        remote_side="MappedActual.id",
        foreign_keys=[supersedes_mapped_actual_id],
    )
    mapped_by: Mapped[User | None] = relationship(foreign_keys=[mapped_by_id])

    __table_args__ = (
        Index("ix_mapped_actuals_project_work_date", "project_id", "work_date"),
        Index("ix_mapped_actuals_discipline_work_date", "discipline_id", "work_date"),
        Index("ix_mapped_actuals_business_key_current", "actual_business_key", "is_current"),
    )
