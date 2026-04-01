from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.datetimes import same_timestamp
from app.core.errors import ApiProblemException
from app.models import (
    Discipline,
    Forecast,
    ForecastLine,
    ForecastVersion,
    MappedActual,
    MonthlyForecastAllocation,
    PredictionRun,
    PredictionScenario,
    Project,
    ProjectBenchmarkDisciplineSummary,
    ProjectBenchmarkSummary,
    ProjectMetadata,
    ProjectOutcome,
    ProjectScheduleRange,
    Quote,
    QuoteLineItem,
    QuoteSection,
    QuoteVersion,
    ReferenceDataValue,
)
from app.models.enums import (
    CetaRowFinancialType,
    ForecastAllocationMethod,
    ForecastVersionStatus,
    ProjectOutcomeType,
)
from app.modules.audit.service import audit_service
from app.modules.forecasts.engine import (
    DEFAULT_CURVE_PROFILES,
    DEFAULT_SEQUENCE_TEMPLATES,
    ForecastEngineLineInput,
    ForecastEngineProjectContext,
    ForecastEngineScheduleRange,
    build_line_plan,
    summarize_version_delta,
)
from app.modules.forecasts.schemas import (
    ForecastAccuracyDisciplineRead,
    ForecastAccuracyMetricsRead,
    ForecastAccuracyMonthRead,
    ForecastAccuracyProjectComparisonRead,
    ForecastAccuracyRecommendationRead,
    ForecastAccuracySummaryRead,
    ForecastAccuracyWeaknessRead,
    ForecastConfidenceCalibrationRead,
    ForecastCurveProfileOption,
    ForecastDetailRead,
    ForecastDisciplineMonthlyRollupRead,
    ForecastExplanationRead,
    ForecastLineAllocationsReplaceRequest,
    ForecastLineMonthAllocationWrite,
    ForecastLineRead,
    ForecastMonthlyAllocationRead,
    ForecastPolicySummary,
    ForecastProjectMonthlyRollupRead,
    ForecastScenarioAccuracyRead,
    ForecastSequenceTemplateOption,
    ForecastSequenceTemplateStageOption,
    ForecastVersionCreateRequest,
    ForecastVersionRead,
    ForecastVersionSummaryRead,
    ForecastVersionUpdateRequest,
)
from app.modules.forecasts.validation import (
    ForecastValidationProjectContext,
    ForecastValidationQuoteLine,
    ForecastValidationScheduleRange,
    _blocking_messages,
    collect_detail_sanity_checks,
    collect_line_sanity_checks,
    collect_version_sanity_checks,
)

type EngineAllocationTuple = tuple[
    str,
    float,
    float,
    float,
    str,
    float | None,
    dict[str, object],
]

FORECAST_CURVE_PROFILE_CATEGORY = "forecast_curve_profile"
FORECAST_SEQUENCE_TEMPLATE_CATEGORY = "forecast_sequence_template"


def _to_cents(amount: float) -> int:
    return round(amount * 100)


def _from_cents(amount_in_cents: int) -> float:
    return amount_in_cents / 100


def _round_amount(value: float) -> float:
    return round(value, 2)


def _round_percent(value: float) -> float:
    return round(value, 2)


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _month_date(month: str) -> date:
    year_text, month_text = month.split("-", maxsplit=1)
    return date(int(year_text), int(month_text), 1)


def _first_day_next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _last_day_of_month(value: date) -> date:
    return _first_day_next_month(value) - timedelta(days=1)


def _diff_days_inclusive(start_date: date, end_date: date) -> int:
    return (end_date - start_date).days + 1


def _safe_percent(numerator: float, denominator: float) -> float | None:
    if abs(denominator) < 0.005:
        return None
    return _round_percent((numerator / denominator) * 100)


def _absolute_percentage_error(actual_amount: float, forecast_amount: float) -> float | None:
    return _safe_percent(abs(actual_amount - forecast_amount), actual_amount)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return _round_amount(sum(values) / len(values))


def _confidence_bucket(score: float) -> tuple[str, str]:
    if score >= 80:
        return ("high", "High confidence")
    if score >= 60:
        return ("medium", "Medium confidence")
    return ("low", "Low confidence")


def _scenario_sort_key(scenario_key: str) -> tuple[int, str]:
    order = {"base": 0, "upside": 1, "downside": 2}
    return (order.get(scenario_key, 99), scenario_key)


def _scenario_projected_total(output_json: dict[str, Any]) -> float | None:
    projected_total = output_json.get("projectedTotalRevenue")
    if projected_total is not None and float(projected_total) > 0:
        return _round_amount(float(projected_total))

    monthly_revenue_spread = output_json.get("monthlyRevenueSpread")
    if isinstance(monthly_revenue_spread, list):
        month_total = sum(
            float(item.get("predictedAmountMedian") or 0)
            for item in monthly_revenue_spread
            if isinstance(item, dict)
        )
        if month_total > 0:
            return _round_amount(month_total)

    discipline_usage = output_json.get("disciplineUsage")
    if isinstance(discipline_usage, list):
        discipline_total = sum(
            float(item.get("predictedActualAmount") or item.get("predictedAmountMedian") or 0)
            for item in discipline_usage
            if isinstance(item, dict)
        )
        if discipline_total > 0:
            return _round_amount(discipline_total)

    likely_quote_range = output_json.get("likelyQuoteRange")
    if isinstance(likely_quote_range, dict):
        for key in ("recommendedMedian", "median"):
            if likely_quote_range.get(key) is not None and float(likely_quote_range[key]) > 0:
                return _round_amount(float(likely_quote_range[key]))

    return None


def _normalize_probability(bucket: str, requested_probability: float | None) -> float:
    if requested_probability is not None and (
        requested_probability < 0 or requested_probability > 100
    ):
        raise ApiProblemException(
            422,
            "Forecast probability percent must be between 0 and 100.",
            "Invalid Forecast Probability",
        )

    if bucket == "awarded":
        return 100.0

    if bucket == "lost":
        return 0.0

    return round(requested_probability if requested_probability is not None else 100.0, 2)


def _sort_with_remainder(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        items,
        key=lambda item: (-float(item["remainder"]), str(item["sort_key"])),
    )


def _build_schedule_monthly_allocations(
    start_date: date, end_date: date, amount_in_cents: int
) -> list[tuple[str, int]]:
    if end_date < start_date:
        raise ApiProblemException(
            422,
            "Schedule range end date cannot be earlier than start date.",
            "Invalid Schedule Range",
        )

    total_days = _diff_days_inclusive(start_date, end_date)
    current_start = start_date
    allocations: list[dict[str, object]] = []

    while current_start <= end_date:
        current_end = min(_last_day_of_month(current_start), end_date)
        days_in_slice = _diff_days_inclusive(current_start, current_end)
        raw_amount = (amount_in_cents * days_in_slice) / total_days
        floor_amount = int(raw_amount // 1)
        allocations.append(
            {
                "month": _month_key(current_start),
                "floor_amount": floor_amount,
                "remainder": raw_amount - floor_amount,
                "sort_key": _month_key(current_start),
            }
        )
        current_start = _first_day_next_month(current_start)

    remainder = amount_in_cents - sum(int(item["floor_amount"]) for item in allocations)
    for item in _sort_with_remainder(allocations):
        if remainder <= 0:
            break
        item["floor_amount"] = int(item["floor_amount"]) + 1
        remainder -= 1

    return [
        (str(item["month"]), int(item["floor_amount"]))
        for item in sorted(allocations, key=lambda item: str(item["month"]))
    ]


def _build_weighted_allocations(
    allocations: list[tuple[str, int]], probability_percent: float
) -> list[tuple[str, int, int]]:
    factor = probability_percent / 100
    total_weighted_cents = round(sum(amount for _, amount in allocations) * factor)
    weighted: list[dict[str, object]] = []

    for month, amount_in_cents in allocations:
        raw_weighted = amount_in_cents * factor
        floor_weighted = int(raw_weighted // 1)
        weighted.append(
            {
                "month": month,
                "amount_in_cents": amount_in_cents,
                "floor_weighted": floor_weighted,
                "remainder": raw_weighted - floor_weighted,
                "sort_key": month,
            }
        )

    remainder = total_weighted_cents - sum(int(item["floor_weighted"]) for item in weighted)
    for item in _sort_with_remainder(weighted):
        if remainder <= 0:
            break
        item["floor_weighted"] = int(item["floor_weighted"]) + 1
        remainder -= 1

    return [
        (str(item["month"]), int(item["amount_in_cents"]), int(item["floor_weighted"]))
        for item in sorted(weighted, key=lambda item: str(item["month"]))
    ]


def _allocate_month_weights(
    total_amount_in_cents: int,
    month_amounts: list[tuple[str, float]],
) -> list[tuple[str, int]]:
    total_weight = sum(amount for _, amount in month_amounts)
    if total_amount_in_cents <= 0 or total_weight <= 0:
        return []
    weighted: list[dict[str, object]] = []
    for month, amount in month_amounts:
        raw_amount = total_amount_in_cents * (amount / total_weight)
        floor_amount = int(raw_amount // 1)
        weighted.append(
            {
                "month": month,
                "floor_amount": floor_amount,
                "remainder": raw_amount - floor_amount,
                "sort_key": month,
            }
        )
    remainder = total_amount_in_cents - sum(int(item["floor_amount"]) for item in weighted)
    for item in _sort_with_remainder(weighted):
        if remainder <= 0:
            break
        item["floor_amount"] = int(item["floor_amount"]) + 1
        remainder -= 1
    return [
        (str(item["month"]), int(item["floor_amount"]))
        for item in sorted(weighted, key=lambda item: str(item["month"]))
    ]


def _merge_engine_allocations(
    allocations: list[EngineAllocationTuple],
) -> list[EngineAllocationTuple]:
    merged: dict[str, dict[str, object]] = {}
    for (
        month,
        amount,
        low_amount,
        high_amount,
        source,
        actual_amount,
        source_context,
    ) in allocations:
        existing = merged.get(month)
        if existing is None:
            merged[month] = {
                "amount": round(amount, 2),
                "low_amount": round(low_amount, 2),
                "high_amount": round(high_amount, 2),
                "source": source,
                "actual_amount": round(actual_amount, 2) if actual_amount is not None else None,
                "source_context": dict(source_context),
            }
            continue
        existing["amount"] = round(float(existing["amount"]) + amount, 2)
        existing["low_amount"] = round(float(existing["low_amount"]) + low_amount, 2)
        existing["high_amount"] = round(float(existing["high_amount"]) + high_amount, 2)
        if source == "actual" or str(existing["source"]) != "actual":
            existing["source"] = source
        if actual_amount is not None:
            existing["actual_amount"] = round(
                float(existing["actual_amount"] or 0.0) + actual_amount,
                2,
            )
        if source_context:
            current_context = existing["source_context"]
            if isinstance(current_context, dict):
                current_context.update(source_context)
        source_list = existing["source_context"].setdefault("mergedSources", [])
        if isinstance(source_list, list) and source not in source_list:
            source_list.append(source)

    return [
        (
            month,
            float(values["amount"]),
            float(values["low_amount"]),
            float(values["high_amount"]),
            str(values["source"]),
            float(values["actual_amount"]) if values["actual_amount"] is not None else None,
            dict(values["source_context"]),
        )
        for month, values in sorted(merged.items())
    ]


def _validate_manual_allocations(
    expected_amount_in_cents: int, allocations: list[ForecastLineMonthAllocationWrite]
) -> tuple[list[tuple[str, int]], list[str]]:
    issues: list[str] = []
    seen_months: set[str] = set()
    normalized: list[tuple[str, int]] = []

    for allocation in sorted(allocations, key=lambda item: item.month):
        if len(allocation.month) != 7 or allocation.month[4] != "-":
            issues.append(f"Invalid month format: {allocation.month}")
        if allocation.amount < 0:
            issues.append(f"Negative manual allocation is not allowed: {allocation.month}")
        if allocation.month in seen_months:
            issues.append(f"Duplicate manual allocation month: {allocation.month}")
        seen_months.add(allocation.month)
        normalized.append((allocation.month, _to_cents(allocation.amount)))

    total_amount_in_cents = sum(amount for _, amount in normalized)
    if total_amount_in_cents != expected_amount_in_cents:
        issues.append(
            "Manual allocations total "
            f"{_from_cents(total_amount_in_cents):.2f} but expected "
            f"{_from_cents(expected_amount_in_cents):.2f}"
        )

    return normalized, issues


@dataclass
class OutcomeSeed:
    outcome_type: str
    effective_at: datetime


@dataclass
class ScheduleRangeSeed:
    id: str
    label: str
    start_date: date
    end_date: date
    discipline_id: str | None = None
    discipline_code: str | None = None
    allocation_percent: float | None = None


@dataclass
class QuoteLineSeed:
    id: str
    label: str
    discipline_id: str | None
    discipline_code: str | None
    amount_in_cents: int
    currency_code: str


@dataclass
class ForecastLineSeed:
    label: str
    total_amount_in_cents: int
    currency_code: str
    allocation_method: str
    discipline_id: str | None = None
    schedule_range_id: str | None = None
    source_quote_line_item_id: str | None = None
    notes: str | None = None
    manual_allocations: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class ProjectSeed:
    id: str
    name: str
    status: str
    start_date: date | None
    end_date: date | None
    pipeline_stage_key: str | None
    project_format_key: str | None
    duration_weeks: int | None
    episode_count: int | None
    metadata_json: dict[str, object] | None
    current_quote_version_id: str | None
    outcomes: list[OutcomeSeed]
    schedule_ranges: list[ScheduleRangeSeed]
    quote_lines: list[QuoteLineSeed]
    actuals_by_discipline_month: dict[str, dict[str, float]]
    actuals_by_project_month: dict[str, float]


class ForecastService:
    def get_policy(self, session: Session) -> ForecastPolicySummary:
        curve_profiles = self._load_curve_profile_options(session)
        sequencing_templates = self._load_sequence_template_options(session)
        return ForecastPolicySummary(
            supported_methods=["manual", "linear", "curve", "milestone", "hybrid"],
            supported_outcomes=["bid", "awarded", "lost"],
            recalc_triggers=[
                "quote_approved",
                "current_quote_issued",
                "allocation_updated",
                "schedule_range_updated",
                "project_dates_updated",
                "project_outcome_updated",
                "actuals_imported",
                "scenario_promoted",
            ],
            curve_profiles=curve_profiles,
            sequencing_templates=sequencing_templates,
        )

    def get_accuracy_summary(self, session: Session) -> ForecastAccuracySummaryRead:
        generated_at = datetime.now(UTC)
        forecasts = list(
            session.scalars(
                select(Forecast).where(Forecast.current_version_id.is_not(None))
            )
        )
        if not forecasts:
            return ForecastAccuracySummaryRead(
                generated_at=generated_at,
                metrics=ForecastAccuracyMetricsRead(
                    comparison_project_count=0,
                    resolved_project_count=0,
                    partial_project_count=0,
                    monthly_coverage_project_count=0,
                    discipline_coverage_project_count=0,
                ),
                forecast_vs_actual=[],
                monthly_variance=[],
                discipline_variance=[],
                confidence_calibration=[],
                scenario_accuracy=[],
                weaknesses=[],
                recommendations=[],
            )

        project_ids = sorted({forecast.project_id for forecast in forecasts})
        version_ids = [
            forecast.current_version_id
            for forecast in forecasts
            if forecast.current_version_id is not None
        ]
        versions = list(
            session.scalars(select(ForecastVersion).where(ForecastVersion.id.in_(version_ids)))
        )
        versions_by_id = {version.id: version for version in versions}
        current_version_by_project_id = {
            forecast.project_id: versions_by_id[forecast.current_version_id]
            for forecast in forecasts
            if (
                forecast.current_version_id is not None
                and forecast.current_version_id in versions_by_id
            )
        }

        lines = list(
            session.scalars(
                select(ForecastLine).where(ForecastLine.forecast_version_id.in_(version_ids))
            )
        )
        lines_by_version_id: dict[str, list[ForecastLine]] = defaultdict(list)
        for line in lines:
            lines_by_version_id[line.forecast_version_id].append(line)

        line_ids = [line.id for line in lines]
        allocations = (
            list(
                session.scalars(
                    select(MonthlyForecastAllocation).where(
                        MonthlyForecastAllocation.forecast_line_id.in_(line_ids)
                    )
                )
            )
            if line_ids
            else []
        )
        allocations_by_line_id: dict[str, list[MonthlyForecastAllocation]] = defaultdict(list)
        for allocation in allocations:
            allocations_by_line_id[allocation.forecast_line_id].append(allocation)

        projects = list(session.scalars(select(Project).where(Project.id.in_(project_ids))))
        projects_by_id = {project.id: project for project in projects}

        benchmark_summaries = list(
            session.scalars(
                select(ProjectBenchmarkSummary).where(
                    ProjectBenchmarkSummary.project_id.in_(project_ids)
                )
            )
        )
        benchmarks_by_project_id = {
            summary.project_id: summary for summary in benchmark_summaries
        }

        benchmark_ids = [summary.id for summary in benchmark_summaries]
        benchmark_discipline_summaries = (
            list(
                session.scalars(
                    select(ProjectBenchmarkDisciplineSummary).where(
                        ProjectBenchmarkDisciplineSummary.benchmark_summary_id.in_(
                            benchmark_ids
                        )
                    )
                )
            )
            if benchmark_ids
            else []
        )
        benchmark_project_by_id = {
            summary.id: summary.project_id for summary in benchmark_summaries
        }
        benchmark_discipline_by_project_id: dict[str, dict[str | None, float]] = defaultdict(dict)
        discipline_ids: set[str] = {
            summary.discipline_id for summary in benchmark_discipline_summaries
        }
        for summary in benchmark_discipline_summaries:
            if summary.actual_amount is None:
                continue
            project_id = benchmark_project_by_id.get(summary.benchmark_summary_id)
            if project_id is None:
                continue
            benchmark_discipline_by_project_id[project_id][summary.discipline_id] = float(
                summary.actual_amount
            )

        mapped_actuals = list(
            session.scalars(
                select(MappedActual).where(
                    MappedActual.project_id.in_(project_ids),
                    MappedActual.financial_type == CetaRowFinancialType.revenue,
                    MappedActual.is_current.is_(True),
                )
            )
        )
        mapped_actuals_by_project_month: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        mapped_actuals_by_project_discipline: dict[str, dict[str | None, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for actual in mapped_actuals:
            comparison_date = actual.work_date or actual.posting_date
            if comparison_date is not None:
                month_key = _month_key(comparison_date)
                mapped_actuals_by_project_month[actual.project_id][month_key] += float(
                    actual.amount
                )
            mapped_actuals_by_project_discipline[actual.project_id][actual.discipline_id] += float(
                actual.amount
            )
            if actual.discipline_id is not None:
                discipline_ids.add(actual.discipline_id)

        latest_prediction_runs: dict[str, PredictionRun] = {}
        prediction_runs = list(
            session.scalars(
                select(PredictionRun)
                .where(PredictionRun.project_id.in_(project_ids))
                .order_by(PredictionRun.project_id, desc(PredictionRun.generated_at))
            )
        )
        for run in prediction_runs:
            latest_prediction_runs.setdefault(run.project_id, run)

        latest_run_ids = [run.id for run in latest_prediction_runs.values()]
        prediction_scenarios = (
            list(
                session.scalars(
                    select(PredictionScenario).where(
                        PredictionScenario.prediction_run_id.in_(latest_run_ids)
                    )
                )
            )
            if latest_run_ids
            else []
        )
        prediction_scenarios_by_run_id: dict[str, list[PredictionScenario]] = defaultdict(list)
        for scenario in prediction_scenarios:
            prediction_scenarios_by_run_id[scenario.prediction_run_id].append(scenario)

        disciplines = (
            list(session.scalars(select(Discipline).where(Discipline.id.in_(discipline_ids))))
            if discipline_ids
            else []
        )
        disciplines_by_id = {discipline.id: discipline for discipline in disciplines}

        version_month_totals: dict[str, dict[str, dict[str, float]]] = {}
        version_discipline_totals: dict[str, dict[str | None, float]] = {}
        for version_id in version_ids:
            month_totals: dict[str, dict[str, float]] = {}
            discipline_totals: dict[str | None, float] = defaultdict(float)
            for line in lines_by_version_id.get(version_id, []):
                discipline_totals[line.discipline_id] += float(line.total_amount or 0)
                for allocation in allocations_by_line_id.get(line.id, []):
                    month = _month_key(allocation.month)
                    values = month_totals.setdefault(
                        month,
                        {"amount": 0.0, "low": 0.0, "high": 0.0},
                    )
                    amount = float(allocation.amount)
                    low_amount = (
                        float(allocation.low_amount)
                        if allocation.low_amount is not None
                        else amount
                    )
                    high_amount = (
                        float(allocation.high_amount)
                        if allocation.high_amount is not None
                        else amount
                    )
                    values["amount"] += amount
                    values["low"] += low_amount
                    values["high"] += high_amount
            version_month_totals[version_id] = month_totals
            version_discipline_totals[version_id] = dict(discipline_totals)

        project_rows: list[ForecastAccuracyProjectComparisonRead] = []
        resolved_actual_totals: dict[str, float] = {}
        monthly_coverage_projects: set[str] = set()
        discipline_coverage_projects: set[str] = set()
        resolved_abs_errors: list[float] = []
        resolved_abs_pct_errors: list[float] = []
        resolved_bias_amounts: list[float] = []
        resolved_bias_pcts: list[float] = []
        resolved_actual_sum = 0.0
        resolved_abs_error_sum = 0.0
        resolved_within_ten_count = 0
        calibration_buckets: dict[str, dict[str, Any]] = {}

        for project_id, version in current_version_by_project_id.items():
            project = projects_by_id.get(project_id)
            if project is None:
                continue
            benchmark = benchmarks_by_project_id.get(project_id)
            mapped_total = _round_amount(
                sum(mapped_actuals_by_project_discipline.get(project_id, {}).values())
            )
            actual_total: float | None = None
            actuals_status = "none"
            actual_source = "none"
            if benchmark is not None and benchmark.actual_amount is not None:
                actual_total = _round_amount(float(benchmark.actual_amount))
                actuals_status = benchmark.actuals_status.value
                actual_source = "benchmark_summary"
            elif mapped_total > 0:
                actual_total = mapped_total
                actuals_status = "partial"
                actual_source = "mapped_actuals"

            if actual_total is None:
                continue

            forecast_amount = _round_amount(float(version.total_amount or 0))
            variance_amount = _round_amount(actual_total - forecast_amount)
            variance_pct = _safe_percent(variance_amount, forecast_amount)
            absolute_percentage_error = _absolute_percentage_error(
                actual_total,
                forecast_amount,
            )
            project_rows.append(
                ForecastAccuracyProjectComparisonRead(
                    project_id=project.id,
                    project_name=project.name,
                    project_status=project.status.value,
                    scenario_key=version.scenario_key or "base",
                    confidence_score=(
                        float(version.confidence_score)
                        if version.confidence_score is not None
                        else None
                    ),
                    actuals_status=actuals_status,
                    actual_source=actual_source,
                    forecast_amount=forecast_amount,
                    actual_amount=actual_total,
                    variance_amount=variance_amount,
                    variance_pct=variance_pct,
                    absolute_percentage_error=absolute_percentage_error,
                )
            )

            if actuals_status == "complete":
                resolved_actual_totals[project_id] = actual_total
                abs_error = abs(actual_total - forecast_amount)
                resolved_abs_errors.append(_round_amount(abs_error))
                resolved_actual_sum += actual_total
                resolved_abs_error_sum += abs_error
                resolved_bias_amounts.append(variance_amount)
                if absolute_percentage_error is not None:
                    resolved_abs_pct_errors.append(absolute_percentage_error)
                    if absolute_percentage_error <= 10:
                        resolved_within_ten_count += 1
                bias_pct = _safe_percent(variance_amount, actual_total)
                if bias_pct is not None:
                    resolved_bias_pcts.append(bias_pct)

                if version.confidence_score is not None and absolute_percentage_error is not None:
                    bucket_key, label = _confidence_bucket(float(version.confidence_score))
                    bucket = calibration_buckets.setdefault(
                        bucket_key,
                        {
                            "label": label,
                            "confidence_scores": [],
                            "accuracy_scores": [],
                            "absolute_percentage_errors": [],
                            "within_range_count": 0,
                            "project_count": 0,
                        },
                    )
                    month_totals = version_month_totals.get(version.id, {})
                    if month_totals:
                        low_total = sum(values["low"] for values in month_totals.values())
                        high_total = sum(values["high"] for values in month_totals.values())
                    else:
                        low_total = forecast_amount
                        high_total = forecast_amount
                    within_range = (low_total - 0.01) <= actual_total <= (high_total + 0.01)
                    bucket["confidence_scores"].append(float(version.confidence_score))
                    bucket["accuracy_scores"].append(
                        _round_percent(max(0.0, 100 - absolute_percentage_error))
                    )
                    bucket["absolute_percentage_errors"].append(absolute_percentage_error)
                    bucket["project_count"] += 1
                    if within_range:
                        bucket["within_range_count"] += 1

            if mapped_actuals_by_project_month.get(project_id):
                monthly_coverage_projects.add(project_id)

        project_rows.sort(
            key=lambda row: (
                0 if row.actuals_status == "complete" else 1,
                -(row.absolute_percentage_error or -1),
                row.project_name,
            )
        )

        monthly_aggregates: dict[str, dict[str, Any]] = {}
        for project_id, version in current_version_by_project_id.items():
            actual_months = mapped_actuals_by_project_month.get(project_id)
            if not actual_months:
                continue
            forecast_months = version_month_totals.get(version.id, {})
            for month, actual_amount in actual_months.items():
                aggregate = monthly_aggregates.setdefault(
                    month,
                    {"forecast_amount": 0.0, "actual_amount": 0.0, "project_ids": set()},
                )
                aggregate["forecast_amount"] += forecast_months.get(month, {}).get("amount", 0.0)
                aggregate["actual_amount"] += actual_amount
                aggregate["project_ids"].add(project_id)

        monthly_rows = [
            ForecastAccuracyMonthRead(
                month=month,
                project_count=len(values["project_ids"]),
                forecast_amount=_round_amount(float(values["forecast_amount"])),
                actual_amount=_round_amount(float(values["actual_amount"])),
                variance_amount=_round_amount(
                    float(values["actual_amount"]) - float(values["forecast_amount"])
                ),
                variance_pct=_safe_percent(
                    float(values["actual_amount"]) - float(values["forecast_amount"]),
                    float(values["forecast_amount"]),
                ),
                absolute_percentage_error=_absolute_percentage_error(
                    float(values["actual_amount"]),
                    float(values["forecast_amount"]),
                ),
            )
            for month, values in sorted(monthly_aggregates.items(), key=lambda item: item[0])
        ]

        discipline_aggregates: dict[str | None, dict[str, Any]] = {}
        for project_id, version in current_version_by_project_id.items():
            benchmark = benchmarks_by_project_id.get(project_id)
            actual_discipline_totals: dict[str | None, float] | None = None
            if benchmark is not None and benchmark.actuals_status.value == "complete":
                actual_discipline_totals = benchmark_discipline_by_project_id.get(project_id)
            elif project_id in resolved_actual_totals:
                actual_discipline_totals = mapped_actuals_by_project_discipline.get(project_id)
            if not actual_discipline_totals:
                continue
            discipline_coverage_projects.add(project_id)
            forecast_discipline_totals = version_discipline_totals.get(version.id, {})
            for discipline_id, actual_amount in actual_discipline_totals.items():
                aggregate = discipline_aggregates.setdefault(
                    discipline_id,
                    {
                        "forecast_amount": 0.0,
                        "actual_amount": 0.0,
                        "absolute_percentage_errors": [],
                        "project_ids": set(),
                    },
                )
                forecast_amount = forecast_discipline_totals.get(discipline_id, 0.0)
                aggregate["forecast_amount"] += forecast_amount
                aggregate["actual_amount"] += actual_amount
                absolute_percentage_error = _absolute_percentage_error(
                    actual_amount,
                    forecast_amount,
                )
                if absolute_percentage_error is not None:
                    aggregate["absolute_percentage_errors"].append(absolute_percentage_error)
                aggregate["project_ids"].add(project_id)

        discipline_rows = [
            ForecastAccuracyDisciplineRead(
                discipline_id=discipline_id,
                discipline_code=(
                    disciplines_by_id[discipline_id].code
                    if discipline_id is not None and discipline_id in disciplines_by_id
                    else None
                ),
                discipline_name=(
                    disciplines_by_id[discipline_id].name
                    if discipline_id is not None and discipline_id in disciplines_by_id
                    else ("Unassigned discipline" if discipline_id is None else None)
                ),
                sample_count=len(values["project_ids"]),
                forecast_amount=_round_amount(float(values["forecast_amount"])),
                actual_amount=_round_amount(float(values["actual_amount"])),
                variance_amount=_round_amount(
                    float(values["actual_amount"]) - float(values["forecast_amount"])
                ),
                variance_pct=_safe_percent(
                    float(values["actual_amount"]) - float(values["forecast_amount"]),
                    float(values["forecast_amount"]),
                ),
                mean_absolute_percentage_error=_mean(
                    list(values["absolute_percentage_errors"])
                ),
            )
            for discipline_id, values in discipline_aggregates.items()
        ]
        discipline_rows.sort(
            key=lambda row: (
                -(row.mean_absolute_percentage_error or -1),
                row.discipline_name or "",
            )
        )

        calibration_rows = [
            ForecastConfidenceCalibrationRead(
                bucket_key=bucket_key,
                label=str(values["label"]),
                project_count=int(values["project_count"]),
                average_confidence_score=_mean(list(values["confidence_scores"])) or 0.0,
                average_accuracy_score=_mean(list(values["accuracy_scores"])) or 0.0,
                mean_absolute_percentage_error=(
                    _mean(list(values["absolute_percentage_errors"])) or 0.0
                ),
                overconfidence_gap=_round_amount(
                    (_mean(list(values["confidence_scores"])) or 0.0)
                    - (_mean(list(values["accuracy_scores"])) or 0.0)
                ),
                within_range_rate=_safe_percent(
                    int(values["within_range_count"]),
                    int(values["project_count"]),
                )
                or 0.0,
            )
            for bucket_key, values in sorted(
                calibration_buckets.items(),
                key=lambda item: {"high": 0, "medium": 1, "low": 2}.get(item[0], 99),
            )
        ]

        scenario_aggregates: dict[str, dict[str, Any]] = {}
        for project_id, actual_total in resolved_actual_totals.items():
            run = latest_prediction_runs.get(project_id)
            if run is None:
                continue
            scenario_distances: list[tuple[str, float]] = []
            for scenario in sorted(
                prediction_scenarios_by_run_id.get(run.id, []),
                key=lambda item: _scenario_sort_key(item.scenario_key),
            ):
                projected_total = _scenario_projected_total(scenario.output_json)
                if projected_total is None or projected_total <= 0:
                    continue
                variance_amount = _round_amount(actual_total - projected_total)
                absolute_percentage_error = _absolute_percentage_error(
                    actual_total,
                    projected_total,
                )
                mean_bias_percentage = _safe_percent(variance_amount, actual_total)
                aggregate = scenario_aggregates.setdefault(
                    scenario.scenario_key,
                    {
                        "variance_amounts": [],
                        "absolute_percentage_errors": [],
                        "bias_percentages": [],
                        "within_ten_count": 0,
                        "closest_count": 0,
                        "project_count": 0,
                    },
                )
                aggregate["variance_amounts"].append(variance_amount)
                if absolute_percentage_error is not None:
                    aggregate["absolute_percentage_errors"].append(absolute_percentage_error)
                    if absolute_percentage_error <= 10:
                        aggregate["within_ten_count"] += 1
                if mean_bias_percentage is not None:
                    aggregate["bias_percentages"].append(mean_bias_percentage)
                aggregate["project_count"] += 1
                scenario_distances.append(
                    (scenario.scenario_key, abs(actual_total - projected_total))
                )

            if scenario_distances:
                closest_key = min(scenario_distances, key=lambda item: item[1])[0]
                scenario_aggregates[closest_key]["closest_count"] += 1

        scenario_rows = [
            ForecastScenarioAccuracyRead(
                scenario_key=scenario_key,
                project_count=int(values["project_count"]),
                mean_variance_amount=_mean(list(values["variance_amounts"])) or 0.0,
                mean_absolute_percentage_error=(
                    _mean(list(values["absolute_percentage_errors"])) or 0.0
                ),
                mean_bias_percentage=_mean(list(values["bias_percentages"])) or 0.0,
                within_ten_percent_rate=_safe_percent(
                    int(values["within_ten_count"]),
                    int(values["project_count"]),
                )
                or 0.0,
                closest_to_actual_rate=_safe_percent(
                    int(values["closest_count"]),
                    int(values["project_count"]),
                )
                or 0.0,
            )
            for scenario_key, values in sorted(
                scenario_aggregates.items(),
                key=lambda item: _scenario_sort_key(item[0]),
            )
        ]

        metrics = ForecastAccuracyMetricsRead(
            comparison_project_count=len(project_rows),
            resolved_project_count=len(resolved_actual_totals),
            partial_project_count=sum(
                1 for row in project_rows if row.actuals_status == "partial"
            ),
            monthly_coverage_project_count=len(monthly_coverage_projects),
            discipline_coverage_project_count=len(discipline_coverage_projects),
            mean_absolute_error=_mean(resolved_abs_errors),
            mean_absolute_percentage_error=_mean(resolved_abs_pct_errors),
            weighted_absolute_percentage_error=_safe_percent(
                resolved_abs_error_sum,
                resolved_actual_sum,
            ),
            mean_bias_amount=_mean(resolved_bias_amounts),
            mean_bias_percentage=_mean(resolved_bias_pcts),
            within_ten_percent_rate=_safe_percent(
                resolved_within_ten_count,
                len(resolved_actual_totals),
            ),
        )
        weaknesses = self._build_accuracy_weaknesses(
            project_rows,
            monthly_rows,
            discipline_rows,
            calibration_rows,
            scenario_rows,
        )
        recommendations = self._build_accuracy_recommendations(
            metrics,
            monthly_rows,
            discipline_rows,
            calibration_rows,
            scenario_rows,
        )
        return ForecastAccuracySummaryRead(
            generated_at=generated_at,
            metrics=metrics,
            forecast_vs_actual=project_rows,
            monthly_variance=monthly_rows,
            discipline_variance=discipline_rows,
            confidence_calibration=calibration_rows,
            scenario_accuracy=scenario_rows,
            weaknesses=weaknesses,
            recommendations=recommendations,
        )

    def _build_accuracy_weaknesses(
        self,
        project_rows: list[ForecastAccuracyProjectComparisonRead],
        monthly_rows: list[ForecastAccuracyMonthRead],
        discipline_rows: list[ForecastAccuracyDisciplineRead],
        calibration_rows: list[ForecastConfidenceCalibrationRead],
        scenario_rows: list[ForecastScenarioAccuracyRead],
    ) -> list[ForecastAccuracyWeaknessRead]:
        weaknesses: list[ForecastAccuracyWeaknessRead] = []

        complete_project_rows = [
            row
            for row in project_rows
            if row.actuals_status == "complete" and row.absolute_percentage_error is not None
        ]
        if complete_project_rows:
            project = max(
                complete_project_rows,
                key=lambda row: row.absolute_percentage_error or -1,
            )
            weaknesses.append(
                ForecastAccuracyWeaknessRead(
                    kind="project",
                    key=project.project_id,
                    label=project.project_name,
                    sample_count=1,
                    mean_absolute_percentage_error=project.absolute_percentage_error,
                    variance_amount=project.variance_amount,
                    detail=(
                        f"{project.project_name} shows the largest complete-project miss at "
                        f"{project.absolute_percentage_error:.2f}% absolute error."
                    ),
                )
            )

        monthly_candidates = [
            row for row in monthly_rows if row.absolute_percentage_error is not None
        ]
        if monthly_candidates:
            month = max(
                monthly_candidates,
                key=lambda row: row.absolute_percentage_error or -1,
            )
            weaknesses.append(
                ForecastAccuracyWeaknessRead(
                    kind="month",
                    key=month.month,
                    label=month.month,
                    sample_count=month.project_count,
                    mean_absolute_percentage_error=month.absolute_percentage_error,
                    variance_amount=month.variance_amount,
                    detail=(
                        f"{month.month} carries the sharpest month-level miss across "
                        f"{month.project_count} tracked projects."
                    ),
                )
            )

        if discipline_rows and discipline_rows[0].mean_absolute_percentage_error is not None:
            discipline = discipline_rows[0]
            discipline_label = (
                discipline.discipline_name
                or discipline.discipline_code
                or "Unassigned discipline"
            )
            weaknesses.append(
                ForecastAccuracyWeaknessRead(
                    kind="discipline",
                    key=discipline.discipline_id or "unassigned",
                    label=discipline_label,
                    sample_count=discipline.sample_count,
                    mean_absolute_percentage_error=discipline.mean_absolute_percentage_error,
                    variance_amount=discipline.variance_amount,
                    detail=f"{discipline_label} is the weakest discipline on observed actuals.",
                )
            )

        if calibration_rows:
            calibration = max(
                calibration_rows,
                key=lambda row: (row.overconfidence_gap, row.mean_absolute_percentage_error),
            )
            if calibration.overconfidence_gap > 0:
                weaknesses.append(
                    ForecastAccuracyWeaknessRead(
                        kind="confidence",
                        key=calibration.bucket_key,
                        label=calibration.label,
                        sample_count=calibration.project_count,
                        mean_absolute_percentage_error=calibration.mean_absolute_percentage_error,
                        variance_amount=None,
                        detail=(
                            f"{calibration.label} forecasts run "
                            f"{calibration.overconfidence_gap:.2f} points above observed accuracy."
                        ),
                    )
                )

        if scenario_rows:
            scenario = max(
                scenario_rows,
                key=lambda row: row.mean_absolute_percentage_error,
            )
            weaknesses.append(
                ForecastAccuracyWeaknessRead(
                    kind="scenario",
                    key=scenario.scenario_key,
                    label=scenario.scenario_key.title(),
                    sample_count=scenario.project_count,
                    mean_absolute_percentage_error=scenario.mean_absolute_percentage_error,
                    variance_amount=scenario.mean_variance_amount,
                    detail=(
                        f"{scenario.scenario_key.title()} scenario projections are the least "
                        "accurate "
                        f"against resolved actuals."
                    ),
                )
            )

        weaknesses.sort(
            key=lambda item: (
                -(item.mean_absolute_percentage_error or -1),
                -(abs(item.variance_amount) if item.variance_amount is not None else 0),
                item.label,
            )
        )
        return weaknesses[:4]

    def _build_accuracy_recommendations(
        self,
        metrics: ForecastAccuracyMetricsRead,
        monthly_rows: list[ForecastAccuracyMonthRead],
        discipline_rows: list[ForecastAccuracyDisciplineRead],
        calibration_rows: list[ForecastConfidenceCalibrationRead],
        scenario_rows: list[ForecastScenarioAccuracyRead],
    ) -> list[ForecastAccuracyRecommendationRead]:
        recommendations: list[ForecastAccuracyRecommendationRead] = []

        if discipline_rows and discipline_rows[0].mean_absolute_percentage_error is not None:
            discipline = discipline_rows[0]
            if discipline.mean_absolute_percentage_error >= 8:
                discipline_label = (
                    discipline.discipline_name
                    or discipline.discipline_code
                    or "unassigned"
                )
                recommendations.append(
                    ForecastAccuracyRecommendationRead(
                        key=f"discipline_{discipline.discipline_id or 'unassigned'}",
                        priority=(
                            "high"
                            if discipline.mean_absolute_percentage_error >= 12
                            else "medium"
                        ),
                        title=f"Retune {discipline_label} discipline assumptions",
                        rationale=(
                            "This discipline is averaging "
                            f"{discipline.mean_absolute_percentage_error:.2f}% absolute error "
                            f"across {discipline.sample_count} projects, so its spread or "
                            "benchmark assumptions need a dedicated pass."
                        ),
                    )
                )

        if monthly_rows:
            month = max(
                monthly_rows,
                key=lambda row: row.absolute_percentage_error or -1,
            )
            if (
                month.absolute_percentage_error is not None
                and month.absolute_percentage_error >= 10
            ):
                recommendations.append(
                    ForecastAccuracyRecommendationRead(
                        key=f"month_{month.month}",
                        priority=(
                            "high" if month.absolute_percentage_error >= 15 else "medium"
                        ),
                        title=f"Tighten month-level timing around {month.month}",
                        rationale=(
                            f"{month.month} is running at {month.absolute_percentage_error:.2f}% "
                            "absolute error, which suggests the current month-shape assumptions "
                            "and actuals assimilation are not landing cleanly."
                        ),
                    )
                )

        if calibration_rows:
            calibration = max(calibration_rows, key=lambda row: row.overconfidence_gap)
            if calibration.overconfidence_gap >= 5:
                recommendations.append(
                    ForecastAccuracyRecommendationRead(
                        key=f"confidence_{calibration.bucket_key}",
                        priority="medium",
                        title=f"Recalibrate {calibration.label.lower()} forecasts",
                        rationale=(
                            f"Average confidence is {calibration.average_confidence_score:.2f}, "
                            "but realized accuracy is only "
                            f"{calibration.average_accuracy_score:.2f}. "
                            "Lower the score or widen the range until that gap closes."
                        ),
                    )
                )

        if scenario_rows:
            best_scenario = max(
                scenario_rows,
                key=lambda row: (row.closest_to_actual_rate, -row.mean_absolute_percentage_error),
            )
            worst_scenario = max(
                scenario_rows,
                key=lambda row: row.mean_absolute_percentage_error,
            )
            if worst_scenario.scenario_key != best_scenario.scenario_key:
                recommendations.append(
                    ForecastAccuracyRecommendationRead(
                        key="scenario_rebalance",
                        priority="medium",
                        title="Rebalance scenario multipliers against realized outcomes",
                        rationale=(
                            f"{best_scenario.scenario_key.title()} is closest to actuals "
                            f"{best_scenario.closest_to_actual_rate:.2f}% of the time, while "
                            f"{worst_scenario.scenario_key.title()} averages "
                            f"{worst_scenario.mean_absolute_percentage_error:.2f}% absolute error."
                        ),
                    )
                )

        if (
            metrics.comparison_project_count > 0
            and metrics.monthly_coverage_project_count < metrics.comparison_project_count
        ):
            recommendations.append(
                ForecastAccuracyRecommendationRead(
                    key="coverage_gap",
                    priority="medium",
                    title="Increase month-level actual coverage before trusting timing accuracy",
                    rationale=(
                        f"Only {metrics.monthly_coverage_project_count} of "
                        f"{metrics.comparison_project_count} compared forecasts have month-level "
                        "actual evidence, so timing performance is still under-observed."
                    ),
                )
            )

        deduped: list[ForecastAccuracyRecommendationRead] = []
        seen_keys: set[str] = set()
        for recommendation in recommendations:
            if recommendation.key in seen_keys:
                continue
            deduped.append(recommendation)
            seen_keys.add(recommendation.key)
        return deduped[:4]

    def get_project_forecast(self, session: Session, project_id: str) -> ForecastDetailRead:
        project = self._get_project_seed(session, project_id)
        forecast = self._get_or_create_forecast(session, project_id)
        return self._build_forecast_detail(session, project, forecast)

    def _load_reference_category(
        self,
        session: Session,
        category: str,
    ) -> list[ReferenceDataValue]:
        return list(
            session.scalars(
                select(ReferenceDataValue)
                .where(
                    ReferenceDataValue.category == category,
                    ReferenceDataValue.is_active.is_(True),
                )
                .order_by(ReferenceDataValue.sort_order, ReferenceDataValue.label)
            )
        )

    def _load_curve_profile_options(self, session: Session) -> list[ForecastCurveProfileOption]:
        records = self._load_reference_category(session, FORECAST_CURVE_PROFILE_CATEGORY)
        options_by_key: dict[str, ForecastCurveProfileOption] = {}
        for record in records:
            metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
            shape_key = str(metadata.get("shapeKey") or record.key)
            default_definition = (
                DEFAULT_CURVE_PROFILES.get(shape_key)
                or DEFAULT_CURVE_PROFILES.get(record.key, {})
            )
            description = metadata.get("description", default_definition.get("description"))
            default_for_disciplines = metadata.get(
                "defaultDisciplineCodes",
                default_definition.get("defaultDisciplineCodes", []),
            )
            options_by_key[record.key] = ForecastCurveProfileOption(
                key=record.key,
                label=record.label,
                shape_key=shape_key,
                description=str(description) if description is not None else None,
                default_for_disciplines=[
                    str(item)
                    for item in default_for_disciplines
                    if isinstance(item, str) and item
                ],
            )
        for key, definition in DEFAULT_CURVE_PROFILES.items():
            if key in options_by_key:
                continue
            options_by_key[key] = ForecastCurveProfileOption(
                key=key,
                label=str(definition.get("label", key.replace("_", " ").title())),
                shape_key=str(definition.get("shapeKey", key)),
                description=(
                    str(definition["description"])
                    if definition.get("description") is not None
                    else None
                ),
                default_for_disciplines=[
                    str(item)
                    for item in definition.get("defaultDisciplineCodes", [])
                    if isinstance(item, str)
                ],
            )
        return list(options_by_key.values())

    def _curve_profile_registry(self, session: Session) -> dict[str, dict[str, object]]:
        records = self._load_reference_category(session, FORECAST_CURVE_PROFILE_CATEGORY)
        registry: dict[str, dict[str, object]] = {}
        for record in records:
            metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
            shape_key = str(metadata.get("shapeKey") or record.key)
            default_definition = dict(
                DEFAULT_CURVE_PROFILES.get(shape_key)
                or DEFAULT_CURVE_PROFILES.get(record.key)
                or {"shapeKey": shape_key}
            )
            default_definition["shapeKey"] = shape_key
            default_definition["label"] = record.label
            default_definition["description"] = metadata.get(
                "description",
                default_definition.get("description"),
            )
            if isinstance(metadata.get("defaultDisciplineCodes"), list):
                default_definition["defaultDisciplineCodes"] = [
                    str(item)
                    for item in metadata["defaultDisciplineCodes"]
                    if isinstance(item, str) and item
                ]
            for numeric_key in (
                "startMultiplier",
                "endMultiplier",
                "baseMultiplier",
                "peakMultiplier",
                "pulseMultiplier",
                "pulseSharpness",
                "minimumMultiplier",
                "flatMultiplier",
            ):
                if metadata.get(numeric_key) is not None:
                    default_definition[numeric_key] = float(metadata[numeric_key])
            registry[record.key] = default_definition
        for key, value in DEFAULT_CURVE_PROFILES.items():
            registry.setdefault(key, dict(value))
        return registry

    def _load_sequence_template_options(
        self,
        session: Session,
    ) -> list[ForecastSequenceTemplateOption]:
        records = self._load_reference_category(session, FORECAST_SEQUENCE_TEMPLATE_CATEGORY)
        options_by_key: dict[str, ForecastSequenceTemplateOption] = {
            key: ForecastSequenceTemplateOption(
                key=key,
                label=key.replace("_", " ").title(),
                project_format_keys=[key] if key != "default" else [],
                stages=[
                    ForecastSequenceTemplateStageOption(
                        discipline_code=discipline_code,
                        stage_key=str(stage["stage"]),
                        start_pct=float(stage["start_pct"]),
                        end_pct=float(stage["end_pct"]),
                        overlap_pct=float(stage["overlap_pct"]),
                    )
                    for discipline_code, stage in template.items()
                ],
            )
            for key, template in DEFAULT_SEQUENCE_TEMPLATES.items()
        }
        for record in records:
            metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
            raw_stages = metadata.get("stages", [])
            stage_models = []
            if isinstance(raw_stages, list):
                for item in raw_stages:
                    if not isinstance(item, dict):
                        continue
                    discipline_code = item.get("disciplineCode")
                    stage_key = item.get("stageKey")
                    start_pct = item.get("startPct")
                    end_pct = item.get("endPct")
                    if not all(
                        value is not None
                        for value in (discipline_code, stage_key, start_pct, end_pct)
                    ):
                        continue
                    stage_models.append(
                        ForecastSequenceTemplateStageOption(
                            discipline_code=str(discipline_code),
                            stage_key=str(stage_key),
                            start_pct=float(start_pct),
                            end_pct=float(end_pct),
                            overlap_pct=(
                                float(item["overlapPct"])
                                if item.get("overlapPct") is not None
                                else None
                            ),
                        )
                    )

            raw_project_format_keys = metadata.get("projectFormatKeys", [])
            options_by_key[record.key] = ForecastSequenceTemplateOption(
                key=record.key,
                label=record.label,
                project_format_keys=[
                    str(item)
                    for item in raw_project_format_keys
                    if isinstance(item, str) and item
                ],
                stages=stage_models,
            )
        return list(options_by_key.values())

    def _sequence_template_registry(
        self,
        session: Session,
    ) -> dict[str, dict[str, dict[str, float | str]]]:
        records = self._load_reference_category(session, FORECAST_SEQUENCE_TEMPLATE_CATEGORY)
        registry: dict[str, dict[str, dict[str, float | str]]] = {
            template_key: {
                discipline_code: dict(entry) for discipline_code, entry in template.items()
            }
            for template_key, template in DEFAULT_SEQUENCE_TEMPLATES.items()
        }
        for record in records:
            metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
            raw_stages = metadata.get("stages", [])
            template: dict[str, dict[str, float | str]] = {}
            if isinstance(raw_stages, list):
                for item in raw_stages:
                    if not isinstance(item, dict) or not item.get("disciplineCode"):
                        continue
                    template[str(item["disciplineCode"])] = {
                        "stage": str(item.get("stageKey") or item["disciplineCode"]),
                        "start_pct": float(item.get("startPct", 0.0)),
                        "end_pct": float(item.get("endPct", 1.0)),
                        "overlap_pct": float(item.get("overlapPct", 0.0)),
                    }
            if template:
                registry[record.key] = template
        return registry

    def get_version(self, session: Session, version_id: str) -> ForecastVersionRead:
        _forecast, project, version = self._get_version_context(session, version_id)
        return self._build_version_read(session, project, version)

    def create_or_clone_version(
        self,
        session: Session,
        project_id: str,
        payload: ForecastVersionCreateRequest,
        *,
        actor_id: str,
    ) -> ForecastVersionRead:
        project = self._get_project_seed(session, project_id)
        forecast = self._get_or_create_forecast(session, project_id)
        existing_draft = self._find_draft(session, forecast.id)
        if existing_draft is not None:
            if payload.base_version_id is None or payload.base_version_id == existing_draft.id:
                before = self._build_version_read(
                    session,
                    project,
                    existing_draft,
                ).model_dump(mode="json")
                existing_draft.title = payload.title or existing_draft.title
                existing_draft.notes_text = payload.notes_text or existing_draft.notes_text
                existing_draft.revision_reason = (
                    payload.revision_reason or existing_draft.revision_reason
                )
                existing_draft.outcome_type_snapshot = self._resolve_bucket(project)
                existing_draft.probability_percent = _normalize_probability(
                    existing_draft.outcome_type_snapshot,
                    payload.probability_percent
                    if payload.probability_percent is not None
                    else float(existing_draft.probability_percent),
                )
                existing_draft.updated_at = datetime.now(UTC)
                forecast.current_version_id = existing_draft.id
                self._sync_version_total(session, existing_draft)
                after = self._build_version_read(
                    session,
                    project,
                    existing_draft,
                ).model_dump(mode="json")
                audit_service.record(
                    session,
                    action="forecast.draft.reused",
                    entity_type="forecast_version",
                    entity_id=existing_draft.id,
                    actor_id=actor_id,
                    project_id=project.id,
                    summary=(
                        f"Reused editable draft v{existing_draft.version_number} for {project.id}."
                    ),
                    before=before,
                    after=after,
                    metadata={
                        "reusedDraftId": existing_draft.id,
                        "sourceQuoteVersionId": existing_draft.source_quote_version_id,
                    },
                )
                return ForecastVersionRead.model_validate(after)
            raise ApiProblemException(
                409,
                "A draft forecast already exists for this project.",
                "Draft Already Exists",
            )

        parent_version: ForecastVersion | None = None
        if payload.base_version_id is not None:
            parent_version = self._get_version_entity(session, payload.base_version_id)
            if parent_version.forecast_id != forecast.id:
                raise ApiProblemException(
                    422,
                    "Base forecast version must belong to the project forecast.",
                    "Invalid Forecast Version",
                )

        prediction_detail = self._load_prediction_detail(session, project, scenario_key="base")
        outcome_type_snapshot = self._resolve_bucket(project)
        predicted_probability_percent = None
        if (
            payload.probability_percent is None
            and parent_version is None
            and isinstance(prediction_detail, dict)
            and outcome_type_snapshot == "bid"
        ):
            scenario = prediction_detail.get("scenario")
            if isinstance(scenario, dict):
                win_probability = scenario.get("winProbability")
                if (
                    isinstance(win_probability, dict)
                    and win_probability.get("probabilityPct") is not None
                ):
                    predicted_probability_percent = float(win_probability["probabilityPct"])

        latest_version_number = session.scalar(
            select(ForecastVersion.version_number)
            .where(ForecastVersion.forecast_id == forecast.id)
            .order_by(desc(ForecastVersion.version_number))
            .limit(1)
        )
        version = ForecastVersion(
            forecast_id=forecast.id,
            parent_version_id=parent_version.id if parent_version is not None else None,
            version_number=(latest_version_number or 0) + 1,
            status=ForecastVersionStatus.draft,
            title=payload.title,
            notes_text=payload.notes_text,
            outcome_type_snapshot=ProjectOutcomeType(outcome_type_snapshot),
            probability_percent=_normalize_probability(
                outcome_type_snapshot,
                payload.probability_percent
                if payload.probability_percent is not None
                else float(parent_version.probability_percent)
                if parent_version is not None
                else predicted_probability_percent,
            ),
            source_quote_version_id=project.current_quote_version_id,
            revision_reason=payload.revision_reason,
            total_amount=0,
            created_by_id=actor_id,
        )
        session.add(version)
        session.flush()

        if parent_version is not None:
            self._clone_lines(session, parent_version, version)
        else:
            self._seed_lines_from_quote(session, version, project)

        self._apply_engine_to_version(
            session,
            project,
            version,
            scenario_key="base",
            prediction_detail=prediction_detail,
            revision_reason=payload.revision_reason,
        )
        forecast.current_version_id = version.id
        session.flush()
        after = self._build_version_read(session, project, version).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.version.created",
            entity_type="forecast_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Created forecast draft v{version.version_number} for {project.id}.",
            after=after,
            metadata={
                "baseVersionId": payload.base_version_id,
                "sourceQuoteVersionId": version.source_quote_version_id,
                "isSourceQuoteCurrent": self._version_source_is_current(project, version),
            },
        )
        return ForecastVersionRead.model_validate(after)

    def promote_prediction_scenario(
        self,
        session: Session,
        project_id: str,
        scenario_output: dict[str, object],
        *,
        prediction_run_id: str | None,
        prediction_confidence_score: float | None,
        prediction_data_sufficiency_score: float | None,
        fallback_tier: str | None,
        title: str | None,
        notes_text: str | None,
        revision_reason: str | None,
        probability_percent: float | None,
        actor_id: str,
    ) -> ForecastVersionRead:
        scenario_key = str(scenario_output.get("scenarioKey", "base"))
        promoted_reason = f"Promoted from predictive scenario {scenario_key}."
        created_version = self.create_or_clone_version(
            session,
            project_id,
            ForecastVersionCreateRequest(
                base_version_id=None,
                title=title or f"{scenario_output.get('title', 'Scenario')} Forecast",
                notes_text=notes_text or promoted_reason,
                probability_percent=probability_percent,
                revision_reason=revision_reason or promoted_reason,
            ),
            actor_id=actor_id,
        )
        forecast, project, version = self._get_version_context(session, created_version.id)
        self._assert_mutable(version, created_version.updated_at)
        prediction_detail = {
            "runId": prediction_run_id,
            "scenarioKey": scenario_output.get("scenarioKey", "base"),
            "scenario": scenario_output,
            "confidenceScore": prediction_confidence_score,
            "dataSufficiencyScore": prediction_data_sufficiency_score,
            "fallbackTier": fallback_tier,
            "methodologySummary": (
                "Promoted from persisted prediction scenario into the unified forecast engine."
            ),
        }

        line_ids = list(
            session.scalars(
                select(ForecastLine.id).where(ForecastLine.forecast_version_id == version.id)
            )
        )
        if line_ids:
            session.execute(
                delete(MonthlyForecastAllocation).where(
                    MonthlyForecastAllocation.forecast_line_id.in_(line_ids)
                )
            )
            session.flush()
        session.execute(delete(ForecastLine).where(ForecastLine.forecast_version_id == version.id))
        session.flush()

        discipline_usage = scenario_output.get("disciplineUsage")
        monthly_revenue_spread = scenario_output.get("monthlyRevenueSpread")
        if not isinstance(discipline_usage, list) or not isinstance(monthly_revenue_spread, list):
            raise ApiProblemException(
                422,
                "Scenario output does not contain a usable discipline or "
                "monthly revenue structure.",
                "Invalid Prediction Scenario",
            )

        currency_code = "GBP"
        likely_quote_range = scenario_output.get("likelyQuoteRange")
        if isinstance(likely_quote_range, dict) and isinstance(
            likely_quote_range.get("currencyCode"), str
        ):
            currency_code = str(likely_quote_range["currencyCode"])

        created_count = 0
        for sort_order, item in enumerate(discipline_usage, start=1):
            line_total = (
                float(item.get("predictedActualAmount"))
                if item.get("predictedActualAmount") is not None
                else float(item.get("predictedAmountMedian") or 0)
            )
            if line_total <= 0:
                continue
            label = (
                item.get("disciplineName")
                or item.get("disciplineCode")
                or item.get("disciplineId")
                or f"Scenario line {sort_order}"
            )
            line = ForecastLine(
                forecast_version_id=version.id,
                sort_order=sort_order,
                discipline_id=item.get("disciplineId"),
                source_quote_line_item_id=None,
                schedule_range_id=None,
                label=str(label),
                allocation_method=ForecastAllocationMethod.schedule,
                total_amount=line_total,
                currency_code=currency_code,
                notes=promoted_reason,
            )
            session.add(line)
            created_count += 1

        project_total = round(
            sum(
                float(item.get("predictedAmountMedian") or 0)
                for item in monthly_revenue_spread
                if isinstance(item, dict)
            ),
            2,
        )

        if created_count == 0 and project_total > 0:
            line = ForecastLine(
                forecast_version_id=version.id,
                sort_order=1,
                discipline_id=None,
                source_quote_line_item_id=None,
                schedule_range_id=None,
                label=str(scenario_output.get("title") or "Scenario revenue"),
                allocation_method=ForecastAllocationMethod.schedule,
                total_amount=project_total,
                currency_code=currency_code,
                notes="Promoted from predictive scenario without discipline breakdown.",
            )
            session.add(line)
        session.flush()
        self._apply_engine_to_version(
            session,
            project,
            version,
            scenario_key=str(scenario_output.get("scenarioKey") or "base"),
            prediction_detail=prediction_detail,
            revision_reason=revision_reason,
        )
        forecast.current_version_id = version.id
        session.flush()
        audit_service.record(
            session,
            action="forecast.prediction.promoted",
            entity_type="forecast_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Promoted predictive scenario into forecast draft v{version.version_number}.",
            metadata={
                "scenarioKey": scenario_output.get("scenarioKey"),
                "createdLineCount": created_count,
            },
        )
        return self._build_version_read(session, project, version)

    def update_version(
        self,
        session: Session,
        version_id: str,
        payload: ForecastVersionUpdateRequest,
        *,
        actor_id: str,
    ) -> ForecastVersionRead:
        forecast, project, version = self._get_version_context(session, version_id)
        self._assert_mutable(version, payload.expected_updated_at)
        before = self._build_version_read(session, project, version).model_dump(mode="json")
        if payload.title is not None:
            version.title = payload.title
        if payload.notes_text is not None:
            version.notes_text = payload.notes_text
        if payload.revision_reason is not None:
            version.revision_reason = payload.revision_reason
        version.outcome_type_snapshot = ProjectOutcomeType(self._resolve_bucket(project))
        version.probability_percent = _normalize_probability(
            version.outcome_type_snapshot.value,
            payload.probability_percent
            if payload.probability_percent is not None
            else float(version.probability_percent),
        )
        version.updated_at = datetime.now(UTC)
        forecast.current_version_id = version.id
        session.flush()
        after = self._build_version_read(session, project, version).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.version.updated",
            entity_type="forecast_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Updated draft v{version.version_number} for {project.id}.",
            before=before,
            after=after,
            metadata={
                "sourceQuoteVersionId": version.source_quote_version_id,
                "isSourceQuoteCurrent": self._version_source_is_current(project, version),
            },
        )
        return ForecastVersionRead.model_validate(after)

    def replace_line_allocations(
        self,
        session: Session,
        line_id: str,
        payload: ForecastLineAllocationsReplaceRequest,
        *,
        actor_id: str,
    ) -> ForecastVersionRead:
        line = session.get(ForecastLine, line_id)
        if line is None:
            raise ApiProblemException(
                404,
                "Forecast line was not found.",
                "Forecast Line Not Found",
            )
        forecast, project, version = self._get_version_context(session, line.forecast_version_id)
        self._assert_mutable(version, payload.expected_updated_at)
        before = self._build_line_read(
            session,
            project,
            line,
            float(version.probability_percent),
        ).model_dump(mode="json")

        if payload.allocation_method not in {"manual", "schedule"}:
            raise ApiProblemException(
                422,
                "Forecast allocation method must be schedule or manual.",
                "Invalid Forecast Allocation Method",
            )

        session.execute(
            delete(MonthlyForecastAllocation).where(
                MonthlyForecastAllocation.forecast_line_id == line.id
            )
        )
        session.flush()

        if payload.allocation_method == "manual":
            normalized_allocations, issues = _validate_manual_allocations(
                _to_cents(float(line.total_amount)),
                payload.allocations,
            )
            if issues:
                raise ApiProblemException(
                    422,
                    "; ".join(issues),
                    "Invalid Manual Allocations",
                )
            line.allocation_method = ForecastAllocationMethod.manual
            if "schedule_range_id" in payload.model_fields_set:
                line.schedule_range_id = payload.schedule_range_id
            for month, amount_in_cents in normalized_allocations:
                session.add(
                    MonthlyForecastAllocation(
                        forecast_line_id=line.id,
                        month=_month_date(month),
                        amount=_from_cents(amount_in_cents),
                        manual_note=payload.reason,
                    )
                )
        else:
            line.allocation_method = ForecastAllocationMethod.schedule
            if "schedule_range_id" in payload.model_fields_set:
                if payload.schedule_range_id is not None:
                    self._ensure_schedule_range(session, payload.schedule_range_id)
                line.schedule_range_id = payload.schedule_range_id

        if payload.reason is not None:
            line.notes = self._append_reason(line.notes, payload.reason)

        version.outcome_type_snapshot = ProjectOutcomeType(self._resolve_bucket(project))
        version.probability_percent = _normalize_probability(
            version.outcome_type_snapshot.value,
            float(version.probability_percent),
        )
        forecast.current_version_id = version.id
        session.flush()
        prediction_detail = self._load_prediction_detail(
            session,
            project,
            scenario_key=version.scenario_key or "base",
        )
        self._apply_engine_to_version(
            session,
            project,
            version,
            scenario_key=version.scenario_key or "base",
            prediction_detail=prediction_detail,
            revision_reason=payload.reason,
        )
        session.flush()
        after = self._build_line_read(
            session,
            project,
            line,
            float(version.probability_percent),
        ).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.line.allocations.replaced",
            entity_type="forecast_line",
            entity_id=line.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Replaced allocations for forecast line {line.label} in {project.id}.",
            before=before,
            after=after,
            metadata={
                "forecastVersionId": version.id,
                "allocationMethod": line.allocation_method.value,
                "reason": payload.reason,
                "scheduleRangeId": line.schedule_range_id,
            },
        )
        return self._build_version_read(session, project, version)

    def submit_version(
        self, session: Session, version_id: str, *, actor_id: str
    ) -> ForecastVersionRead:
        forecast, project, version = self._get_version_context(session, version_id)
        if version.status != ForecastVersionStatus.draft:
            raise ApiProblemException(
                409,
                "Only draft forecast versions can be submitted.",
                "Invalid Forecast Version Transition",
            )
        before = self._build_version_read(session, project, version).model_dump(mode="json")
        computed = self._build_version_read(session, project, version)
        if computed.issues:
            raise ApiProblemException(
                409,
                "Forecast version has validation issues and cannot be submitted.",
                "Forecast Version Invalid",
            )
        version.status = ForecastVersionStatus.submitted
        version.submitted_by_id = actor_id
        version.submitted_at = datetime.now(UTC)
        version.updated_at = datetime.now(UTC)
        forecast.current_version_id = version.id
        session.flush()
        after = self._build_version_read(session, project, version).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.version.submitted",
            entity_type="forecast_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Submitted forecast v{version.version_number} for {project.id}.",
            before=before,
            after=after,
        )
        return ForecastVersionRead.model_validate(after)

    def lock_version(
        self, session: Session, version_id: str, *, actor_id: str
    ) -> ForecastVersionRead:
        forecast, project, version = self._get_version_context(session, version_id)
        if version.status not in {ForecastVersionStatus.draft, ForecastVersionStatus.submitted}:
            raise ApiProblemException(
                409,
                "Only draft or submitted forecast versions can be locked.",
                "Invalid Forecast Version Transition",
            )
        before = self._build_version_read(session, project, version).model_dump(mode="json")
        computed = self._build_version_read(session, project, version)
        if computed.issues:
            raise ApiProblemException(
                409,
                "Forecast version has validation issues and cannot be locked.",
                "Forecast Version Invalid",
            )
        if forecast.current_version_id is not None and forecast.current_version_id != version.id:
            previous = session.get(ForecastVersion, forecast.current_version_id)
            if previous is not None:
                previous.status = ForecastVersionStatus.superseded
                previous.updated_at = datetime.now(UTC)
        version.status = ForecastVersionStatus.locked
        version.locked_by_id = actor_id
        version.locked_at = datetime.now(UTC)
        version.updated_at = datetime.now(UTC)
        forecast.current_version_id = version.id
        session.flush()
        after = self._build_version_read(session, project, version).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.version.locked",
            entity_type="forecast_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Locked forecast v{version.version_number} for {project.id}.",
            before=before,
            after=after,
        )
        return ForecastVersionRead.model_validate(after)

    def record_recalculation_request(
        self, session: Session, project_id: str, *, actor_id: str
    ) -> None:
        project = self._get_project_seed(session, project_id)
        forecast = self._get_or_create_forecast(session, project_id)
        if forecast.current_version_id is None:
            return
        current_version = session.get(ForecastVersion, forecast.current_version_id)
        if current_version is None:
            return
        current_version.outcome_type_snapshot = ProjectOutcomeType(self._resolve_bucket(project))
        current_version.probability_percent = _normalize_probability(
            current_version.outcome_type_snapshot.value,
            float(current_version.probability_percent),
        )
        current_version.updated_at = datetime.now(UTC)
        session.flush()
        audit_service.record(
            session,
            action="forecast.recalculate.requested",
            entity_type="project",
            entity_id=project_id,
            actor_id=actor_id,
            project_id=project_id,
            summary=f"Queued forecast recalculation for {project_id}.",
            metadata={
                "forecastVersionId": current_version.id,
                "sourceQuoteVersionId": current_version.source_quote_version_id,
                "currentQuoteVersionId": project.current_quote_version_id,
            },
        )

    def recalculate_project(
        self, session: Session, project_id: str, *, actor_id: str
    ) -> tuple[ForecastVersionRead | None, str]:
        project = self._get_project_seed(session, project_id)
        forecast = self._get_or_create_forecast(session, project_id)

        target_version = None
        created_new_version = False
        recalculation_message = (
            "Recalculated the current draft forecast against the current quote."
        )
        current_version = (
            session.get(ForecastVersion, forecast.current_version_id)
            if forecast.current_version_id is not None
            else None
        )

        if current_version is None:
            target_version = self.create_or_clone_version(
                session,
                project_id,
                ForecastVersionCreateRequest(
                    title="Forecast Draft",
                    revision_reason="Created during forecast recalculation.",
                ),
                actor_id=actor_id,
            )
            return target_version, "Created the initial draft forecast during recalculation."

        if current_version.status != ForecastVersionStatus.draft:
            existing_draft = self._find_draft(session, forecast.id)
            if existing_draft is not None:
                current_version = existing_draft
                recalculation_message = (
                    "Reused the existing draft forecast and recalculated it against "
                    "the current quote."
                )
            else:
                rebase_from_quote = not self._version_source_is_current(project, current_version)
                target_version = self.create_or_clone_version(
                    session,
                    project_id,
                    ForecastVersionCreateRequest(
                        base_version_id=None if rebase_from_quote else current_version.id,
                        title=current_version.title,
                        notes_text=current_version.notes_text,
                        probability_percent=float(current_version.probability_percent),
                        revision_reason=(
                            "Recalculated from the current quote version."
                            if rebase_from_quote
                            else "Recalculated from the current forecast version."
                        ),
                    ),
                    actor_id=actor_id,
                )
                created_new_version = True
                recalculation_message = (
                    (
                        "Created a new draft from the current quote because "
                        "the active forecast was not editable."
                    )
                    if rebase_from_quote
                    else (
                        "Created a new editable draft and recalculated it against "
                        "the current quote."
                    )
                )
                current_version = self._get_version_entity(session, target_version.id)
                project = self._get_project_seed(session, project_id)

        before = self._build_version_read(session, project, current_version).model_dump(mode="json")
        preserve_manual_lines = self._version_source_is_current(project, current_version)
        if not preserve_manual_lines:
            recalculation_message = (
                "Rebased the draft forecast onto the current quote version during recalculation."
            )
        manual_line_count = self._rebuild_draft_lines(
            session,
            project,
            current_version,
            preserve_manual_lines=preserve_manual_lines,
        )
        prediction_detail = self._load_prediction_detail(
            session,
            project,
            scenario_key=current_version.scenario_key or "base",
        )
        self._apply_engine_to_version(
            session,
            project,
            current_version,
            scenario_key=current_version.scenario_key or "base",
            prediction_detail=prediction_detail,
            revision_reason=current_version.revision_reason,
        )
        forecast.current_version_id = current_version.id
        session.flush()
        after = self._build_version_read(session, project, current_version).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.version.recalculated",
            entity_type="forecast_version",
            entity_id=current_version.id,
            actor_id=actor_id,
            project_id=project_id,
            summary=(f"Recalculated forecast v{current_version.version_number} for {project_id}."),
            before=before,
            after=after,
            metadata={
                "createdNewVersion": created_new_version,
                "preservedManualLines": preserve_manual_lines,
                "manualLineCount": manual_line_count,
                "sourceQuoteVersionId": current_version.source_quote_version_id,
                "currentQuoteVersionId": project.current_quote_version_id,
            },
        )
        return ForecastVersionRead.model_validate(after), recalculation_message

    def _get_project_seed(self, session: Session, project_id: str) -> ProjectSeed:
        project = session.get(Project, project_id)
        if project is None:
            raise ApiProblemException(404, "Project was not found.", "Project Not Found")
        metadata_record = session.scalar(
            select(ProjectMetadata).where(ProjectMetadata.project_id == project.id)
        )
        discipline_lookup = {
            discipline.id: discipline.code for discipline in session.scalars(select(Discipline))
        }

        outcomes = [
            OutcomeSeed(outcome_type=outcome.outcome_type.value, effective_at=outcome.effective_at)
            for outcome in session.scalars(
                select(ProjectOutcome)
                .where(ProjectOutcome.project_id == project.id)
                .order_by(ProjectOutcome.effective_at)
            )
        ]
        schedule_ranges = [
            ScheduleRangeSeed(
                id=item.id,
                label=item.label,
                start_date=item.start_date,
                end_date=item.end_date,
                discipline_id=item.discipline_id,
                discipline_code=discipline_lookup.get(item.discipline_id),
                allocation_percent=float(item.allocation_percent)
                if item.allocation_percent is not None
                else None,
            )
            for item in session.scalars(
                select(ProjectScheduleRange)
                .where(ProjectScheduleRange.project_id == project.id)
                .order_by(ProjectScheduleRange.start_date)
            )
        ]

        current_quote_version_id = None
        quote_lines: list[QuoteLineSeed] = []
        current_quote = session.scalar(
            select(Quote)
            .where(Quote.project_id == project.id)
            .order_by(desc(Quote.updated_at))
            .limit(1)
        )
        if current_quote is not None:
            current_quote_version_id = current_quote.current_version_id
        if current_quote_version_id is not None:
            sections = list(
                session.scalars(
                    select(QuoteSection)
                    .where(QuoteSection.quote_version_id == current_quote_version_id)
                    .order_by(QuoteSection.sort_order)
                )
            )
            for section in sections:
                line_items = list(
                    session.scalars(
                        select(QuoteLineItem)
                        .where(QuoteLineItem.quote_section_id == section.id)
                        .order_by(QuoteLineItem.sort_order)
                    )
                )
                for item in line_items:
                    quote_lines.append(
                        QuoteLineSeed(
                            id=item.id,
                            label=item.description,
                            discipline_id=item.discipline_id,
                            discipline_code=discipline_lookup.get(item.discipline_id),
                            amount_in_cents=_to_cents(float(item.amount)),
                            currency_code=self._quote_currency_code(
                                session,
                                current_quote_version_id,
                            ),
                        )
                    )

        actuals_by_discipline_month: dict[str, dict[str, float]] = {}
        actuals_by_project_month: dict[str, float] = {}
        actual_rows = list(
            session.scalars(
                select(MappedActual).where(
                    MappedActual.project_id == project.id,
                    MappedActual.is_current.is_(True),
                    MappedActual.financial_type == CetaRowFinancialType.revenue,
                )
            )
        )
        for actual in actual_rows:
            month = _month_key(actual.work_date or actual.posting_date or date.today())
            actuals_by_project_month[month] = round(
                actuals_by_project_month.get(month, 0.0) + float(actual.amount),
                2,
            )
            if actual.discipline_id is None:
                continue
            discipline_months = actuals_by_discipline_month.setdefault(actual.discipline_id, {})
            discipline_months[month] = round(
                discipline_months.get(month, 0.0) + float(actual.amount),
                2,
            )

        return ProjectSeed(
            id=project.id,
            name=project.name,
            status=project.status.value,
            start_date=project.start_date,
            end_date=project.end_date,
            pipeline_stage_key=project.pipeline_stage_key,
            project_format_key=(
                metadata_record.project_format_key
                if metadata_record is not None and metadata_record.project_format_key
                else metadata_record.format_type
                if metadata_record is not None
                else None
            ),
            duration_weeks=(
                int(metadata_record.duration_weeks)
                if metadata_record is not None and metadata_record.duration_weeks is not None
                else None
            ),
            episode_count=(
                int(metadata_record.episode_count)
                if metadata_record is not None and metadata_record.episode_count is not None
                else None
            ),
            metadata_json=metadata_record.metadata_json if metadata_record is not None else None,
            current_quote_version_id=current_quote_version_id,
            outcomes=outcomes,
            schedule_ranges=schedule_ranges,
            quote_lines=quote_lines,
            actuals_by_discipline_month=actuals_by_discipline_month,
            actuals_by_project_month=actuals_by_project_month,
        )

    def _discipline_code_lookup(self, project: ProjectSeed) -> dict[str, str | None]:
        lookup: dict[str, str | None] = {}
        for item in project.quote_lines:
            if item.discipline_id is not None:
                lookup[item.discipline_id] = item.discipline_code
        for item in project.schedule_ranges:
            if item.discipline_id is not None:
                lookup[item.discipline_id] = item.discipline_code
        return lookup

    def _validation_context(self, project: ProjectSeed) -> ForecastValidationProjectContext:
        return ForecastValidationProjectContext(
            project_id=project.id,
            project_name=project.name,
            status=project.status,
            start_date=project.start_date,
            end_date=project.end_date,
            project_format_key=project.project_format_key,
            duration_weeks=project.duration_weeks,
            episode_count=project.episode_count,
            metadata_json=project.metadata_json,
            current_quote_version_id=project.current_quote_version_id,
            schedule_ranges=[
                ForecastValidationScheduleRange(
                    id=item.id,
                    label=item.label,
                    start_date=item.start_date,
                    end_date=item.end_date,
                    discipline_id=item.discipline_id,
                    discipline_code=item.discipline_code,
                    allocation_percent=item.allocation_percent,
                )
                for item in project.schedule_ranges
            ],
            quote_lines=[
                ForecastValidationQuoteLine(
                    id=item.id,
                    label=item.label,
                    discipline_id=item.discipline_id,
                    discipline_code=item.discipline_code,
                    amount=_from_cents(item.amount_in_cents),
                )
                for item in project.quote_lines
            ],
            actuals_by_discipline_month=project.actuals_by_discipline_month,
            actuals_by_project_month=project.actuals_by_project_month,
        )

    def _load_prediction_scenario_output(
        self,
        session: Session,
        version: ForecastVersion,
    ) -> dict[str, Any] | None:
        if version.prediction_run_id is None:
            return None
        scenario_key = version.prediction_scenario_key or version.scenario_key or "base"
        scenario = session.scalar(
            select(PredictionScenario).where(
                PredictionScenario.prediction_run_id == version.prediction_run_id,
                PredictionScenario.scenario_key == scenario_key,
            )
        )
        if scenario is None or not isinstance(scenario.output_json, dict):
            return None
        return scenario.output_json

    def _quote_currency_code(self, session: Session, quote_version_id: str) -> str:
        version = session.get(QuoteVersion, quote_version_id)
        if version is None:
            return "GBP"
        return version.currency_code

    def _get_or_create_forecast(self, session: Session, project_id: str) -> Forecast:
        existing = session.scalar(select(Forecast).where(Forecast.project_id == project_id))
        if existing is not None:
            return existing
        forecast = Forecast(project_id=project_id)
        session.add(forecast)
        session.flush()
        return forecast

    def _find_draft(self, session: Session, forecast_id: str) -> ForecastVersion | None:
        return session.scalar(
            select(ForecastVersion)
            .where(
                ForecastVersion.forecast_id == forecast_id,
                ForecastVersion.status == ForecastVersionStatus.draft,
            )
            .order_by(desc(ForecastVersion.version_number))
            .limit(1)
        )

    def _version_source_is_current(self, project: ProjectSeed, version: ForecastVersion) -> bool:
        return version.source_quote_version_id == project.current_quote_version_id

    def _resolve_bucket(self, project: ProjectSeed) -> str:
        if project.status == "lost":
            return "lost"
        terminal_outcomes = [
            outcome for outcome in project.outcomes if outcome.outcome_type != "bid"
        ]
        terminal_outcomes.sort(key=lambda outcome: outcome.effective_at, reverse=True)
        if terminal_outcomes:
            return terminal_outcomes[0].outcome_type
        if project.status in {"awarded", "active", "complete"}:
            return "awarded"
        return "bid"

    def _resolve_schedule_ranges(
        self, project: ProjectSeed, discipline_id: str | None, schedule_range_id: str | None
    ) -> tuple[list[ScheduleRangeSeed], list[str]]:
        if schedule_range_id is not None:
            matching_range = next(
                (item for item in project.schedule_ranges if item.id == schedule_range_id),
                None,
            )
            if matching_range is None:
                return [], [f"Schedule range {schedule_range_id} was not found."]
            return [matching_range], []

        if discipline_id is None:
            return [], ["Schedule line requires a discipline."]

        discipline_ranges = [
            item for item in project.schedule_ranges if item.discipline_id == discipline_id
        ]
        if not discipline_ranges:
            discipline_ranges = [
                item for item in project.schedule_ranges if item.discipline_id is None
            ]
        if not discipline_ranges:
            return [], ["No schedule ranges were found for this line."]
        if len(discipline_ranges) == 1:
            return discipline_ranges, []
        if any(item.allocation_percent is None for item in discipline_ranges):
            return [], ["Schedule ranges need allocation percentages to split a line."]
        total_percent = round(sum(item.allocation_percent or 0 for item in discipline_ranges), 2)
        if total_percent != 100:
            return [], ["Schedule range percentages must total 100."]
        ordered = sorted(discipline_ranges, key=lambda item: item.start_date)
        for index in range(1, len(ordered)):
            if ordered[index].start_date <= ordered[index - 1].end_date:
                return [], ["Schedule ranges overlap and cannot be auto-spread."]
        return ordered, []

    def _split_amounts_for_ranges(
        self, total_amount_in_cents: int, ranges: list[ScheduleRangeSeed]
    ) -> list[tuple[ScheduleRangeSeed, int]]:
        if len(ranges) == 1:
            return [(ranges[0], total_amount_in_cents)]

        total_percent = sum(range_item.allocation_percent or 0 for range_item in ranges)
        if total_percent <= 0:
            raise ApiProblemException(
                422,
                "Schedule ranges need positive allocation percentages to split a line.",
                "Invalid Schedule Range",
            )

        weighted: list[dict[str, object]] = []
        for range_item in ranges:
            percent = range_item.allocation_percent or 0
            raw_amount = (total_amount_in_cents * percent) / total_percent
            floor_amount = int(raw_amount // 1)
            weighted.append(
                {
                    "range": range_item,
                    "floor_amount": floor_amount,
                    "remainder": raw_amount - floor_amount,
                    "sort_key": range_item.id,
                }
            )

        remainder = total_amount_in_cents - sum(int(item["floor_amount"]) for item in weighted)
        for item in _sort_with_remainder(weighted):
            if remainder <= 0:
                break
            item["floor_amount"] = int(item["floor_amount"]) + 1
            remainder -= 1

        return [
            (item["range"], int(item["floor_amount"]))  # type: ignore[index]
            for item in weighted
        ]

    def _build_manual_seed_from_line(
        self, session: Session, line: ForecastLine
    ) -> ForecastLineSeed:
        allocations = [
            (_month_key(allocation.month), _to_cents(float(allocation.amount)))
            for allocation in session.scalars(
                select(MonthlyForecastAllocation)
                .where(MonthlyForecastAllocation.forecast_line_id == line.id)
                .order_by(MonthlyForecastAllocation.month)
            )
        ]
        total_amount_in_cents = sum(amount for _, amount in allocations)
        if total_amount_in_cents == 0:
            total_amount_in_cents = _to_cents(float(line.total_amount))

        return ForecastLineSeed(
            label=line.label,
            total_amount_in_cents=total_amount_in_cents,
            currency_code=line.currency_code,
            allocation_method=ForecastAllocationMethod.manual.value,
            discipline_id=line.discipline_id,
            schedule_range_id=line.schedule_range_id,
            source_quote_line_item_id=line.source_quote_line_item_id,
            notes=line.notes,
            manual_allocations=allocations,
        )

    def _build_seed_line_label(
        self,
        quote_label: str,
        range_item: ScheduleRangeSeed | None,
        *,
        show_range_label: bool,
    ) -> str:
        if range_item is None or not show_range_label:
            return quote_label

        return f"{quote_label} - {range_item.label}"

    def _build_unresolved_schedule_seed(
        self,
        quote_line: QuoteLineSeed,
        *,
        total_amount_in_cents: int | None = None,
    ) -> ForecastLineSeed:
        return ForecastLineSeed(
            label=quote_line.label,
            total_amount_in_cents=(
                quote_line.amount_in_cents
                if total_amount_in_cents is None
                else total_amount_in_cents
            ),
            currency_code=quote_line.currency_code,
            allocation_method=ForecastAllocationMethod.schedule.value,
            discipline_id=quote_line.discipline_id,
            source_quote_line_item_id=quote_line.id,
        )

    def _build_schedule_seed_lines(
        self,
        quote_line: QuoteLineSeed,
        ranges: list[ScheduleRangeSeed],
        *,
        total_amount_in_cents: int | None = None,
        show_range_labels: bool | None = None,
    ) -> list[ForecastLineSeed]:
        schedule_amount = (
            quote_line.amount_in_cents if total_amount_in_cents is None else total_amount_in_cents
        )
        include_range_labels = len(ranges) > 1 if show_range_labels is None else show_range_labels
        return [
            ForecastLineSeed(
                label=self._build_seed_line_label(
                    quote_line.label,
                    range_item,
                    show_range_label=include_range_labels,
                ),
                total_amount_in_cents=split_amount,
                currency_code=quote_line.currency_code,
                allocation_method=ForecastAllocationMethod.schedule.value,
                discipline_id=quote_line.discipline_id,
                schedule_range_id=range_item.id,
                source_quote_line_item_id=quote_line.id,
            )
            for range_item, split_amount in self._split_amounts_for_ranges(
                schedule_amount,
                ranges,
            )
        ]

    def _rebuild_draft_lines(
        self,
        session: Session,
        project: ProjectSeed,
        version: ForecastVersion,
        *,
        preserve_manual_lines: bool,
    ) -> int:
        existing_lines = list(
            session.scalars(
                select(ForecastLine)
                .where(ForecastLine.forecast_version_id == version.id)
                .order_by(ForecastLine.sort_order)
            )
        )
        manual_line_seeds: dict[str, list[ForecastLineSeed]] = {}
        orphan_manual_line_seeds: list[ForecastLineSeed] = []
        manual_line_count = 0

        if preserve_manual_lines:
            for line in existing_lines:
                if line.allocation_method != ForecastAllocationMethod.manual:
                    continue
                manual_line_count += 1
                seed = self._build_manual_seed_from_line(session, line)
                if line.source_quote_line_item_id is not None:
                    manual_line_seeds.setdefault(line.source_quote_line_item_id, []).append(seed)
                else:
                    orphan_manual_line_seeds.append(seed)

        existing_line_ids = [line.id for line in existing_lines]
        if existing_line_ids:
            session.execute(
                delete(MonthlyForecastAllocation).where(
                    MonthlyForecastAllocation.forecast_line_id.in_(existing_line_ids)
                )
            )
            session.execute(
                delete(ForecastLine).where(ForecastLine.forecast_version_id == version.id)
            )
            session.flush()

        refreshed_lines: list[ForecastLineSeed] = []
        for quote_line in project.quote_lines:
            ranges, issues = self._resolve_schedule_ranges(project, quote_line.discipline_id, None)
            preserved_manual_seeds = manual_line_seeds.pop(quote_line.id, [])

            if preserved_manual_seeds:
                range_lookup = {range_item.id: range_item for range_item in ranges}
                manual_total_amount_in_cents = 0
                manual_range_ids = {
                    seed.schedule_range_id
                    for seed in preserved_manual_seeds
                    if seed.schedule_range_id is not None
                }

                for seed in preserved_manual_seeds:
                    matching_range = (
                        range_lookup.get(seed.schedule_range_id)
                        if seed.schedule_range_id is not None
                        else None
                    )
                    seed.label = self._build_seed_line_label(
                        quote_line.label,
                        matching_range,
                        show_range_label=len(ranges) > 1,
                    )
                    seed.currency_code = quote_line.currency_code
                    seed.discipline_id = quote_line.discipline_id
                    refreshed_lines.append(seed)
                    manual_total_amount_in_cents += seed.total_amount_in_cents

                remaining_amount_in_cents = (
                    quote_line.amount_in_cents - manual_total_amount_in_cents
                )
                if remaining_amount_in_cents <= 0:
                    continue

                if issues:
                    refreshed_lines.append(
                        self._build_unresolved_schedule_seed(
                            quote_line,
                            total_amount_in_cents=remaining_amount_in_cents,
                        )
                    )
                    continue

                remaining_ranges = [
                    range_item for range_item in ranges if range_item.id not in manual_range_ids
                ]
                if not remaining_ranges:
                    refreshed_lines.append(
                        self._build_unresolved_schedule_seed(
                            quote_line,
                            total_amount_in_cents=remaining_amount_in_cents,
                        )
                    )
                    continue

                refreshed_lines.extend(
                    self._build_schedule_seed_lines(
                        quote_line,
                        remaining_ranges,
                        total_amount_in_cents=remaining_amount_in_cents,
                        show_range_labels=len(ranges) > 1,
                    )
                )
                continue

            if issues:
                refreshed_lines.append(self._build_unresolved_schedule_seed(quote_line))
                continue

            refreshed_lines.extend(self._build_schedule_seed_lines(quote_line, ranges))

        for seeds in manual_line_seeds.values():
            refreshed_lines.extend(seeds)
        refreshed_lines.extend(orphan_manual_line_seeds)
        self._persist_seed_lines(session, version, refreshed_lines)
        version.source_quote_version_id = project.current_quote_version_id
        version.outcome_type_snapshot = ProjectOutcomeType(self._resolve_bucket(project))
        version.probability_percent = _normalize_probability(
            version.outcome_type_snapshot.value,
            float(version.probability_percent),
        )
        version.updated_at = datetime.now(UTC)
        self._sync_version_total(session, version)
        session.flush()
        return manual_line_count

    def _seed_lines_from_quote(
        self, session: Session, version: ForecastVersion, project: ProjectSeed
    ) -> None:
        seeded_lines: list[ForecastLineSeed] = []
        for quote_line in project.quote_lines:
            ranges, issues = self._resolve_schedule_ranges(project, quote_line.discipline_id, None)
            if issues:
                seeded_lines.append(self._build_unresolved_schedule_seed(quote_line))
                continue
            seeded_lines.extend(self._build_schedule_seed_lines(quote_line, ranges))
        self._persist_seed_lines(session, version, seeded_lines)

    def _load_prediction_detail(
        self,
        session: Session,
        project: ProjectSeed,
        *,
        scenario_key: str,
    ) -> dict[str, object] | None:
        try:
            from app.modules.predictions.service import prediction_service
        except Exception:
            return None

        try:
            detail = prediction_service.get_project_predictive_guidance(
                session,
                project.id,
                quote_version_id=project.current_quote_version_id,
                limit=25,
                discipline_id=None,
            )
        except Exception:
            return None

        if not isinstance(detail, dict):
            return None

        scenarios = detail.get("scenarios")
        scenario_output = None
        if isinstance(scenarios, list):
            scenario_output = next(
                (
                    item
                    for item in scenarios
                    if isinstance(item, dict) and item.get("scenarioKey") == scenario_key
                ),
                None,
            )
        if scenario_output is None and isinstance(scenarios, list):
            scenario_output = next(
                (item for item in scenarios if isinstance(item, dict) and item.get("isExpected")),
                None,
            )
        if scenario_output is None:
            scenario_output = {
                "scenarioKey": scenario_key,
                "monthlyRevenueSpread": detail.get("monthlyRevenueSpread", []),
                "disciplineUsage": detail.get("disciplineUsage", []),
                "winProbability": detail.get("winProbability"),
            }

        return {
            "runId": detail.get("id"),
            "scenarioKey": scenario_output.get("scenarioKey", scenario_key)
            if isinstance(scenario_output, dict)
            else scenario_key,
            "scenario": scenario_output,
            "confidenceScore": detail.get("confidenceScore"),
            "dataSufficiencyScore": detail.get("dataSufficiencyScore"),
            "fallbackTier": detail.get("fallbackTier"),
            "methodologySummary": detail.get("methodologySummary"),
        }

    def _build_engine_context(
        self,
        session: Session,
        project: ProjectSeed,
        *,
        prediction_detail: dict[str, object] | None,
    ) -> ForecastEngineProjectContext:
        scenario = (
            prediction_detail.get("scenario") if isinstance(prediction_detail, dict) else None
        )
        discipline_predictions: dict[str, dict[str, object]] = {}
        if isinstance(scenario, dict) and isinstance(scenario.get("disciplineUsage"), list):
            for item in scenario["disciplineUsage"]:
                if isinstance(item, dict) and item.get("disciplineId"):
                    discipline_predictions[str(item["disciplineId"])] = item

        project_curve = []
        if isinstance(scenario, dict) and isinstance(scenario.get("monthlyRevenueSpread"), list):
            project_curve = [
                item for item in scenario["monthlyRevenueSpread"] if isinstance(item, dict)
            ]

        return ForecastEngineProjectContext(
            project_id=project.id,
            project_format_key=project.project_format_key,
            metadata_json=project.metadata_json,
            episode_count=project.episode_count,
            duration_weeks=project.duration_weeks,
            start_date=project.start_date,
            end_date=project.end_date,
            schedule_ranges=[
                ForecastEngineScheduleRange(
                    id=item.id,
                    label=item.label,
                    start_date=item.start_date,
                    end_date=item.end_date,
                    discipline_id=item.discipline_id,
                )
                for item in project.schedule_ranges
            ],
            project_curve=project_curve,
            discipline_predictions=discipline_predictions,
            actuals_by_discipline_month=project.actuals_by_discipline_month,
            actuals_by_project_month=project.actuals_by_project_month,
            prediction_run_id=(
                str(prediction_detail.get("runId"))
                if isinstance(prediction_detail, dict) and prediction_detail.get("runId")
                else None
            ),
            prediction_scenario_key=(
                str(prediction_detail.get("scenarioKey"))
                if isinstance(prediction_detail, dict) and prediction_detail.get("scenarioKey")
                else None
            ),
            fallback_tier=(
                str(prediction_detail.get("fallbackTier"))
                if isinstance(prediction_detail, dict) and prediction_detail.get("fallbackTier")
                else None
            ),
            confidence_score=(
                float(prediction_detail.get("confidenceScore"))
                if isinstance(prediction_detail, dict)
                and prediction_detail.get("confidenceScore") is not None
                else None
            ),
            data_sufficiency_score=(
                float(prediction_detail.get("dataSufficiencyScore"))
                if isinstance(prediction_detail, dict)
                and prediction_detail.get("dataSufficiencyScore") is not None
                else None
            ),
            curve_profiles=self._curve_profile_registry(session),
            sequence_templates=self._sequence_template_registry(session),
        )

    def _project_month_totals_from_version(
        self, session: Session, version: ForecastVersion
    ) -> dict[str, float]:
        totals: dict[str, float] = {}
        line_ids = list(
            session.scalars(
                select(ForecastLine.id).where(ForecastLine.forecast_version_id == version.id)
            )
        )
        if not line_ids:
            return totals
        allocations = list(
            session.scalars(
                select(MonthlyForecastAllocation).where(
                    MonthlyForecastAllocation.forecast_line_id.in_(line_ids)
                )
            )
        )
        for allocation in allocations:
            key = _month_key(allocation.month)
            totals[key] = round(totals.get(key, 0.0) + float(allocation.amount), 2)
        return totals

    def _apply_engine_to_version(
        self,
        session: Session,
        project: ProjectSeed,
        version: ForecastVersion,
        *,
        scenario_key: str = "base",
        prediction_detail: dict[str, object] | None = None,
        revision_reason: str | None = None,
    ) -> None:
        before_months = self._project_month_totals_from_version(session, version)
        before_total_amount = float(version.total_amount or 0)
        before_weighted_total_amount = round(
            before_total_amount * (float(version.probability_percent) / 100),
            2,
        )

        engine_context = self._build_engine_context(
            session,
            project,
            prediction_detail=prediction_detail,
        )
        existing_lines = list(
            session.scalars(
                select(ForecastLine)
                .where(ForecastLine.forecast_version_id == version.id)
                .order_by(ForecastLine.sort_order)
            )
        )
        manual_allocations_by_line: dict[str, list[tuple[str, float]]] = {}
        line_ids = [line.id for line in existing_lines]
        if line_ids:
            allocations = list(
                session.scalars(
                    select(MonthlyForecastAllocation)
                    .where(MonthlyForecastAllocation.forecast_line_id.in_(line_ids))
                    .order_by(MonthlyForecastAllocation.month)
                )
            )
            for allocation in allocations:
                line = next(
                    (item for item in existing_lines if item.id == allocation.forecast_line_id),
                    None,
                )
                if line is None or line.allocation_method != ForecastAllocationMethod.manual:
                    continue
                manual_allocations_by_line.setdefault(line.id, []).append(
                    (_month_key(allocation.month), float(allocation.amount))
                )
            session.execute(
                delete(MonthlyForecastAllocation).where(
                    MonthlyForecastAllocation.forecast_line_id.in_(line_ids)
                )
            )
            session.flush()

        for line in existing_lines:
            discipline_code = next(
                (
                    quote_line.discipline_code
                    for quote_line in project.quote_lines
                    if quote_line.id == line.source_quote_line_item_id
                ),
                next(
                    (
                        schedule_range.discipline_code
                        for schedule_range in project.schedule_ranges
                        if schedule_range.id == line.schedule_range_id
                    ),
                    None,
                ),
            )
            plan = build_line_plan(
                engine_context,
                ForecastEngineLineInput(
                    line_id=line.id,
                    label=line.label,
                    total_amount=float(line.total_amount),
                    discipline_id=line.discipline_id,
                    discipline_code=discipline_code,
                    schedule_range_id=line.schedule_range_id,
                    manual_allocations=manual_allocations_by_line.get(line.id, []),
                    notes=line.notes,
                ),
            )
            merged_allocations = _merge_engine_allocations(
                [
                    (
                        allocation.month,
                        allocation.amount,
                        allocation.low_amount,
                        allocation.high_amount,
                        allocation.allocation_source,
                        allocation.actual_amount,
                        allocation.source_context,
                    )
                    for allocation in plan.allocations
                ]
            )
            if merged_allocations:
                line.total_amount = round(
                    sum(amount for _, amount, _, _, _, _, _ in merged_allocations),
                    2,
                )
            line.forecast_method_key = plan.forecast_method_key
            line.allocation_profile_key = plan.allocation_profile_key
            line.sequencing_template_key = plan.sequencing_template_key
            line.sequencing_stage_key = plan.sequencing_stage_key
            line.overlap_percent = plan.overlap_percent
            line.confidence_score = plan.confidence_score
            line.data_sufficiency_score = plan.data_sufficiency_score
            line.fallback_tier = plan.fallback_tier
            line.actuals_to_date_amount = plan.actuals_to_date_amount
            line.remaining_amount = plan.remaining_amount
            line.forecast_inputs_json = plan.forecast_inputs
            line.explanation_json = plan.explanations
            for (
                month,
                amount,
                low_amount,
                high_amount,
                allocation_source,
                actual_amount,
                source_context,
            ) in merged_allocations:
                session.add(
                    MonthlyForecastAllocation(
                        forecast_line_id=line.id,
                        month=_month_date(month),
                        amount=amount,
                        low_amount=low_amount,
                        high_amount=high_amount,
                        actual_amount=actual_amount,
                        allocation_source=allocation_source,
                        source_context_json=source_context,
                        manual_note=(
                            "Manual override" if allocation_source == "manual_override" else None
                        ),
                    )
                )

        version.scenario_key = scenario_key
        version.engine_source = "unified_forecast_engine"
        version.prediction_run_id = engine_context.prediction_run_id
        version.prediction_scenario_key = engine_context.prediction_scenario_key or scenario_key
        version.confidence_score = engine_context.confidence_score
        version.data_sufficiency_score = engine_context.data_sufficiency_score
        version.fallback_tier = engine_context.fallback_tier
        version.explanation_summary_json = {
            "methodologySummary": (
                prediction_detail.get("methodologySummary")
                if isinstance(prediction_detail, dict)
                else None
            ),
            "projectFormatKey": project.project_format_key,
            "actualMonthCount": len(project.actuals_by_project_month),
            "scenarioKey": scenario_key,
        }
        self._sync_version_total(session, version)
        current_months = self._project_month_totals_from_version(session, version)
        current_weighted_total_amount = round(
            float(version.total_amount) * (float(version.probability_percent) / 100),
            2,
        )
        version.change_summary_json = summarize_version_delta(
            previous_total_amount=before_total_amount,
            current_total_amount=float(version.total_amount),
            previous_weighted_total_amount=before_weighted_total_amount,
            current_weighted_total_amount=current_weighted_total_amount,
            previous_months=before_months,
            current_months=current_months,
            reason=revision_reason,
            scenario_key=scenario_key,
        )
        version.updated_at = datetime.now(UTC)
        session.flush()

    def _persist_seed_lines(
        self, session: Session, version: ForecastVersion, lines: list[ForecastLineSeed]
    ) -> None:
        for index, item in enumerate(lines, start=1):
            line = ForecastLine(
                forecast_version_id=version.id,
                sort_order=index,
                discipline_id=item.discipline_id,
                source_quote_line_item_id=item.source_quote_line_item_id,
                schedule_range_id=item.schedule_range_id,
                label=item.label,
                allocation_method=ForecastAllocationMethod(item.allocation_method),
                total_amount=_from_cents(item.total_amount_in_cents),
                currency_code=item.currency_code,
                notes=item.notes,
            )
            session.add(line)
            session.flush()
            for month, amount_in_cents in item.manual_allocations:
                session.add(
                    MonthlyForecastAllocation(
                        forecast_line_id=line.id,
                        month=_month_date(month),
                        amount=_from_cents(amount_in_cents),
                    )
                )
        session.flush()

    def _clone_lines(
        self,
        session: Session,
        source_version: ForecastVersion,
        target_version: ForecastVersion,
    ) -> None:
        source_lines = list(
            session.scalars(
                select(ForecastLine)
                .where(ForecastLine.forecast_version_id == source_version.id)
                .order_by(ForecastLine.sort_order)
            )
        )
        for source_line in source_lines:
            cloned = ForecastLine(
                forecast_version_id=target_version.id,
                sort_order=source_line.sort_order,
                discipline_id=source_line.discipline_id,
                source_quote_line_item_id=source_line.source_quote_line_item_id,
                schedule_range_id=source_line.schedule_range_id,
                label=source_line.label,
                allocation_method=source_line.allocation_method,
                total_amount=source_line.total_amount,
                currency_code=source_line.currency_code,
                notes=source_line.notes,
            )
            session.add(cloned)
            session.flush()
            source_allocations = list(
                session.scalars(
                    select(MonthlyForecastAllocation)
                    .where(MonthlyForecastAllocation.forecast_line_id == source_line.id)
                    .order_by(MonthlyForecastAllocation.month)
                )
            )
            for allocation in source_allocations:
                session.add(
                    MonthlyForecastAllocation(
                        forecast_line_id=cloned.id,
                        month=allocation.month,
                        amount=allocation.amount,
                        manual_note=allocation.manual_note,
                    )
                )
        session.flush()

    def _sync_version_total(self, session: Session, version: ForecastVersion) -> None:
        total = sum(
            float(line.total_amount)
            for line in session.scalars(
                select(ForecastLine).where(ForecastLine.forecast_version_id == version.id)
            )
        )
        version.total_amount = total
        session.flush()

    def _assert_mutable(self, version: ForecastVersion, expected_updated_at: datetime) -> None:
        if version.status != ForecastVersionStatus.draft:
            raise ApiProblemException(
                409,
                "Only draft forecast versions can be edited.",
                "Forecast Version Not Editable",
            )
        if not same_timestamp(version.updated_at, expected_updated_at):
            raise ApiProblemException(
                409,
                "Forecast version has been updated by another request.",
                "Forecast Version Conflict",
            )

    def _get_version_context(
        self, session: Session, version_id: str
    ) -> tuple[Forecast, ProjectSeed, ForecastVersion]:
        version = self._get_version_entity(session, version_id)
        forecast = session.get(Forecast, version.forecast_id)
        if forecast is None:
            raise ApiProblemException(404, "Forecast was not found.", "Forecast Not Found")
        project = self._get_project_seed(session, forecast.project_id)
        return forecast, project, version

    def _get_version_entity(self, session: Session, version_id: str) -> ForecastVersion:
        version = session.get(ForecastVersion, version_id)
        if version is None:
            raise ApiProblemException(
                404,
                "Forecast version was not found.",
                "Forecast Version Not Found",
            )
        return version

    def _build_line_read(
        self,
        session: Session,
        project: ProjectSeed,
        line: ForecastLine,
        probability_percent: float,
    ) -> ForecastLineRead:
        issues: list[str] = []
        stored_allocations = list(
            session.scalars(
                select(MonthlyForecastAllocation)
                .where(MonthlyForecastAllocation.forecast_line_id == line.id)
                .order_by(MonthlyForecastAllocation.month)
            )
        )

        base_allocations: list[tuple[str, int]] = []
        allocation_lookup: dict[str, MonthlyForecastAllocation] = {}
        line_total_cents = _to_cents(float(line.total_amount))
        if stored_allocations:
            base_allocations = [
                (_month_key(allocation.month), _to_cents(float(allocation.amount)))
                for allocation in stored_allocations
            ]
            allocation_lookup = {
                _month_key(allocation.month): allocation for allocation in stored_allocations
            }
            if line.allocation_method == ForecastAllocationMethod.manual:
                normalized_allocations = [
                    ForecastLineMonthAllocationWrite(
                        month=month,
                        amount=_from_cents(amount_in_cents),
                    )
                    for month, amount_in_cents in base_allocations
                ]
                _normalized, issues = _validate_manual_allocations(
                    line_total_cents,
                    normalized_allocations,
                )
        elif line.allocation_method == ForecastAllocationMethod.manual:
            issues.append("Manual forecast line is missing month allocations.")
        else:
            ranges, range_issues = self._resolve_schedule_ranges(
                project,
                line.discipline_id,
                line.schedule_range_id,
            )
            if range_issues:
                issues.extend(range_issues)
            elif len(ranges) != 1:
                issues.append("Schedule line must resolve to exactly one schedule range.")
            else:
                range_item = ranges[0]
                base_allocations = _build_schedule_monthly_allocations(
                    range_item.start_date,
                    range_item.end_date,
                    line_total_cents,
                )

        weighted_allocations = _build_weighted_allocations(base_allocations, probability_percent)
        allocations = []
        for month, amount_in_cents, weighted_amount_in_cents in weighted_allocations:
            source_row = allocation_lookup.get(month)
            low_amount = (
                float(source_row.low_amount)
                if source_row and source_row.low_amount is not None
                else None
            )
            high_amount = (
                float(source_row.high_amount)
                if source_row and source_row.high_amount is not None
                else None
            )
            actual_amount = (
                float(source_row.actual_amount)
                if source_row and source_row.actual_amount is not None
                else None
            )
            allocations.append(
                ForecastMonthlyAllocationRead(
                    month=month,
                    amount=_from_cents(amount_in_cents),
                    weighted_amount=_from_cents(weighted_amount_in_cents),
                    low_amount=low_amount,
                    high_amount=high_amount,
                    actual_amount=actual_amount,
                    allocation_source=source_row.allocation_source if source_row else None,
                    source_context=source_row.source_context_json if source_row else None,
                )
            )

        overlap_percent = float(line.overlap_percent) if line.overlap_percent is not None else None
        confidence_score = (
            float(line.confidence_score) if line.confidence_score is not None else None
        )
        data_sufficiency_score = (
            float(line.data_sufficiency_score) if line.data_sufficiency_score is not None else None
        )
        actuals_to_date_amount = (
            float(line.actuals_to_date_amount) if line.actuals_to_date_amount is not None else None
        )
        remaining_amount = (
            float(line.remaining_amount) if line.remaining_amount is not None else None
        )
        return ForecastLineRead(
            id=line.id,
            source_line_id=line.source_quote_line_item_id or line.id,
            label=line.label,
            total_amount=_from_cents(sum(amount for _, amount in base_allocations)),
            weighted_total_amount=_from_cents(
                sum(weighted_amount for _, _, weighted_amount in weighted_allocations)
            ),
            currency_code=line.currency_code,
            allocation_method=line.allocation_method.value,
            discipline_id=line.discipline_id,
            schedule_range_id=line.schedule_range_id,
            notes=line.notes,
            forecast_method_key=line.forecast_method_key,
            allocation_profile_key=line.allocation_profile_key,
            sequencing_template_key=line.sequencing_template_key,
            sequencing_stage_key=line.sequencing_stage_key,
            overlap_percent=overlap_percent,
            confidence_score=confidence_score,
            data_sufficiency_score=data_sufficiency_score,
            fallback_tier=line.fallback_tier,
            actuals_to_date_amount=actuals_to_date_amount,
            remaining_amount=remaining_amount,
            forecast_inputs=line.forecast_inputs_json,
            explanations=[
                ForecastExplanationRead.model_validate(item)
                for item in (line.explanation_json or [])
                if isinstance(item, dict)
            ],
            sanity_checks=[],
            issues=issues,
            allocations=allocations,
        )

    def _build_version_read(
        self, session: Session, project: ProjectSeed, version: ForecastVersion
    ) -> ForecastVersionRead:
        version.outcome_type_snapshot = ProjectOutcomeType(self._resolve_bucket(project))
        version.probability_percent = _normalize_probability(
            version.outcome_type_snapshot.value,
            float(version.probability_percent),
        )
        validation_context = self._validation_context(project)
        discipline_codes_by_id = self._discipline_code_lookup(project)
        line_models = list(
            session.scalars(
                select(ForecastLine)
                .where(ForecastLine.forecast_version_id == version.id)
                .order_by(ForecastLine.sort_order)
            )
        )
        line_reads = [
            self._build_line_read(session, project, line, float(version.probability_percent))
            for line in line_models
        ]
        peer_codes = {
            line_read.id: discipline_codes_by_id.get(line_read.discipline_id or "")
            for line_read in line_reads
        }
        for line_read in line_reads:
            line_checks = collect_line_sanity_checks(
                context=validation_context,
                line=line_read,
                discipline_code=discipline_codes_by_id.get(line_read.discipline_id or ""),
                peer_lines=line_reads,
                peer_codes=peer_codes,
            )
            line_read.sanity_checks = line_checks
            line_read.issues.extend(_blocking_messages(line_checks))
        issues = [issue for line in line_reads for issue in line.issues]
        if version.source_quote_version_id is None:
            issues.append("Forecast version is not linked to a source quote version.")
        elif not self._version_source_is_current(project, version):
            issues.append(
                "Forecast source quote version is no longer current. "
                "Recalculate or create a new draft from the current quote."
            )

        discipline_rollups: dict[tuple[str | None, str], dict[str, float]] = {}
        project_rollups: dict[str, dict[str, float]] = {}
        for line in line_reads:
            for allocation in line.allocations:
                discipline_key = (line.discipline_id, allocation.month)
                if discipline_key not in discipline_rollups:
                    discipline_rollups[discipline_key] = {
                        "amount": 0,
                        "weighted_amount": 0,
                        "low_amount": 0,
                        "high_amount": 0,
                        "actual_amount": 0,
                    }
                discipline_rollups[discipline_key]["amount"] += allocation.amount
                discipline_rollups[discipline_key]["weighted_amount"] += allocation.weighted_amount
                discipline_rollups[discipline_key]["low_amount"] += (
                    allocation.low_amount or allocation.amount
                )
                discipline_rollups[discipline_key]["high_amount"] += (
                    allocation.high_amount or allocation.amount
                )
                discipline_rollups[discipline_key]["actual_amount"] += allocation.actual_amount or 0
                if allocation.month not in project_rollups:
                    project_rollups[allocation.month] = {
                        "amount": 0,
                        "weighted_amount": 0,
                        "low_amount": 0,
                        "high_amount": 0,
                        "actual_amount": 0,
                    }
                project_rollups[allocation.month]["amount"] += allocation.amount
                project_rollups[allocation.month]["weighted_amount"] += allocation.weighted_amount
                project_rollups[allocation.month]["low_amount"] += (
                    allocation.low_amount or allocation.amount
                )
                project_rollups[allocation.month]["high_amount"] += (
                    allocation.high_amount or allocation.amount
                )
                project_rollups[allocation.month]["actual_amount"] += allocation.actual_amount or 0

        discipline_monthly_rollups = [
            ForecastDisciplineMonthlyRollupRead(
                discipline_id=discipline_id,
                month=month,
                amount=round(values["amount"], 2),
                weighted_amount=round(values["weighted_amount"], 2),
                low_amount=round(values["low_amount"], 2),
                high_amount=round(values["high_amount"], 2),
                actual_amount=round(values["actual_amount"], 2),
            )
            for (discipline_id, month), values in sorted(
                discipline_rollups.items(),
                key=lambda item: ((item[0][0] or ""), item[0][1]),
            )
        ]
        project_monthly_rollups = [
            ForecastProjectMonthlyRollupRead(
                month=month,
                amount=round(values["amount"], 2),
                weighted_amount=round(values["weighted_amount"], 2),
                low_amount=round(values["low_amount"], 2),
                high_amount=round(values["high_amount"], 2),
                actual_amount=round(values["actual_amount"], 2),
            )
            for month, values in sorted(project_rollups.items(), key=lambda item: item[0])
        ]
        total_amount = round(sum(line.total_amount for line in line_reads), 2)
        weighted_total_amount = round(sum(line.weighted_total_amount for line in line_reads), 2)
        version_read = ForecastVersionRead(
            id=version.id,
            forecast_id=version.forecast_id,
            version_number=version.version_number,
            status=version.status.value,
            title=version.title,
            notes_text=version.notes_text,
            outcome_type_snapshot=version.outcome_type_snapshot.value,
            probability_percent=float(version.probability_percent),
            total_amount=total_amount,
            weighted_total_amount=weighted_total_amount,
            scenario_key=version.scenario_key,
            engine_source=version.engine_source,
            prediction_run_id=version.prediction_run_id,
            prediction_scenario_key=version.prediction_scenario_key,
            confidence_score=(
                float(version.confidence_score) if version.confidence_score is not None else None
            ),
            data_sufficiency_score=(
                float(version.data_sufficiency_score)
                if version.data_sufficiency_score is not None
                else None
            ),
            fallback_tier=version.fallback_tier,
            change_summary=version.change_summary_json,
            source_quote_version_id=version.source_quote_version_id,
            is_source_quote_current=self._version_source_is_current(project, version),
            revision_reason=version.revision_reason,
            parent_version_id=version.parent_version_id,
            created_at=version.created_at,
            updated_at=version.updated_at,
            explanation_summary=version.explanation_summary_json,
            sanity_checks=[],
            issues=issues,
            lines=line_reads,
            discipline_monthly_rollups=discipline_monthly_rollups,
            project_monthly_rollups=project_monthly_rollups,
        )
        version_checks = collect_version_sanity_checks(
            context=validation_context,
            version=version_read,
            prediction_scenario_output=self._load_prediction_scenario_output(session, version),
        )
        version_read.sanity_checks = version_checks
        version_read.issues.extend(_blocking_messages(version_checks))
        return version_read

    def _build_forecast_detail(
        self, session: Session, project: ProjectSeed, forecast: Forecast
    ) -> ForecastDetailRead:
        versions = list(
            session.scalars(
                select(ForecastVersion)
                .where(ForecastVersion.forecast_id == forecast.id)
                .order_by(ForecastVersion.version_number)
            )
        )
        version_reads = [
            self._build_version_read(session, project, version) for version in versions
        ]
        version_summaries = [
            ForecastVersionSummaryRead(
                id=version.id,
                forecast_id=version.forecast_id,
                version_number=version.version_number,
                status=version.status,
                title=version.title,
                outcome_type_snapshot=version.outcome_type_snapshot,
                probability_percent=version.probability_percent,
                total_amount=version.total_amount,
                weighted_total_amount=version.weighted_total_amount,
                scenario_key=version.scenario_key,
                engine_source=version.engine_source,
                prediction_run_id=version.prediction_run_id,
                prediction_scenario_key=version.prediction_scenario_key,
                confidence_score=version.confidence_score,
                data_sufficiency_score=version.data_sufficiency_score,
                fallback_tier=version.fallback_tier,
                change_summary=version.change_summary,
                source_quote_version_id=version.source_quote_version_id,
                is_source_quote_current=version.is_source_quote_current,
                created_at=version.created_at,
                updated_at=version.updated_at,
            )
            for version in version_reads
        ]
        current_version_read = next(
            (version for version in version_reads if version.id == forecast.current_version_id),
            None,
        )
        detail_checks = collect_detail_sanity_checks(version_reads)
        if current_version_read is not None and detail_checks:
            current_version_read.sanity_checks.extend(detail_checks)
        return ForecastDetailRead(
            forecast_id=forecast.id,
            project_id=project.id,
            current_version_id=forecast.current_version_id,
            versions=version_summaries,
            current_version=current_version_read,
            sanity_checks=detail_checks,
        )

    def _ensure_schedule_range(self, session: Session, schedule_range_id: str) -> None:
        if session.get(ProjectScheduleRange, schedule_range_id) is None:
            raise ApiProblemException(
                422,
                f"Schedule range '{schedule_range_id}' was not found.",
                "Invalid Schedule Range",
            )

    def _append_reason(
        self, existing: str | None, reason: str | None, *, prefix: str = "Manual override"
    ) -> str | None:
        if reason is None:
            return existing
        suffix = f"{prefix}: {reason}"
        if existing:
            return f"{existing}\n{suffix}"
        return suffix


forecast_service = ForecastService()
