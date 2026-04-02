from __future__ import annotations

from enum import StrEnum


class AuthInvitationStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"


class BackgroundJobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class PdfExtractionConfidenceFlag(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class PdfExtractionResultSource(StrEnum):
    parser = "parser"
    reviewer = "reviewer"


class PdfExtractionReviewStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class PdfExtractionRunStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"
    failed = "failed"


class PdfExtractionTargetMode(StrEnum):
    new_quote = "new_quote"
    new_version = "new_version"


class CetaImportCoverageMode(StrEnum):
    snapshot = "snapshot"
    incremental = "incremental"


class CetaImportStatus(StrEnum):
    uploaded = "uploaded"
    parsed = "parsed"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"
    failed = "failed"


class CetaRowFinancialType(StrEnum):
    cost = "cost"
    revenue = "revenue"
    review_required = "review_required"


class CetaRowStatus(StrEnum):
    unmatched = "unmatched"
    suggested = "suggested"
    mapped = "mapped"
    approved = "approved"
    rejected = "rejected"


class CetaImportIssueSeverity(StrEnum):
    fatal = "fatal"
    blocking = "blocking"
    warning = "warning"
    info = "info"


class CetaImportCandidateDimension(StrEnum):
    project = "project"
    discipline = "discipline"
    cost_category = "cost_category"
    revenue_category = "revenue_category"
    financial_type = "financial_type"


class CompanyClassificationType(StrEnum):
    client = "client"
    production_company = "production_company"
    studio = "studio"
    streamer = "streamer"
    broadcaster = "broadcaster"
    competitor = "competitor"
    vendor = "vendor"


class ForecastAllocationMethod(StrEnum):
    schedule = "schedule"
    manual = "manual"


class RevenueAllocationMethod(StrEnum):
    cadence_profile = "cadence_profile"


class BenchmarkActualsStatus(StrEnum):
    none = "none"
    partial = "partial"
    complete = "complete"


class ForecastVersionStatus(StrEnum):
    draft = "draft"
    submitted = "submitted"
    locked = "locked"
    superseded = "superseded"


class ProjectOutcomeType(StrEnum):
    bid = "bid"
    awarded = "awarded"
    lost = "lost"


class ProjectPartyRole(StrEnum):
    client = "client"
    production_company = "production_company"
    studio = "studio"
    streamer = "streamer"
    broadcaster = "broadcaster"
    competitor = "competitor"


class ProjectStatus(StrEnum):
    bid = "bid"
    awarded = "awarded"
    lost = "lost"
    active = "active"
    complete = "complete"
    archived = "archived"


class QuoteLineItemType(StrEnum):
    service = "service"
    expense = "expense"
    discount = "discount"
    adjustment = "adjustment"


class ComparableProjectLinkDisposition(StrEnum):
    pinned = "pinned"
    excluded = "excluded"


class MappingMethod(StrEnum):
    manual = "manual"
    suggested = "suggested"
    rule = "rule"


class ActualMappingDecisionStatus(StrEnum):
    suggested = "suggested"
    approved = "approved"
    rejected = "rejected"


class ActualMappingApprovalAction(StrEnum):
    post_new = "post_new"
    supersede_existing = "supersede_existing"
    link_existing = "link_existing"
    reject = "reject"


class MappedActualChangeType(StrEnum):
    new = "new"
    corrected = "corrected"
    withdrawn = "withdrawn"
    repeat_linked = "repeat_linked"


class QuoteVersionStatus(StrEnum):
    draft = "draft"
    issued = "issued"
    superseded = "superseded"
    accepted = "accepted"
    rejected = "rejected"


class UploadedFileCategory(StrEnum):
    quote_pdf = "quote_pdf"
    quote_attachment = "quote_attachment"
    issued_quote_pdf = "issued_quote_pdf"
    ceta_export = "ceta_export"
    project_attachment = "project_attachment"
    forecast_attachment = "forecast_attachment"
    other = "other"


class UploadedFileStatus(StrEnum):
    awaiting_upload = "awaiting_upload"
    uploaded = "uploaded"
