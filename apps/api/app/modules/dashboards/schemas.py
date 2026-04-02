from __future__ import annotations

from datetime import datetime

from app.core.schemas import BaseSchema
from app.modules.forecasts.schemas import DashboardForecastDatasetContractRead


class DashboardOption(BaseSchema):
    id: str
    label: str


class DashboardAppliedFilters(BaseSchema):
    from_month: str
    to_month: str
    client_id: str | None = None
    project_id: str | None = None
    discipline_id: str | None = None
    status: str | None = None
    scenario_key: str | None = None


class DashboardFilterOptions(BaseSchema):
    clients: list[DashboardOption]
    projects: list[DashboardOption]
    disciplines: list[DashboardOption]
    statuses: list[DashboardOption]
    scenarios: list[DashboardOption]


class DashboardSummaryCard(BaseSchema):
    key: str
    label: str
    value: str
    detail: str


class PipelineStageSummary(BaseSchema):
    status: str
    label: str
    project_count: int
    quote_amount: float
    weighted_amount: float
    booked_amount: float
    currency_code: str


class SalesPipelineSection(BaseSchema):
    currency_code: str
    total_quote_amount: float
    total_weighted_amount: float
    total_booked_amount: float
    stages: list[PipelineStageSummary]


class RevenueMonthPoint(BaseSchema):
    month: str
    gross_amount: float
    weighted_amount: float
    low_amount: float | None = None
    high_amount: float | None = None
    actual_amount: float | None = None
    booked_amount: float | None = None


class MonthlyRevenueForecastSection(BaseSchema):
    currency_code: str
    months: list[RevenueMonthPoint]


class ForecastRevenueMonthStatusPoint(BaseSchema):
    month: str
    bid_amount: float
    weighted_bid_amount: float
    awarded_amount: float
    active_amount: float
    complete_amount: float
    booked_amount: float
    lost_amount: float


class ForecastRevenueStatusTotal(BaseSchema):
    status: str
    label: str
    project_count: int
    total_amount: float
    weighted_total_amount: float


class ForecastRevenueProjectMonthValue(BaseSchema):
    month: str
    amount: float
    weighted_amount: float
    actual_amount: float | None = None
    booked_amount: float | None = None


class ForecastRevenueDisciplineRow(BaseSchema):
    discipline_id: str
    discipline_name: str
    base_phasing_profile: str
    forecast_method: str
    line_count: int
    manual_override_line_count: int
    total_amount: float
    weighted_total_amount: float
    month_values: list[ForecastRevenueProjectMonthValue]


class ForecastRevenueProjectRow(BaseSchema):
    project_id: str
    project_name: str
    client_id: str
    client_name: str
    status: str
    quote_entry_date: str | None = None
    execution_start_date: str | None = None
    execution_end_date: str | None = None
    quote_to_execution_lead_months: int | None = None
    spanning_month_count: int
    base_phasing_profile: str
    forecast_method: str
    manual_override_line_count: int
    total_revenue: float
    window_revenue: float
    weighted_total_revenue: float
    window_weighted_revenue: float
    forecast_version_id: str | None = None
    forecast_status: str | None = None
    scenario_key: str | None = None
    change_summary: dict[str, object] | None = None
    explanation_summary: dict[str, object] | None = None
    month_values: list[ForecastRevenueProjectMonthValue]
    discipline_rows: list[ForecastRevenueDisciplineRow]


class ForecastRevenueDashboardSection(BaseSchema):
    currency_code: str
    months: list[str]
    monthly_status_totals: list[ForecastRevenueMonthStatusPoint]
    overall_status_totals: list[ForecastRevenueStatusTotal]
    project_rows: list[ForecastRevenueProjectRow]


class AwardedLostMonthPoint(BaseSchema):
    month: str
    awarded_count: int
    lost_count: int
    awarded_amount: float
    lost_amount: float


class AwardedLostTrendSection(BaseSchema):
    currency_code: str
    months: list[AwardedLostMonthPoint]


class VarianceBucketSummary(BaseSchema):
    key: str
    label: str
    project_count: int
    quoted_amount: float
    actual_amount: float
    variance_amount: float


class QuoteActualVarianceSection(BaseSchema):
    currency_code: str
    project_count: int
    median_variance_pct: float | None = None
    complete_actuals_count: int
    buckets: list[VarianceBucketSummary]


class ClientHistorySummary(BaseSchema):
    client_id: str
    client_name: str
    project_count: int
    bid_count: int
    awarded_count: int
    lost_count: int
    active_count: int
    complete_count: int
    quoted_amount: float
    actual_amount: float
    median_variance_pct: float | None = None


class ClientProjectHistorySection(BaseSchema):
    currency_code: str
    clients: list[ClientHistorySummary]


class DisciplineTrendPoint(BaseSchema):
    month: str
    gross_amount: float
    weighted_amount: float


class DisciplineRevenueSeries(BaseSchema):
    discipline_id: str
    discipline_name: str
    points: list[DisciplineTrendPoint]


class DisciplineRevenueTrendsSection(BaseSchema):
    currency_code: str
    months: list[str]
    series: list[DisciplineRevenueSeries]


class ConfidenceBandSummary(BaseSchema):
    band: str
    label: str
    project_count: int


class ForecastConfidenceSection(BaseSchema):
    project_count: int
    average_score: float
    high_confidence_project_count: int
    bands: list[ConfidenceBandSummary]


class BenchmarkDisciplineSummary(BaseSchema):
    discipline_id: str
    discipline_name: str
    project_count: int
    median_variance_pct: float | None = None


class BenchmarkOverviewSection(BaseSchema):
    currency_code: str
    benchmark_project_count: int
    complete_actuals_count: int
    median_variance_pct: float | None = None
    variance_bands: list[VarianceBucketSummary]
    disciplines: list[BenchmarkDisciplineSummary]


class OperationalDashboardResponse(BaseSchema):
    generated_at: datetime
    applied_filters: DashboardAppliedFilters
    filter_options: DashboardFilterOptions
    summary_cards: list[DashboardSummaryCard]
    sales_pipeline: SalesPipelineSection
    forecast_dataset: DashboardForecastDatasetContractRead
    monthly_revenue_forecast: MonthlyRevenueForecastSection
    forecast_revenue: ForecastRevenueDashboardSection
    awarded_lost_trend: AwardedLostTrendSection
    quote_actual_variance: QuoteActualVarianceSection
    client_project_history: ClientProjectHistorySection
    discipline_revenue_trends: DisciplineRevenueTrendsSection
    forecast_confidence: ForecastConfidenceSection
    benchmark_overview: BenchmarkOverviewSection


class DashboardDrilldownColumn(BaseSchema):
    key: str
    label: str
    kind: str


class DashboardDrilldownResponse(BaseSchema):
    view: str
    title: str
    columns: list[DashboardDrilldownColumn]
    rows: list[dict[str, str | int | float | None]]
    totals: dict[str, str | int | float | None]
