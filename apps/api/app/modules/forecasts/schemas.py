from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.schemas import BaseSchema


class ForecastMonthlyAllocationRead(BaseSchema):
    month: str
    amount: float
    weighted_amount: float
    low_amount: float | None = None
    high_amount: float | None = None
    actual_amount: float | None = None
    allocation_source: str | None = None
    source_context: dict[str, object] | None = None
    is_manual_override: bool = False
    is_locked: bool = False
    manual_note: str | None = None


class ForecastExplanationRead(BaseSchema):
    key: str
    label: str
    impact: str
    detail: str


class ForecastSanityCheckRead(BaseSchema):
    key: str
    severity: str
    scope: str
    title: str
    detail: str
    recommendation: str | None = None
    blocking: bool = False
    line_id: str | None = None
    month: str | None = None


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
    forecast_method_key: str | None = None
    allocation_profile_key: str | None = None
    sequencing_template_key: str | None = None
    sequencing_stage_key: str | None = None
    overlap_percent: float | None = None
    confidence_score: float | None = None
    data_sufficiency_score: float | None = None
    fallback_tier: str | None = None
    actuals_to_date_amount: float | None = None
    remaining_amount: float | None = None
    forecast_inputs: dict[str, object] | None = None
    explanations: list[ForecastExplanationRead]
    sanity_checks: list[ForecastSanityCheckRead] = Field(default_factory=list)
    issues: list[str]
    allocations: list[ForecastMonthlyAllocationRead]


class ForecastDisciplineMonthlyRollupRead(BaseSchema):
    discipline_id: str | None = None
    month: str
    amount: float
    weighted_amount: float
    low_amount: float | None = None
    high_amount: float | None = None
    actual_amount: float | None = None


class ForecastProjectMonthlyRollupRead(BaseSchema):
    month: str
    amount: float
    weighted_amount: float
    low_amount: float | None = None
    high_amount: float | None = None
    actual_amount: float | None = None


class ForecastDashboardMonthValueRead(BaseSchema):
    month: str
    amount: float
    weighted_amount: float
    actual_amount: float | None = None
    booked_amount: float | None = None


class ForecastDashboardOverrideFlagsRead(BaseSchema):
    has_manual_overrides: bool = False
    has_locked_months: bool = False
    has_actualized_months: bool = False


class ForecastDashboardDisciplineRowRead(BaseSchema):
    discipline_id: str
    discipline_name: str
    allocation_method_used: str
    allocation_profile_key: str | None = None
    line_count: int
    manual_override_line_count: int
    total_amount: float
    weighted_total_amount: float
    month_values: list[ForecastDashboardMonthValueRead] = Field(default_factory=list)


class ForecastDashboardProjectProjectionRead(BaseSchema):
    project_id: str
    project_name: str
    client_id: str | None = None
    client_name: str | None = None
    currency_code: str = "GBP"
    commercial_status: str
    operational_status: str
    quote_version_id: str | None = None
    source_quote_version_id: str | None = None
    is_source_quote_current: bool = True
    forecast_version_id: str | None = None
    forecast_status: str | None = None
    scenario_key: str = "base"
    total_project_value: float
    forecast_total_value: float
    weighted_forecast_total_value: float
    probability_percent: float
    execution_start_date: str | None = None
    execution_end_date: str | None = None
    allocation_method_used: str
    allocation_profile_key: str | None = None
    base_phasing_profile: str | None = None
    manual_override_line_count: int = 0
    override_flags: ForecastDashboardOverrideFlagsRead
    confidence_score: float | None = None
    data_sufficiency_score: float | None = None
    fallback_tier: str | None = None
    change_summary: dict[str, object] | None = None
    explanation_summary: dict[str, object] | None = None
    issues: list[str] = Field(default_factory=list)
    project_months: list[ForecastDashboardMonthValueRead] = Field(default_factory=list)
    discipline_rows: list[ForecastDashboardDisciplineRowRead] = Field(default_factory=list)


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
    scenario_key: str = "base"
    engine_source: str = "unified_forecast_engine"
    prediction_run_id: str | None = None
    prediction_scenario_key: str | None = None
    confidence_score: float | None = None
    data_sufficiency_score: float | None = None
    fallback_tier: str | None = None
    change_summary: dict[str, object] | None = None
    source_quote_version_id: str | None = None
    is_source_quote_current: bool
    created_at: datetime
    updated_at: datetime


class ForecastVersionRead(ForecastVersionSummaryRead):
    notes_text: str | None = None
    revision_reason: str | None = None
    parent_version_id: str | None = None
    explanation_summary: dict[str, object] | None = None
    sanity_checks: list[ForecastSanityCheckRead] = Field(default_factory=list)
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
    sanity_checks: list[ForecastSanityCheckRead] = Field(default_factory=list)


class ForecastPhasingFilterOption(BaseSchema):
    id: str
    label: str


class ForecastPhasingFilterOptions(BaseSchema):
    clients: list[ForecastPhasingFilterOption]
    projects: list[ForecastPhasingFilterOption]
    disciplines: list[ForecastPhasingFilterOption]
    statuses: list[ForecastPhasingFilterOption]
    scenarios: list[ForecastPhasingFilterOption]


class ForecastPhasingCellRead(BaseSchema):
    month: str
    amount: float
    weighted_amount: float
    actual_amount: float | None = None
    low_amount: float | None = None
    high_amount: float | None = None
    allocation_source: str | None = None
    is_manual_override: bool = False
    is_locked: bool = False
    editable: bool = True
    manual_note: str | None = None


class ForecastPhasingCellWrite(BaseSchema):
    month: str
    amount: float = Field(ge=0)
    is_locked: bool = False
    note: str | None = None


class ForecastPhasingDraftStateRead(BaseSchema):
    forecast_version_id: str | None = None
    expected_updated_at: datetime
    reason: str | None = None
    cells: list[ForecastPhasingCellWrite] = Field(default_factory=list)


class ForecastPhasingDraftRead(BaseSchema):
    id: str
    forecast_version_id: str
    project_id: str
    row_mode: str
    discipline_id: str | None = None
    save_mode: str = "replace"
    current_state: ForecastPhasingDraftStateRead
    past_states: list[ForecastPhasingDraftStateRead] = Field(default_factory=list)
    future_states: list[ForecastPhasingDraftStateRead] = Field(default_factory=list)
    updated_by_id: str | None = None
    updated_by_email: str | None = None
    updated_at: datetime


class ForecastPhasingMonthTotalRead(BaseSchema):
    month: str
    amount: float
    weighted_amount: float


class ForecastPhasingStatusMonthTotalRead(BaseSchema):
    status: str
    month: str
    amount: float
    weighted_amount: float


class ForecastPhasingRowRead(BaseSchema):
    row_key: str
    row_mode: str
    project_id: str
    project_name: str
    client_id: str | None = None
    client_name: str | None = None
    status: str
    discipline_id: str | None = None
    discipline_name: str | None = None
    forecast_version_id: str | None = None
    forecast_version_status: str | None = None
    forecast_version_updated_at: datetime | None = None
    scenario_key: str = "base"
    currency_code: str = "GBP"
    base_phasing_profile: str | None = None
    execution_start_date: str | None = None
    execution_end_date: str | None = None
    total_amount: float
    weighted_total_amount: float
    can_edit: bool = False
    cells: list[ForecastPhasingCellRead] = Field(default_factory=list)
    active_draft: ForecastPhasingDraftRead | None = None


class ForecastPhasingChangeRead(BaseSchema):
    id: str
    project_id: str
    forecast_version_id: str
    row_mode: str
    month: str
    discipline_id: str | None = None
    before_amount: float
    after_amount: float
    before_locked: bool = False
    after_locked: bool = False
    source_method: str
    reason: str | None = None
    note: str | None = None
    actor_id: str | None = None
    actor_email: str | None = None
    created_at: datetime


class ForecastPhasingWorkspaceRead(BaseSchema):
    generated_at: datetime
    from_month: str
    to_month: str
    row_mode: str
    scenario_key: str = "base"
    filter_options: ForecastPhasingFilterOptions
    months: list[str]
    rows: list[ForecastPhasingRowRead]
    month_totals: list[ForecastPhasingMonthTotalRead]
    status_month_totals: list[ForecastPhasingStatusMonthTotalRead]
    recent_changes: list[ForecastPhasingChangeRead] = Field(default_factory=list)


DashboardForecastStatus = Literal["estimated", "awarded", "lost"]
DashboardForecastAllocationMethod = Literal["schedule", "manual"]


class DashboardForecastProjectRead(BaseSchema):
    project_id: str
    project_name: str
    client: str
    client_id: str | None = None
    client_name: str | None = None
    status: DashboardForecastStatus
    operational_status: str
    quote_version_id: str | None = None
    source_quote_version_id: str | None = None
    is_source_quote_current: bool = True
    forecast_version_id: str | None = None
    forecast_status: str | None = None
    scenario_key: str = "base"
    execution_start_date: str | None = None
    execution_end_date: str | None = None
    total_project_value: float = 0
    total_forecast_value: float
    window_forecast_value: float = 0
    weighted_total_forecast_value: float = 0
    window_weighted_forecast_value: float = 0
    probability_percent: float = 0
    allocation_method_used: str = "none"
    allocation_profile_key: str | None = None
    base_phasing_profile: str | None = None
    manual_override_line_count: int = 0
    override_flags: ForecastDashboardOverrideFlagsRead = Field(
        default_factory=ForecastDashboardOverrideFlagsRead
    )
    confidence_score: float | None = None
    data_sufficiency_score: float | None = None
    fallback_tier: str | None = None
    change_summary: dict[str, object] | None = None
    explanation_summary: dict[str, object] | None = None
    issues: list[str] = Field(default_factory=list)
    project_months: list[ForecastDashboardMonthValueRead] = Field(default_factory=list)
    discipline_rows: list[ForecastDashboardDisciplineRowRead] = Field(default_factory=list)


class DashboardForecastProjectContractRead(BaseSchema):
    project_id: str
    project_name: str
    client: str
    status: DashboardForecastStatus
    execution_start_date: str | None = None
    execution_end_date: str | None = None
    total_forecast_value: float


class DashboardForecastMonthRowRead(BaseSchema):
    month: str
    revenue_value: float
    project_id: str
    discipline: str | None = None
    allocation_method: DashboardForecastAllocationMethod
    override_flag: bool = False


class DashboardForecastMonthTotalRead(BaseSchema):
    month: str
    revenue_value: float


class DashboardForecastStatusTotalRead(BaseSchema):
    status: DashboardForecastStatus
    revenue_value: float


class DashboardForecastDisciplineTotalRead(BaseSchema):
    discipline: str | None = None
    revenue_value: float


class DashboardForecastAggregationsRead(BaseSchema):
    totals_by_month: list[DashboardForecastMonthTotalRead]
    totals_by_status: list[DashboardForecastStatusTotalRead]
    totals_by_discipline: list[DashboardForecastDisciplineTotalRead]


class DashboardForecastDatasetRead(BaseSchema):
    generated_at: datetime
    currency_code: str
    from_month: str
    to_month: str
    scenario_key: str
    projects: list[DashboardForecastProjectRead]
    monthly_rows: list[DashboardForecastMonthRowRead]
    aggregations: DashboardForecastAggregationsRead


class DashboardForecastDatasetContractRead(BaseSchema):
    generated_at: datetime
    currency_code: str
    from_month: str
    to_month: str
    scenario_key: str
    projects: list[DashboardForecastProjectContractRead]
    monthly_rows: list[DashboardForecastMonthRowRead]
    aggregations: DashboardForecastAggregationsRead


class ForecastPhasingDraftStateWrite(BaseSchema):
    forecast_version_id: str | None = None
    expected_updated_at: datetime
    reason: str | None = None
    cells: list[ForecastPhasingCellWrite] = Field(default_factory=list)


class ForecastPhasingPreviewRequest(BaseSchema):
    project_id: str
    row_mode: str
    discipline_id: str | None = None
    from_month: str
    to_month: str
    action: str
    locked_months: list[str] = Field(default_factory=list)
    cadence_profile_type: str | None = None


class ForecastPhasingPreviewRead(BaseSchema):
    project_id: str
    row_mode: str
    discipline_id: str | None = None
    action: str
    cells: list[ForecastPhasingCellWrite] = Field(default_factory=list)


class ForecastPhasingRowUpdateRequest(BaseSchema):
    forecast_version_id: str | None = None
    expected_updated_at: datetime
    row_mode: str
    discipline_id: str | None = None
    cells: list[ForecastPhasingCellWrite] = Field(default_factory=list)
    replace_existing_overrides: bool = True
    source_method: str = "manual_cells"
    reason: str | None = None


class ForecastPhasingDraftUpsertRequest(BaseSchema):
    row_mode: str
    discipline_id: str | None = None
    save_mode: str = "replace"
    expected_draft_updated_at: datetime | None = None
    current_state: ForecastPhasingDraftStateWrite
    past_states: list[ForecastPhasingDraftStateWrite] = Field(default_factory=list)
    future_states: list[ForecastPhasingDraftStateWrite] = Field(default_factory=list)


class ForecastAccuracyMetricsRead(BaseSchema):
    comparison_project_count: int
    resolved_project_count: int
    partial_project_count: int
    monthly_coverage_project_count: int
    discipline_coverage_project_count: int
    mean_absolute_error: float | None = None
    mean_absolute_percentage_error: float | None = None
    weighted_absolute_percentage_error: float | None = None
    mean_bias_amount: float | None = None
    mean_bias_percentage: float | None = None
    within_ten_percent_rate: float | None = None


class ForecastAccuracyProjectComparisonRead(BaseSchema):
    project_id: str
    project_name: str
    project_status: str
    scenario_key: str
    confidence_score: float | None = None
    actuals_status: str
    actual_source: str
    forecast_amount: float
    actual_amount: float
    variance_amount: float
    variance_pct: float | None = None
    absolute_percentage_error: float | None = None


class ForecastAccuracyMonthRead(BaseSchema):
    month: str
    project_count: int
    forecast_amount: float
    actual_amount: float
    variance_amount: float
    variance_pct: float | None = None
    absolute_percentage_error: float | None = None


class ForecastAccuracyDisciplineRead(BaseSchema):
    discipline_id: str | None = None
    discipline_code: str | None = None
    discipline_name: str | None = None
    sample_count: int
    forecast_amount: float
    actual_amount: float
    variance_amount: float
    variance_pct: float | None = None
    mean_absolute_percentage_error: float | None = None


class ForecastConfidenceCalibrationRead(BaseSchema):
    bucket_key: str
    label: str
    project_count: int
    average_confidence_score: float
    average_accuracy_score: float
    mean_absolute_percentage_error: float
    overconfidence_gap: float
    within_range_rate: float


class ForecastScenarioAccuracyRead(BaseSchema):
    scenario_key: str
    project_count: int
    mean_variance_amount: float
    mean_absolute_percentage_error: float
    mean_bias_percentage: float
    within_ten_percent_rate: float
    closest_to_actual_rate: float


class ForecastAccuracyWeaknessRead(BaseSchema):
    kind: str
    key: str
    label: str
    sample_count: int
    mean_absolute_percentage_error: float | None = None
    variance_amount: float | None = None
    detail: str


class ForecastAccuracyRecommendationRead(BaseSchema):
    key: str
    priority: str
    title: str
    rationale: str


class ForecastAccuracySummaryRead(BaseSchema):
    generated_at: datetime
    metrics: ForecastAccuracyMetricsRead
    forecast_vs_actual: list[ForecastAccuracyProjectComparisonRead]
    monthly_variance: list[ForecastAccuracyMonthRead]
    discipline_variance: list[ForecastAccuracyDisciplineRead]
    confidence_calibration: list[ForecastConfidenceCalibrationRead]
    scenario_accuracy: list[ForecastScenarioAccuracyRead]
    weaknesses: list[ForecastAccuracyWeaknessRead]
    recommendations: list[ForecastAccuracyRecommendationRead]


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


class ForecastCurveProfileOption(BaseSchema):
    key: str
    label: str
    shape_key: str
    description: str | None = None
    default_for_disciplines: list[str] = Field(default_factory=list)


class ForecastSequenceTemplateStageOption(BaseSchema):
    discipline_code: str
    stage_key: str
    start_pct: float
    end_pct: float
    overlap_pct: float | None = None


class ForecastSequenceTemplateOption(BaseSchema):
    key: str
    label: str
    project_format_keys: list[str] = Field(default_factory=list)
    stages: list[ForecastSequenceTemplateStageOption] = Field(default_factory=list)


class ForecastPolicySummary(BaseSchema):
    supported_methods: list[str]
    supported_outcomes: list[str]
    recalc_triggers: list[str]
    curve_profiles: list[ForecastCurveProfileOption] = Field(default_factory=list)
    sequencing_templates: list[ForecastSequenceTemplateOption] = Field(default_factory=list)


class ForecastRecalculateResponse(BaseSchema):
    project_id: str
    job_id: str
    queue_name: str
    status: str
    forecast_version_id: str | None = None
    message: str
