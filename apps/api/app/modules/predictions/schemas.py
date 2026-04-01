from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.schemas import BaseSchema
from app.modules.comparables.schemas import (
    ActualInformedRangeSummary,
    ComparableRangeSummary,
    ComparableTargetSummary,
    RiskSignal,
)


class PredictionModelInfo(BaseSchema):
    strategy: str
    refreshed_at: datetime
    update_approach: str
    comparable_projects_considered: int
    comparable_projects_used: int
    complete_actual_history_count: int
    monthly_profile_count: int


class PredictionTopFactor(BaseSchema):
    key: str
    label: str
    impact: str
    detail: str


class PredictionComparableEvidence(BaseSchema):
    project_id: str | None = None
    project_name: str
    similarity_score: float
    strength: str
    selection_state: str
    is_primary: bool = False
    evidence: list[PredictionTopFactor] = Field(default_factory=list)


class PredictiveQuoteGuidance(BaseSchema):
    basis: str
    confidence: str
    low: float
    median: float
    high: float
    currency_code: str
    sample_size: int
    comparable_project_ids: list[str]
    methodology: str
    applied_variance_median_pct: float | None = None
    quoted_amount: float | None = None
    recommended_low: float | None = None
    recommended_median: float | None = None
    recommended_high: float | None = None
    quote_position: str | None = None
    omitted_discipline_ids: list[str] = Field(default_factory=list)
    acceptance_status: str | None = None
    reasoning: list[str]


class PredictiveDisciplineUsage(BaseSchema):
    discipline_id: str
    discipline_code: str | None = None
    discipline_name: str | None = None
    sample_size: int
    usage_rate_pct: float
    predicted_share_pct: float
    quoted_amount: float | None = None
    predicted_amount_low: float | None = None
    predicted_amount_median: float | None = None
    predicted_amount_high: float | None = None
    predicted_actual_amount: float | None = None
    predicted_variance_pct: float | None = None
    observed_variance_median_pct: float | None = None
    confidence: str
    confidence_score: float | None = None
    data_sufficiency_score: float | None = None
    fallback_tier: str | None = None
    overrun_risk: str = "low"
    is_target_discipline: bool
    comparable_project_ids: list[str]
    key_drivers: list[str] = Field(default_factory=list)
    reasoning: list[str]


class PredictiveMonthlyRevenueSpread(BaseSchema):
    month: str
    sample_size: int
    low_share_pct: float
    median_share_pct: float
    high_share_pct: float
    predicted_amount_low: float | None = None
    predicted_amount_median: float | None = None
    predicted_amount_high: float | None = None
    confidence: str
    fallback_tier: str | None = None
    spread_profile: str | None = None
    comparable_project_ids: list[str]
    reasoning: list[str]


class OverrunRiskFlag(BaseSchema):
    key: str
    severity: str
    title: str
    detail: str
    confidence: str
    comparable_project_ids: list[str]
    reasoning: list[str]


class OverrunRiskSummary(BaseSchema):
    level: str
    flags: list[OverrunRiskFlag]


class PredictionWinProbabilityFactor(BaseSchema):
    key: str
    label: str
    effect: float
    detail: str


class PredictionWinProbability(BaseSchema):
    probability_pct: float
    probability_band: str
    confidence: str
    confidence_score: float
    fallback_tier: str
    key_factors: list[PredictionWinProbabilityFactor]
    override_status: str | None = None
    reasoning: list[str]


class PredictionScenarioRead(BaseSchema):
    id: str | None = None
    scenario_key: str
    title: str
    is_expected: bool = False
    updated_at: datetime | None = None
    assumption_overrides: dict[str, object] = Field(default_factory=dict)
    likely_quote_range: PredictiveQuoteGuidance | None = None
    discipline_usage: list[PredictiveDisciplineUsage] = Field(default_factory=list)
    monthly_revenue_spread: list[PredictiveMonthlyRevenueSpread] = Field(default_factory=list)
    overrun_risk: OverrunRiskSummary
    win_probability: PredictionWinProbability | None = None
    projected_total_revenue: float | None = None
    projected_weighted_revenue: float | None = None
    promoted_forecast_version_id: str | None = None
    promoted_at: datetime | None = None


class PredictionModuleOutputRead(BaseSchema):
    module_key: str
    model_module: str
    fallback_tier: str
    confidence_score: float
    data_sufficiency_score: float
    confidence_label: str
    output: dict[str, object]
    explanations: list[PredictionTopFactor] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)


class PredictionOverrideRead(BaseSchema):
    id: str
    module_key: str
    scenario_key: str | None = None
    target_key: str
    status: str
    override_value: dict[str, object] | None = None
    note: str | None = None
    actor_id: str | None = None
    decided_at: datetime


class PredictionEvaluationRead(BaseSchema):
    id: str
    module_key: str
    scenario_key: str | None = None
    metric_key: str
    predicted_value: dict[str, object] | None = None
    actual_value: dict[str, object] | None = None
    error_value: float | None = None
    calibration_bucket: str | None = None
    note: str | None = None
    outcome_recorded_at: datetime | None = None


class PredictionRunSummaryRead(BaseSchema):
    id: str
    project_id: str
    quote_version_id: str | None = None
    forecast_version_id: str | None = None
    model_version: str
    strategy_key: str
    maturity_stage: str
    primary_evidence_source: str
    fallback_tier: str
    feature_readiness_score: float
    data_sufficiency_score: float
    confidence_score: float
    confidence_label: str
    expected_scenario_key: str
    methodology_summary: str
    generated_at: datetime
    created_at: datetime
    updated_at: datetime


class PredictionRunListResponse(BaseSchema):
    items: list[PredictionRunSummaryRead]


class PredictionRunDetailRead(PredictionRunSummaryRead):
    target: ComparableTargetSummary
    model_info: PredictionModelInfo
    comparable_quote_range: ComparableRangeSummary | None = None
    actual_informed_quote_range: ActualInformedRangeSummary | None = None
    likely_quote_range: PredictiveQuoteGuidance | None = None
    discipline_usage: list[PredictiveDisciplineUsage]
    monthly_revenue_spread: list[PredictiveMonthlyRevenueSpread]
    overrun_risk: OverrunRiskSummary
    risk_signals: list[RiskSignal]
    methodology_summary: str
    win_probability: PredictionWinProbability | None = None
    scenarios: list[PredictionScenarioRead] = Field(default_factory=list)
    top_comparables: list[PredictionComparableEvidence] = Field(default_factory=list)
    module_outputs: list[PredictionModuleOutputRead] = Field(default_factory=list)
    overrides: list[PredictionOverrideRead] = Field(default_factory=list)
    evaluations: list[PredictionEvaluationRead] = Field(default_factory=list)
    missing_critical_inputs: list[str] = Field(default_factory=list)
    feature_snapshot: dict[str, object] = Field(default_factory=dict)
    request_context: dict[str, object] = Field(default_factory=dict)
    source_references: list[dict[str, object]] = Field(default_factory=list)


class ProjectPredictiveGuidanceResponse(PredictionRunDetailRead):
    pass


class PredictionRunCreateRequest(BaseSchema):
    quote_version_id: str | None = None
    discipline_id: str | None = None
    limit: int = Field(default=25, ge=1, le=25)
    scenario_assumptions: dict[str, dict[str, object]] | None = None
    force_refresh: bool = False


class PredictionOverrideWrite(BaseSchema):
    module_key: str
    scenario_key: str | None = None
    target_key: str
    status: str
    override_value: dict[str, object] | None = None
    note: str | None = None


class PredictionOverridesPatchRequest(BaseSchema):
    items: list[PredictionOverrideWrite] = Field(default_factory=list)


class PredictionScenarioUpdateRequest(BaseSchema):
    expected_updated_at: datetime
    assumption_overrides: dict[str, object] = Field(default_factory=dict)


class PredictionScenarioPromoteRequest(BaseSchema):
    scenario_key: str
    title: str | None = None
    notes_text: str | None = None
    revision_reason: str | None = None
    probability_percent: float | None = Field(default=None, ge=0, le=100)


class PredictionScenarioPromotionResponse(BaseSchema):
    prediction_run_id: str
    scenario_key: str
    promoted_forecast_version_id: str
    promoted_at: datetime
