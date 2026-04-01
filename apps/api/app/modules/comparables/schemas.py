from __future__ import annotations

from pydantic import Field

from app.core.schemas import BaseSchema


class ComparableTargetSummary(BaseSchema):
    project_id: str
    project_name: str
    quote_currency_code: str
    quote_version_id: str | None = None
    project_format_key: str | None = None


class RiskSignal(BaseSchema):
    key: str
    severity: str
    detail: str


class ComparableFactorMatch(BaseSchema):
    factor_key: str
    label: str
    weight: int
    awarded_points: float
    detail: str


class DisciplineBenchmarkSummary(BaseSchema):
    discipline_id: str
    discipline_name: str | None = None
    quoted_amount: float
    actual_amount: float | None = None
    quote_to_actual_variance_amount: float | None = None
    quote_to_actual_variance_pct: float | None = None
    actuals_status: str


class BenchmarkSummary(BaseSchema):
    source_quote_version_id: str | None = None
    currency_code: str
    quoted_amount: float
    actual_amount: float | None = None
    quote_to_actual_variance_amount: float | None = None
    quote_to_actual_variance_pct: float | None = None
    actuals_status: str
    actuals_as_of_date: str | None = None
    discipline_summaries: list[DisciplineBenchmarkSummary]


class ComparableProjectItem(BaseSchema):
    project_id: str
    project_name: str
    status: str
    client_name: str | None = None
    similarity_score: float
    coverage_pct: float
    strength: str
    selection_state: str
    matched_factors: list[ComparableFactorMatch]
    benchmark_summary: BenchmarkSummary | None = None
    discipline_benchmark_summaries: list[DisciplineBenchmarkSummary]
    is_eligible_for_recommendations: bool


class ProjectComparablesResponse(BaseSchema):
    target: ComparableTargetSummary
    scoring_model_version: str
    risk_signals: list[RiskSignal]
    items: list[ComparableProjectItem]


class ComparableRangeSummary(BaseSchema):
    low: float
    median: float
    high: float
    currency_code: str
    sample_size: int
    comparable_project_ids: list[str]
    methodology: str


class ActualInformedRangeSummary(ComparableRangeSummary):
    variance_low_pct: float
    variance_median_pct: float
    variance_high_pct: float


class DisciplineRangeSummary(ComparableRangeSummary):
    discipline_id: str
    discipline_name: str | None = None
    observed_variance_median_pct: float | None = None


class ProjectRecommendationsResponse(BaseSchema):
    target: ComparableTargetSummary
    scoring_model_version: str
    overall_quote_range: ComparableRangeSummary | None = None
    overall_actual_informed_range: ActualInformedRangeSummary | None = None
    discipline_ranges: list[DisciplineRangeSummary]
    comparables_used: list[str]
    risk_signals: list[RiskSignal]
    methodology_summary: str


class ComparableSelectionUpdateRequest(BaseSchema):
    pinned_project_ids: list[str] = Field(default_factory=list)
    excluded_project_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class ComparableSelectionUpdateResponse(BaseSchema):
    pinned_project_ids: list[str]
    excluded_project_ids: list[str]
    note: str | None = None
    updated_at: str
