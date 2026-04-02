from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.datetimes import same_timestamp
from app.core.errors import ApiProblemException
from app.models import (
    Company,
    Discipline,
    Forecast,
    ForecastLine,
    ForecastPhasingChange,
    ForecastPhasingDraft,
    ForecastVersion,
    MappedActual,
    MonthlyForecastAllocation,
    PredictionRun,
    PredictionScenario,
    Project,
    ProjectBenchmarkDisciplineSummary,
    ProjectBenchmarkSummary,
    ProjectDiscipline,
    ProjectMetadata,
    ProjectOutcome,
    ProjectParty,
    ProjectScheduleRange,
    Quote,
    QuoteLineItem,
    QuoteSection,
    QuoteVersion,
    ReferenceDataValue,
    User,
)
from app.models.enums import (
    CetaRowFinancialType,
    ForecastAllocationMethod,
    ForecastVersionStatus,
    ProjectOutcomeType,
    RevenueAllocationMethod,
)
from app.modules.audit.service import audit_service
from app.modules.forecasts.engine import (
    DEFAULT_CURVE_PROFILES,
    DEFAULT_SEQUENCE_TEMPLATES,
    ForecastEngineLineInput,
    ForecastEngineManualAllocationInput,
    ForecastEngineProjectContext,
    ForecastEngineScheduleRange,
    build_line_plan,
    summarize_version_delta,
)
from app.modules.forecasts.schemas import (
    DashboardForecastAggregationsRead,
    DashboardForecastDatasetContractRead,
    DashboardForecastDatasetRead,
    DashboardForecastDisciplineTotalRead,
    DashboardForecastMonthRowRead,
    DashboardForecastMonthTotalRead,
    DashboardForecastProjectContractRead,
    DashboardForecastProjectRead,
    DashboardForecastStatusTotalRead,
    ForecastAccuracyDisciplineRead,
    ForecastAccuracyMetricsRead,
    ForecastAccuracyMonthRead,
    ForecastAccuracyProjectComparisonRead,
    ForecastAccuracyRecommendationRead,
    ForecastAccuracySummaryRead,
    ForecastAccuracyWeaknessRead,
    ForecastConfidenceCalibrationRead,
    ForecastCurveProfileOption,
    ForecastDashboardDisciplineRowRead,
    ForecastDashboardMonthValueRead,
    ForecastDashboardOverrideFlagsRead,
    ForecastDetailRead,
    ForecastDisciplineMonthlyRollupRead,
    ForecastExplanationRead,
    ForecastPhasingCellRead,
    ForecastPhasingCellWrite,
    ForecastPhasingChangeRead,
    ForecastPhasingDraftRead,
    ForecastPhasingDraftStateRead,
    ForecastPhasingDraftStateWrite,
    ForecastPhasingDraftUpsertRequest,
    ForecastPhasingFilterOption,
    ForecastPhasingFilterOptions,
    ForecastPhasingMonthTotalRead,
    ForecastPhasingPreviewRead,
    ForecastPhasingPreviewRequest,
    ForecastPhasingRowRead,
    ForecastPhasingRowUpdateRequest,
    ForecastPhasingStatusMonthTotalRead,
    ForecastPhasingWorkspaceRead,
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
DASHBOARD_BOOKED_STATUSES = {"awarded", "active", "complete"}


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


def _normalize_manual_override_cells(
    *,
    cells: list[ForecastPhasingCellWrite],
    expected_total_amount: float,
    existing_manual_cells: dict[str, ForecastPhasingCellWrite] | None = None,
    replace_existing_overrides: bool,
    allowed_months: set[str] | None = None,
    actual_months: set[str] | None = None,
    require_total_match: bool,
    invalid_months_message: str,
    actual_months_message: str,
    exceed_message: str,
    total_mismatch_message: str,
    title: str,
) -> list[ForecastPhasingCellWrite]:
    effective_cells_by_month: dict[str, ForecastPhasingCellWrite] = (
        {
            month: ForecastPhasingCellWrite(
                month=current_cell.month,
                amount=round(current_cell.amount, 2),
                is_locked=current_cell.is_locked,
                note=current_cell.note,
            )
            for month, current_cell in (existing_manual_cells or {}).items()
        }
        if not replace_existing_overrides
        else {}
    )
    normalized_allowed_months = allowed_months or set()
    normalized_actual_months = actual_months or set()
    seen_months: set[str] = set()
    invalid_months: list[str] = []
    duplicate_months: list[str] = []
    negative_months: list[str] = []

    for cell in sorted(cells, key=lambda item: item.month):
        try:
            _month_date(cell.month)
        except ValueError as exc:
            raise ApiProblemException(
                422,
                f"Manual allocation month '{cell.month}' is not valid.",
                title,
            ) from exc
        if cell.month in seen_months:
            duplicate_months.append(cell.month)
        seen_months.add(cell.month)
        if cell.amount < 0:
            negative_months.append(cell.month)
        if normalized_allowed_months and cell.month not in normalized_allowed_months:
            invalid_months.append(cell.month)
        if cell.month in normalized_actual_months:
            raise ApiProblemException(422, actual_months_message, title)
        if cell.amount <= 0.009 and not cell.is_locked:
            effective_cells_by_month.pop(cell.month, None)
            continue
        effective_cells_by_month[cell.month] = ForecastPhasingCellWrite(
            month=cell.month,
            amount=round(cell.amount, 2),
            is_locked=cell.is_locked,
            note=cell.note,
        )

    if duplicate_months:
        raise ApiProblemException(
            422,
            f"Duplicate manual allocation months are not allowed: {', '.join(sorted(set(duplicate_months)))}.",
            title,
        )
    if negative_months:
        raise ApiProblemException(
            422,
            f"Negative manual allocation values are not allowed: {', '.join(sorted(set(negative_months)))}.",
            title,
        )
    if invalid_months:
        raise ApiProblemException(
            422,
            invalid_months_message.format(months=", ".join(sorted(set(invalid_months)))),
            title,
        )

    effective_cells = [
        effective_cells_by_month[month] for month in sorted(effective_cells_by_month)
    ]
    manual_total = round(sum(cell.amount for cell in effective_cells), 2)
    if manual_total - expected_total_amount > 0.01:
        raise ApiProblemException(422, exceed_message, title)
    if require_total_match and abs(manual_total - expected_total_amount) > 0.01:
        raise ApiProblemException(
            422,
            total_mismatch_message.format(
                total=f"{manual_total:.2f}",
                expected=f"{expected_total_amount:.2f}",
            ),
            title,
        )
    return effective_cells


def _month_keys_between(from_month: str, to_month: str) -> list[str]:
    current = _month_date(from_month)
    end = _month_date(to_month)
    months: list[str] = []
    while current <= end:
        months.append(_month_key(current))
        current = _first_day_next_month(current)
    return months


def _aggregate_allocation_source(sources: set[str]) -> str | None:
    if not sources:
        return None
    if "actual" in sources:
        return "actual"
    if len(sources) == 1:
        return next(iter(sources))
    if "manual_override" in sources:
        return "mixed_override"
    return "mixed"


def _distribute_group_amounts(
    total_amount: float,
    weights: list[tuple[str, float]],
) -> dict[str, float]:
    if total_amount < 0:
        raise ApiProblemException(
            422,
            "Phasing cell values cannot be negative.",
            "Invalid Forecast Phasing",
        )
    positive_weights = [(key, value) for key, value in weights if value > 0]
    if not positive_weights:
        if not weights:
            return {}
        equal_share = round(total_amount / len(weights), 2)
        remainder = round(total_amount - (equal_share * len(weights)), 2)
        distributed = {key: equal_share for key, _value in weights}
        if remainder:
            first_key = weights[0][0]
            distributed[first_key] = round(distributed[first_key] + remainder, 2)
        return distributed

    total_amount_in_cents = _to_cents(total_amount)
    total_weight = sum(weight for _, weight in positive_weights)
    weighted: list[dict[str, object]] = []
    for key, weight in positive_weights:
        raw_amount = total_amount_in_cents * (weight / total_weight)
        floor_amount = int(raw_amount // 1)
        weighted.append(
            {
                "key": key,
                "floor_amount": floor_amount,
                "remainder": raw_amount - floor_amount,
                "sort_key": key,
            }
        )

    remainder = total_amount_in_cents - sum(int(item["floor_amount"]) for item in weighted)
    for item in _sort_with_remainder(weighted):
        if remainder <= 0:
            break
        item["floor_amount"] = int(item["floor_amount"]) + 1
        remainder -= 1

    distributed = {key: 0.0 for key, _weight in weights}
    for item in weighted:
        distributed[str(item["key"])] = _from_cents(int(item["floor_amount"]))
    return distributed


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
    estimated_execution_start_date: date | None
    estimated_execution_end_date: date | None
    revenue_allocation_method: str | None
    cadence_profile_type: str | None
    cadence_profile_data: dict[str, object] | None
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
    def resolve_execution_window(
        self,
        project: Project | ProjectSeed,
        *,
        month_values: list[str] | None = None,
    ) -> tuple[str | None, str | None]:
        estimated_start = getattr(project, "estimated_execution_start_date", None)
        estimated_end = getattr(project, "estimated_execution_end_date", None)
        schedule_ranges = list(getattr(project, "schedule_ranges", []) or [])
        fallback_start: date | None = None
        fallback_end: date | None = None
        if schedule_ranges:
            fallback_start = min(item.start_date for item in schedule_ranges)
            fallback_end = max(item.end_date for item in schedule_ranges)
        else:
            fallback_start = getattr(project, "start_date", None)
            fallback_end = getattr(project, "end_date", None)

        active_months = sorted(
            month for month in (month_values or []) if isinstance(month, str) and month
        )
        if fallback_start is None and active_months:
            fallback_start = _month_date(active_months[0])
        if fallback_end is None and active_months:
            fallback_end = _last_day_of_month(_month_date(active_months[-1]))

        resolved_start = estimated_start or fallback_start
        resolved_end = estimated_end or fallback_end
        return (
            resolved_start.isoformat() if resolved_start is not None else None,
            resolved_end.isoformat() if resolved_end is not None else None,
        )

    def resolve_base_phasing_profile(self, project: Project | ProjectSeed) -> str:
        return getattr(project, "cadence_profile_type", None) or "system_default"

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

    def get_phasing_workspace(
        self,
        session: Session,
        *,
        from_month: str | None,
        to_month: str | None,
        client_id: str | None,
        project_id: str | None,
        discipline_id: str | None,
        status: str | None,
        scenario_key: str | None,
        row_mode: str,
    ) -> ForecastPhasingWorkspaceRead:
        normalized_row_mode = self._normalize_phasing_row_mode(row_mode)
        normalized_scenario_key = scenario_key or "base"
        reference_month = _month_key(date.today())
        normalized_from_month = from_month or reference_month
        normalized_to_month = to_month
        if normalized_to_month is None:
            end_reference = _month_date(reference_month)
            for _ in range(17):
                end_reference = _first_day_next_month(end_reference)
            normalized_to_month = _month_key(end_reference)
        if _month_date(normalized_to_month) < _month_date(normalized_from_month):
            raise ApiProblemException(
                422,
                "Revenue phasing toMonth cannot be earlier than fromMonth.",
                "Invalid Revenue Phasing Range",
            )
        months = _month_keys_between(normalized_from_month, normalized_to_month)

        projects = list(
            session.scalars(
                select(Project).options(
                    selectinload(Project.parties).selectinload(ProjectParty.company),
                    selectinload(Project.disciplines).selectinload(ProjectDiscipline.discipline),
                    selectinload(Project.forecast)
                    .selectinload(Forecast.versions)
                    .selectinload(ForecastVersion.lines)
                    .selectinload(ForecastLine.allocations),
                )
            )
        )
        filter_options = self._build_phasing_filter_options(projects)
        rows: list[ForecastPhasingRowRead] = []
        status_month_totals: dict[tuple[str, str], dict[str, float]] = defaultdict(
            lambda: {"amount": 0.0, "weighted_amount": 0.0}
        )
        scoped_projects: list[tuple[Project, ForecastVersion, str | None, str | None]] = []

        for project_entity in projects:
            selected_version = self._select_workspace_version(
                project_entity,
                scenario_key=normalized_scenario_key,
            )
            if selected_version is None:
                continue

            resolved_client_id, resolved_client_name = self._resolve_project_client(project_entity)
            if client_id and resolved_client_id != client_id:
                continue
            if project_id and project_entity.id != project_id:
                continue
            if status and project_entity.status.value != status:
                continue
            scoped_projects.append(
                (
                    project_entity,
                    selected_version,
                    resolved_client_id,
                    resolved_client_name,
                )
            )

        draft_map = self._load_phasing_drafts(
            session,
            forecast_version_ids=[version.id for _, version, _, _ in scoped_projects],
        )

        for (
            project_entity,
            selected_version,
            resolved_client_id,
            resolved_client_name,
        ) in scoped_projects:
            discipline_name_by_id = {
                item.discipline_id: item.discipline.name
                for item in project_entity.disciplines
                if item.discipline_id is not None and item.discipline is not None
            }

            base_lines = list(selected_version.lines)
            if discipline_id is not None:
                base_lines = [
                    line for line in base_lines if (line.discipline_id or "unassigned") == discipline_id
                ]
            if not base_lines:
                continue

            project_months = self._aggregate_phasing_months(
                base_lines,
                probability_percent=float(selected_version.probability_percent),
                months=months,
                editable=selected_version.status == ForecastVersionStatus.draft,
            )
            for month, values in project_months.items():
                key = (project_entity.status.value, month)
                status_month_totals[key]["amount"] += values["amount"]
                status_month_totals[key]["weighted_amount"] += values["weighted_amount"]

            if normalized_row_mode == "project":
                rows.append(
                    self._build_phasing_row(
                        project_entity=project_entity,
                        selected_version=selected_version,
                        row_mode="project",
                        client_id=resolved_client_id,
                        client_name=resolved_client_name,
                        discipline_id=None,
                        discipline_name=None,
                        lines=base_lines,
                        months=months,
                        active_draft=draft_map.get(
                            (
                                selected_version.id,
                                self._make_phasing_row_key("project", project_entity.id, None),
                            )
                        ),
                    )
                )
                continue

            grouped_lines: dict[str | None, list[ForecastLine]] = defaultdict(list)
            for line in base_lines:
                grouped_lines[line.discipline_id].append(line)
            for grouped_discipline_id, grouped_items in sorted(
                grouped_lines.items(),
                key=lambda item: (
                    discipline_name_by_id.get(item[0] or "", "Unassigned"),
                    item[0] or "",
                ),
            ):
                rows.append(
                    self._build_phasing_row(
                        project_entity=project_entity,
                        selected_version=selected_version,
                        row_mode="discipline",
                        client_id=resolved_client_id,
                        client_name=resolved_client_name,
                        discipline_id=grouped_discipline_id,
                        discipline_name=discipline_name_by_id.get(grouped_discipline_id or "")
                        if grouped_discipline_id is not None
                        else "Unassigned",
                        lines=grouped_items,
                        months=months,
                        active_draft=draft_map.get(
                            (
                                selected_version.id,
                                self._make_phasing_row_key(
                                    "discipline",
                                    project_entity.id,
                                    grouped_discipline_id,
                                ),
                            )
                        ),
                    )
                )

        month_totals = self._build_workspace_month_totals(rows, months)
        recent_changes = self._load_recent_phasing_changes(
            session,
            project_ids=[row.project_id for row in rows],
        )
        return ForecastPhasingWorkspaceRead(
            generated_at=datetime.now(UTC),
            from_month=normalized_from_month,
            to_month=normalized_to_month,
            row_mode=normalized_row_mode,
            scenario_key=normalized_scenario_key,
            filter_options=filter_options,
            months=months,
            rows=sorted(
                rows,
                key=lambda item: (
                    item.client_name or "",
                    item.project_name,
                    item.discipline_name or "",
                ),
            ),
            month_totals=month_totals,
            status_month_totals=[
                ForecastPhasingStatusMonthTotalRead(
                    status=project_status,
                    month=month,
                    amount=round(values["amount"], 2),
                    weighted_amount=round(values["weighted_amount"], 2),
                )
                for (project_status, month), values in sorted(status_month_totals.items())
            ],
            recent_changes=recent_changes,
        )

    def get_dashboard_forecast_dataset(
        self,
        session: Session,
        *,
        from_month: str | None,
        to_month: str | None,
        client_id: str | None,
        project_id: str | None,
        discipline_id: str | None,
        status: str | None,
        scenario_key: str | None,
    ) -> DashboardForecastDatasetRead:
        normalized_scenario_key = scenario_key or "base"
        reference_month = _month_key(date.today())
        normalized_from_month = from_month or reference_month
        normalized_to_month = to_month or normalized_from_month
        self._assert_dashboard_forecast_month(normalized_from_month)
        self._assert_dashboard_forecast_month(normalized_to_month)
        if _month_date(normalized_to_month) < _month_date(normalized_from_month):
            raise ApiProblemException(
                422,
                "Dashboard forecast toMonth cannot be earlier than fromMonth.",
                "Invalid Dashboard Forecast Range",
            )

        months = _month_keys_between(normalized_from_month, normalized_to_month)
        month_set = set(months)
        projects = list(
            session.scalars(
                select(Project).options(
                    selectinload(Project.parties).selectinload(ProjectParty.company),
                    selectinload(Project.disciplines).selectinload(ProjectDiscipline.discipline),
                    selectinload(Project.quotes).selectinload(Quote.versions),
                    selectinload(Project.forecast).selectinload(Forecast.versions),
                )
            )
        )
        discipline_lookup = {
            discipline.id: (discipline.code, discipline.name)
            for discipline in session.scalars(select(Discipline))
        }
        discipline_code_lookup = {
            discipline_id: code for discipline_id, (code, _name) in discipline_lookup.items()
        }

        response_currency_code: str | None = None
        project_rows: dict[str, DashboardForecastProjectRead] = {}
        grouped_rows: dict[tuple[str, str, str | None, str, bool], float] = defaultdict(float)

        for project_entity in projects:
            resolved_client_id, resolved_client_name = self._resolve_project_client(project_entity)
            if client_id and resolved_client_id != client_id:
                continue
            if project_id and project_entity.id != project_id:
                continue
            if status and project_entity.status.value != status:
                continue
            if discipline_id and not any(
                item.discipline_id == discipline_id for item in project_entity.disciplines
            ):
                continue

            version_read = self._select_dashboard_source_version(
                session,
                project_entity,
                scenario_key=normalized_scenario_key,
            )
            if version_read is None:
                continue

            if version_read.total_amount <= 0.009:
                continue

            project_seed = self._get_project_seed(session, project_entity.id)
            mapped_status = self._map_dashboard_forecast_status(
                version_read.outcome_type_snapshot,
            )
            full_active_months = [
                item.month
                for item in version_read.project_monthly_rollups
                if item.amount > 0.009
            ]
            project_months = self._build_dashboard_project_months(
                version_read,
                project_status=project_entity.status.value,
                months=months,
            )
            discipline_rows = self._build_dashboard_discipline_rows(
                version_read,
                project_status=project_entity.status.value,
                months=months,
                discipline_lookup=discipline_lookup,
            )
            window_forecast_value = round(sum(item.amount for item in project_months), 2)
            window_weighted_forecast_value = round(
                sum(item.weighted_amount for item in project_months),
                2,
            )
            if window_forecast_value <= 0.009:
                continue
            override_flags = ForecastDashboardOverrideFlagsRead(
                has_manual_overrides=any(
                    allocation.is_manual_override
                    for line in version_read.lines
                    for allocation in line.allocations
                ),
                has_locked_months=any(
                    allocation.is_locked
                    for line in version_read.lines
                    for allocation in line.allocations
                ),
                has_actualized_months=any(
                    (allocation.actual_amount or 0.0) > 0.009
                    for line in version_read.lines
                    for allocation in line.allocations
                ),
            )
            manual_override_line_count = sum(
                1
                for line in version_read.lines
                if any(allocation.is_manual_override for allocation in line.allocations)
            )
            project_currency_code = self._dashboard_project_currency_code(
                project_entity,
                version_read,
            )
            if response_currency_code is None:
                response_currency_code = project_currency_code

            execution_start_date, execution_end_date = self.resolve_execution_window(
                project_entity,
                month_values=sorted(full_active_months),
            )
            project_rows[project_entity.id] = DashboardForecastProjectRead(
                project_id=project_entity.id,
                project_name=project_entity.name,
                client=resolved_client_name or "Unknown client",
                client_id=resolved_client_id,
                client_name=resolved_client_name or "Unknown client",
                status=mapped_status,
                operational_status=project_entity.status.value,
                quote_version_id=project_seed.current_quote_version_id,
                source_quote_version_id=version_read.source_quote_version_id,
                is_source_quote_current=version_read.is_source_quote_current,
                forecast_version_id=version_read.id,
                forecast_status=version_read.status,
                scenario_key=version_read.scenario_key,
                execution_start_date=execution_start_date,
                execution_end_date=execution_end_date,
                total_project_value=self._project_quote_total(project_seed),
                total_forecast_value=round(version_read.total_amount, 2),
                window_forecast_value=window_forecast_value,
                weighted_total_forecast_value=round(version_read.weighted_total_amount, 2),
                window_weighted_forecast_value=window_weighted_forecast_value,
                probability_percent=round(version_read.probability_percent, 2),
                allocation_method_used=(
                    self._summarize_dashboard_values(
                        {line.allocation_method for line in version_read.lines},
                        default="none",
                    )
                    or "none"
                ),
                allocation_profile_key=self._summarize_dashboard_values(
                    {line.allocation_profile_key for line in version_read.lines},
                    default=self.resolve_base_phasing_profile(project_entity),
                ),
                base_phasing_profile=self.resolve_base_phasing_profile(project_entity),
                manual_override_line_count=manual_override_line_count,
                override_flags=override_flags,
                confidence_score=version_read.confidence_score,
                data_sufficiency_score=version_read.data_sufficiency_score,
                fallback_tier=version_read.fallback_tier,
                change_summary=version_read.change_summary,
                explanation_summary=version_read.explanation_summary,
                issues=list(version_read.issues),
                project_months=project_months,
                discipline_rows=discipline_rows,
            )

            for line in version_read.lines:
                if line.allocation_method not in {"schedule", "manual"}:
                    raise ApiProblemException(
                        409,
                        (
                            f"Dashboard forecast row for project {project_entity.id} uses unknown "
                            f"allocation method '{line.allocation_method}'."
                        ),
                        "Invalid Dashboard Forecast Dataset",
                    )
                discipline_code = (
                    discipline_code_lookup.get(line.discipline_id)
                    if line.discipline_id is not None
                    else None
                )
                for allocation in line.allocations:
                    self._assert_dashboard_forecast_month(allocation.month)
                    if allocation.month not in month_set:
                        continue
                    if allocation.amount < -0.009:
                        raise ApiProblemException(
                            409,
                            (
                                f"Dashboard forecast row for project {project_entity.id} has a "
                                f"negative revenue value in {allocation.month}."
                            ),
                            "Invalid Dashboard Forecast Dataset",
                        )
                    revenue_value = round(float(allocation.amount), 2)
                    if revenue_value <= 0.009:
                        continue
                    grouped_rows[
                        (
                            project_entity.id,
                            allocation.month,
                            discipline_code,
                            line.allocation_method,
                            bool(allocation.is_manual_override),
                        )
                    ] = round(
                        grouped_rows[
                            (
                                project_entity.id,
                                allocation.month,
                                discipline_code,
                                line.allocation_method,
                                bool(allocation.is_manual_override),
                            )
                        ]
                        + revenue_value,
                        2,
                    )

        monthly_rows = [
            DashboardForecastMonthRowRead(
                project_id=project_key,
                month=month,
                discipline=discipline_code,
                allocation_method=allocation_method,
                override_flag=override_flag,
                revenue_value=round(revenue_value, 2),
            )
            for (
                project_key,
                month,
                discipline_code,
                allocation_method,
                override_flag,
            ), revenue_value in sorted(
                grouped_rows.items(),
                key=lambda item: (
                    item[0][0],
                    item[0][1],
                    item[0][2] or "",
                    item[0][3],
                    item[0][4],
                ),
            )
        ]

        totals_by_month: dict[str, float] = {month: 0.0 for month in months}
        totals_by_status: dict[str, float] = {
            "estimated": 0.0,
            "awarded": 0.0,
            "lost": 0.0,
        }
        totals_by_discipline: dict[str | None, float] = defaultdict(float)

        for row in monthly_rows:
            project_summary = project_rows.get(row.project_id)
            if project_summary is None:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast row for project {row.project_id} does not have a "
                        "matching project summary."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            totals_by_month[row.month] = round(
                totals_by_month.get(row.month, 0.0) + row.revenue_value,
                2,
            )
            totals_by_status[project_summary.status] = round(
                totals_by_status.get(project_summary.status, 0.0) + row.revenue_value,
                2,
            )
            totals_by_discipline[row.discipline] = round(
                totals_by_discipline.get(row.discipline, 0.0) + row.revenue_value,
                2,
            )

        dataset = DashboardForecastDatasetRead(
            generated_at=datetime.now(UTC),
            currency_code=response_currency_code or "GBP",
            from_month=normalized_from_month,
            to_month=normalized_to_month,
            scenario_key=normalized_scenario_key,
            projects=sorted(
                project_rows.values(),
                key=lambda item: (
                    item.client,
                    item.project_name,
                    item.project_id,
                ),
            ),
            monthly_rows=monthly_rows,
            aggregations=DashboardForecastAggregationsRead(
                totals_by_month=[
                    DashboardForecastMonthTotalRead(
                        month=month,
                        revenue_value=round(totals_by_month.get(month, 0.0), 2),
                    )
                    for month in months
                ],
                totals_by_status=[
                    DashboardForecastStatusTotalRead(
                        status=status_key,  # type: ignore[arg-type]
                        revenue_value=round(totals_by_status.get(status_key, 0.0), 2),
                    )
                    for status_key in ("estimated", "awarded", "lost")
                ],
                totals_by_discipline=[
                    DashboardForecastDisciplineTotalRead(
                        discipline=discipline_code,
                        revenue_value=round(revenue_value, 2),
                    )
                    for discipline_code, revenue_value in sorted(
                        totals_by_discipline.items(),
                        key=lambda item: (item[0] is None, item[0] or ""),
                    )
                ],
            ),
        )
        self._validate_dashboard_forecast_dataset(dataset)
        return dataset

    def to_dashboard_forecast_contract_dataset(
        self,
        dataset: DashboardForecastDatasetRead,
    ) -> DashboardForecastDatasetContractRead:
        contract = DashboardForecastDatasetContractRead(
            generated_at=dataset.generated_at,
            currency_code=dataset.currency_code,
            from_month=dataset.from_month,
            to_month=dataset.to_month,
            scenario_key=dataset.scenario_key,
            projects=[
                DashboardForecastProjectContractRead(
                    project_id=project.project_id,
                    project_name=project.project_name,
                    client=project.client,
                    status=project.status,
                    execution_start_date=project.execution_start_date,
                    execution_end_date=project.execution_end_date,
                    total_forecast_value=round(project.window_forecast_value, 2),
                )
                for project in dataset.projects
                if project.window_forecast_value > 0.009
            ],
            monthly_rows=dataset.monthly_rows,
            aggregations=dataset.aggregations,
        )
        self._validate_dashboard_forecast_contract_dataset(contract)
        return contract

    def preview_phasing_action(
        self,
        session: Session,
        payload: ForecastPhasingPreviewRequest,
    ) -> ForecastPhasingPreviewRead:
        workspace = self.get_phasing_workspace(
            session,
            from_month=payload.from_month,
            to_month=payload.to_month,
            client_id=None,
            project_id=payload.project_id,
            discipline_id=payload.discipline_id,
            status=None,
            scenario_key=None,
            row_mode=payload.row_mode,
        )
        target_row = next(
            (
                row
                for row in workspace.rows
                if row.project_id == payload.project_id
                and (
                    row.discipline_id == payload.discipline_id
                    if payload.row_mode == "discipline"
                    else row.discipline_id is None
                )
            ),
            None,
        )
        if target_row is None:
            raise ApiProblemException(
                404,
                "Revenue phasing row was not found.",
                "Revenue Phasing Row Not Found",
            )

        locked_months = set(payload.locked_months)
        locked_total = sum(
            cell.amount for cell in target_row.cells if cell.month in locked_months or cell.actual_amount
        )
        unlocked_cells = [
            cell
            for cell in target_row.cells
            if cell.month not in locked_months and (cell.actual_amount or 0.0) <= 0.009
        ]
        if not unlocked_cells:
            return ForecastPhasingPreviewRead(
                project_id=payload.project_id,
                row_mode=payload.row_mode,
                discipline_id=payload.discipline_id,
                action=payload.action,
                cells=[],
            )
        remaining_total = max(0.0, round(target_row.total_amount - locked_total, 2))
        preview_cells: list[ForecastPhasingCellWrite]
        if payload.action == "equal_split":
            amount_per_cell = round(remaining_total / len(unlocked_cells), 2)
            preview_cells = [
                ForecastPhasingCellWrite(
                    month=cell.month,
                    amount=amount_per_cell,
                    is_locked=cell.is_locked,
                    note=cell.manual_note,
                )
                for cell in unlocked_cells
            ]
            adjustment = round(
                remaining_total - sum(item.amount for item in preview_cells),
                2,
            )
            if preview_cells and adjustment:
                preview_cells[0].amount = round(preview_cells[0].amount + adjustment, 2)
        elif payload.action == "rebalance_remaining":
            existing_total = sum(cell.amount for cell in unlocked_cells)
            weights = [
                (cell.month, cell.amount if existing_total > 0 else 1.0) for cell in unlocked_cells
            ]
            distributed = _distribute_group_amounts(remaining_total, weights)
            preview_cells = [
                ForecastPhasingCellWrite(
                    month=cell.month,
                    amount=distributed.get(cell.month, 0.0),
                    is_locked=cell.is_locked,
                    note=cell.manual_note,
                )
                for cell in unlocked_cells
            ]
        elif payload.action == "cadence_profile":
            profile_key = payload.cadence_profile_type or target_row.cadence_profile_type or "flat_equal"
            profile_weights = self._preview_profile_weights(profile_key, unlocked_cells)
            distributed = _distribute_group_amounts(remaining_total, profile_weights)
            preview_cells = [
                ForecastPhasingCellWrite(
                    month=cell.month,
                    amount=distributed.get(cell.month, 0.0),
                    is_locked=cell.is_locked,
                    note=cell.manual_note,
                )
                for cell in unlocked_cells
            ]
        else:
            raise ApiProblemException(
                422,
                f"Unsupported phasing preview action '{payload.action}'.",
                "Invalid Revenue Phasing Action",
            )

        return ForecastPhasingPreviewRead(
            project_id=payload.project_id,
            row_mode=payload.row_mode,
            discipline_id=payload.discipline_id,
            action=payload.action,
            cells=preview_cells,
        )

    def _normalize_phasing_draft_state(
        self,
        *,
        editable_version: ForecastVersion,
        allowed_months: set[str],
        actual_months: set[str],
        group_total: float,
        state: ForecastPhasingDraftStateRead | ForecastPhasingDraftStateWrite,
    ) -> ForecastPhasingDraftStateRead:
        invalid_months = sorted(
            cell.month for cell in state.cells if allowed_months and cell.month not in allowed_months
        )
        if invalid_months:
            raise ApiProblemException(
                422,
                f"Phasing months are outside the current forecast window: {', '.join(invalid_months)}.",
                "Invalid Revenue Phasing Draft",
            )
        if any(cell.month in actual_months for cell in state.cells):
            raise ApiProblemException(
                422,
                "Actual months cannot be manually overridden from the phasing workspace.",
                "Invalid Revenue Phasing Draft",
            )

        normalized_cells_by_month: dict[str, ForecastPhasingCellWrite] = {}
        for cell in state.cells:
            amount = round(cell.amount, 2)
            if amount <= 0.009 and not cell.is_locked:
                normalized_cells_by_month.pop(cell.month, None)
                continue
            normalized_cells_by_month[cell.month] = ForecastPhasingCellWrite(
                month=cell.month,
                amount=amount,
                is_locked=cell.is_locked,
                note=cell.note,
            )

        manual_total = round(sum(cell.amount for cell in normalized_cells_by_month.values()), 2)
        if manual_total - group_total > 0.01:
            raise ApiProblemException(
                422,
                "Manual phasing exceeds the row total and cannot be saved.",
                "Invalid Revenue Phasing Draft",
            )

        return ForecastPhasingDraftStateRead(
            forecast_version_id=editable_version.id,
            expected_updated_at=editable_version.updated_at,
            reason=state.reason,
            cells=[
                normalized_cells_by_month[month] for month in sorted(normalized_cells_by_month)
            ],
        )

    def upsert_phasing_draft(
        self,
        session: Session,
        project_id: str,
        payload: ForecastPhasingDraftUpsertRequest,
        *,
        actor_id: str,
    ) -> ForecastPhasingDraftRead:
        normalized_row_mode = self._normalize_phasing_row_mode(payload.row_mode)
        normalized_save_mode = self._normalize_phasing_save_mode(payload.save_mode)
        forecast = self._get_or_create_forecast(session, project_id)
        source_version = (
            self._get_version_entity(session, payload.current_state.forecast_version_id)
            if payload.current_state.forecast_version_id is not None
            else (
                session.get(ForecastVersion, forecast.current_version_id)
                if forecast.current_version_id is not None
                else None
            )
        )
        if source_version is not None and not same_timestamp(
            source_version.updated_at,
            payload.current_state.expected_updated_at,
        ):
            raise ApiProblemException(
                409,
                "Forecast version has been updated by another request.",
                "Forecast Version Conflict",
            )

        editable_version = self._ensure_editable_phasing_version(
            session,
            project_id,
            source_version=source_version,
            actor_id=actor_id,
        )
        project = self._get_project_seed(session, project_id)
        target_lines = list(
            session.scalars(
                select(ForecastLine)
                .where(ForecastLine.forecast_version_id == editable_version.id)
                .order_by(ForecastLine.sort_order)
            )
        )
        if normalized_row_mode == "discipline":
            target_lines = [
                line for line in target_lines if line.discipline_id == payload.discipline_id
            ]
        if not target_lines:
            raise ApiProblemException(
                404,
                "Revenue phasing target lines were not found.",
                "Revenue Phasing Row Not Found",
            )

        existing_allocations = list(
            session.scalars(
                select(MonthlyForecastAllocation)
                .where(MonthlyForecastAllocation.forecast_line_id.in_([line.id for line in target_lines]))
                .order_by(MonthlyForecastAllocation.month)
            )
        )
        allowed_months = {_month_key(allocation.month) for allocation in existing_allocations}
        actual_months = {
            _month_key(allocation.month)
            for allocation in existing_allocations
            if allocation.actual_amount is not None and float(allocation.actual_amount) > 0.009
        }
        group_total = round(sum(float(line.total_amount) for line in target_lines), 2)
        current_state = self._normalize_phasing_draft_state(
            editable_version=editable_version,
            allowed_months=allowed_months,
            actual_months=actual_months,
            group_total=group_total,
            state=payload.current_state,
        )
        if len(payload.past_states) > 100 or len(payload.future_states) > 100:
            raise ApiProblemException(
                422,
                "Revenue phasing draft history is too large to persist.",
                "Invalid Revenue Phasing Draft",
            )
        past_states = [
            self._normalize_phasing_draft_state(
                editable_version=editable_version,
                allowed_months=allowed_months,
                actual_months=actual_months,
                group_total=group_total,
                state=state,
            )
            for state in payload.past_states
        ]
        future_states = [
            self._normalize_phasing_draft_state(
                editable_version=editable_version,
                allowed_months=allowed_months,
                actual_months=actual_months,
                group_total=group_total,
                state=state,
            )
            for state in payload.future_states
        ]

        row_key = self._make_phasing_row_key(
            normalized_row_mode,
            project_id,
            payload.discipline_id if normalized_row_mode == "discipline" else None,
        )
        existing_draft = session.scalar(
            select(ForecastPhasingDraft).where(
                ForecastPhasingDraft.forecast_version_id == editable_version.id,
                ForecastPhasingDraft.row_key == row_key,
            )
        )
        if existing_draft is not None:
            if payload.expected_draft_updated_at is None or not same_timestamp(
                existing_draft.updated_at,
                payload.expected_draft_updated_at,
            ):
                raise ApiProblemException(
                    409,
                    "Revenue phasing draft has been updated by another operator.",
                    "Revenue Phasing Draft Conflict",
                )
        elif payload.expected_draft_updated_at is not None:
            raise ApiProblemException(
                409,
                "Revenue phasing draft has been updated by another operator.",
                "Revenue Phasing Draft Conflict",
            )

        if existing_draft is None:
            draft_record = ForecastPhasingDraft(
                forecast_version_id=editable_version.id,
                project_id=project_id,
                discipline_id=payload.discipline_id if normalized_row_mode == "discipline" else None,
                row_mode=normalized_row_mode,
                row_key=row_key,
            )
            session.add(draft_record)
        else:
            draft_record = existing_draft

        draft_record.save_mode = normalized_save_mode
        draft_record.current_state_json = self._serialize_phasing_draft_state(current_state)
        draft_record.past_states_json = [
            self._serialize_phasing_draft_state(state) for state in past_states
        ]
        draft_record.future_states_json = [
            self._serialize_phasing_draft_state(state) for state in future_states
        ]
        draft_record.updated_by_id = actor_id
        session.flush()

        audit_service.record(
            session,
            action="forecast.phasing.draft.updated",
            entity_type="forecast_version",
            entity_id=editable_version.id,
            actor_id=actor_id,
            project_id=project_id,
            summary=f"Updated shared {normalized_row_mode} phasing draft for {project_id}.",
            metadata={
                "disciplineId": payload.discipline_id,
                "rowKey": row_key,
                "saveMode": normalized_save_mode,
                "cellCount": len(current_state.cells),
                "pastCount": len(past_states),
                "futureCount": len(future_states),
            },
        )

        actor_email = session.scalar(select(User.email).where(User.id == actor_id))
        return self._build_phasing_draft_read(
            draft_record,
            updated_by_email=actor_email,
        )

    def discard_phasing_draft(
        self,
        session: Session,
        project_id: str,
        *,
        forecast_version_id: str | None,
        row_mode: str,
        discipline_id: str | None,
        actor_id: str,
    ) -> ForecastPhasingWorkspaceRead:
        normalized_row_mode = self._normalize_phasing_row_mode(row_mode)
        forecast = self._get_or_create_forecast(session, project_id)
        source_version = (
            self._get_version_entity(session, forecast_version_id)
            if forecast_version_id is not None
            else (
                session.get(ForecastVersion, forecast.current_version_id)
                if forecast.current_version_id is not None
                else None
            )
        )
        editable_version = self._ensure_editable_phasing_version(
            session,
            project_id,
            source_version=source_version,
            actor_id=actor_id,
        )
        target_discipline_id = discipline_id if normalized_row_mode == "discipline" else None
        row_key = self._make_phasing_row_key(normalized_row_mode, project_id, target_discipline_id)
        draft_record = session.scalar(
            select(ForecastPhasingDraft).where(
                ForecastPhasingDraft.forecast_version_id == editable_version.id,
                ForecastPhasingDraft.row_key == row_key,
            )
        )
        if draft_record is not None:
            session.delete(draft_record)
            audit_service.record(
                session,
                action="forecast.phasing.draft.discarded",
                entity_type="forecast_version",
                entity_id=editable_version.id,
                actor_id=actor_id,
                project_id=project_id,
                summary=f"Discarded shared {normalized_row_mode} phasing draft for {project_id}.",
                metadata={
                    "disciplineId": target_discipline_id,
                    "rowKey": row_key,
                },
            )
            session.flush()

        return self.get_phasing_workspace(
            session,
            from_month=None,
            to_month=None,
            client_id=None,
            project_id=project_id,
            discipline_id=target_discipline_id,
            status=None,
            scenario_key=editable_version.scenario_key,
            row_mode=normalized_row_mode,
        )

    def update_phasing_row(
        self,
        session: Session,
        project_id: str,
        payload: ForecastPhasingRowUpdateRequest,
        *,
        actor_id: str,
    ) -> ForecastPhasingWorkspaceRead:
        normalized_row_mode = self._normalize_phasing_row_mode(payload.row_mode)
        row_key = self._make_phasing_row_key(
            normalized_row_mode,
            project_id,
            payload.discipline_id if normalized_row_mode == "discipline" else None,
        )
        forecast = self._get_or_create_forecast(session, project_id)
        source_version = (
            self._get_version_entity(session, payload.forecast_version_id)
            if payload.forecast_version_id is not None
            else (
                session.get(ForecastVersion, forecast.current_version_id)
                if forecast.current_version_id is not None
                else None
            )
        )
        if source_version is not None and not same_timestamp(
            source_version.updated_at,
            payload.expected_updated_at,
        ):
            raise ApiProblemException(
                409,
                "Forecast version has been updated by another request.",
                "Forecast Version Conflict",
            )

        editable_version = self._ensure_editable_phasing_version(
            session,
            project_id,
            source_version=source_version,
            actor_id=actor_id,
        )
        project = self._get_project_seed(session, project_id)
        target_lines = list(
            session.scalars(
                select(ForecastLine)
                .where(ForecastLine.forecast_version_id == editable_version.id)
                .order_by(ForecastLine.sort_order)
            )
        )
        if normalized_row_mode == "discipline":
            target_lines = [
                line for line in target_lines if line.discipline_id == payload.discipline_id
            ]
        if not target_lines:
            raise ApiProblemException(
                404,
                "Revenue phasing target lines were not found.",
                "Revenue Phasing Row Not Found",
            )

        existing_allocations = list(
            session.scalars(
                select(MonthlyForecastAllocation)
                .where(MonthlyForecastAllocation.forecast_line_id.in_([line.id for line in target_lines]))
                .order_by(MonthlyForecastAllocation.month)
            )
        )
        row_before = self._aggregate_phasing_months(
            target_lines,
            probability_percent=float(editable_version.probability_percent),
            months=sorted({_month_key(allocation.month) for allocation in existing_allocations}),
            editable=editable_version.status == ForecastVersionStatus.draft,
        )
        existing_manual_cells: dict[str, ForecastPhasingCellWrite] = {}
        for allocation in existing_allocations:
            if (
                not allocation.is_manual_override
                and allocation.allocation_source != "manual_override"
            ):
                continue
            month_key = _month_key(allocation.month)
            current_cell = existing_manual_cells.get(month_key)
            if current_cell is None:
                existing_manual_cells[month_key] = ForecastPhasingCellWrite(
                    month=month_key,
                    amount=round(float(allocation.amount), 2),
                    is_locked=bool(allocation.is_locked),
                    note=allocation.manual_note,
                )
                continue
            current_cell.amount = round(
                float(current_cell.amount) + float(allocation.amount),
                2,
            )
            current_cell.is_locked = current_cell.is_locked or bool(allocation.is_locked)
            if current_cell.note is None and allocation.manual_note:
                current_cell.note = allocation.manual_note

        group_total = round(sum(float(line.total_amount) for line in target_lines), 2)
        actual_months = {
            _month_key(allocation.month)
            for allocation in existing_allocations
            if allocation.actual_amount is not None and float(allocation.actual_amount) > 0.009
        }
        allowed_months = {
            _month_key(allocation.month)
            for allocation in existing_allocations
        }
        effective_cells = _normalize_manual_override_cells(
            cells=payload.cells,
            expected_total_amount=group_total,
            existing_manual_cells=existing_manual_cells,
            replace_existing_overrides=payload.replace_existing_overrides,
            allowed_months=allowed_months,
            actual_months=actual_months,
            require_total_match=False,
            invalid_months_message=(
                "Phasing months are outside the current forecast window: {months}."
            ),
            actual_months_message=(
                "Actual months cannot be manually overridden from the phasing workspace."
            ),
            exceed_message="Manual phasing exceeds the row total and cannot be saved.",
            total_mismatch_message=(
                "Manual phasing totals {total} but expected {expected}."
            ),
            title="Invalid Revenue Phasing",
        )
        effective_cells_by_month = {
            cell.month: cell for cell in effective_cells
        }

        line_weights = [
            (line.id, float(line.total_amount) if float(line.total_amount) > 0 else 1.0)
            for line in target_lines
        ]
        manual_allocations_override: dict[str, list[ForecastEngineManualAllocationInput]] = {
            line.id: [] for line in target_lines
        }
        for cell in effective_cells:
            distributed = _distribute_group_amounts(cell.amount, line_weights)
            for line in target_lines:
                amount = distributed.get(line.id, 0.0)
                if amount <= 0 and not cell.is_locked:
                    continue
                manual_allocations_override.setdefault(line.id, []).append(
                    ForecastEngineManualAllocationInput(
                        month=cell.month,
                        amount=amount,
                        is_locked=cell.is_locked,
                        note=cell.note or payload.reason,
                    )
                )
        actual_totals_by_line_id: dict[str, float] = defaultdict(float)
        for allocation in existing_allocations:
            if allocation.actual_amount is None or float(allocation.actual_amount) <= 0.009:
                continue
            actual_totals_by_line_id[allocation.forecast_line_id] += float(allocation.actual_amount)

        manual_totals_by_line_id = {
            line_id: round(sum(item.amount for item in allocations), 2)
            for line_id, allocations in manual_allocations_override.items()
        }
        for line in target_lines:
            actual_total = round(actual_totals_by_line_id.get(line.id, 0.0), 2)
            manual_total = manual_totals_by_line_id.get(line.id, 0.0)
            line_total = round(float(line.total_amount), 2)
            if actual_total <= 0.009 and abs(manual_total - line_total) <= 0.009:
                line.allocation_method = ForecastAllocationMethod.manual
            else:
                line.allocation_method = ForecastAllocationMethod.schedule

        self._apply_engine_to_version(
            session,
            project,
            editable_version,
            scenario_key=editable_version.scenario_key or "base",
            prediction_detail=self._load_prediction_detail(
                session,
                project,
                scenario_key=editable_version.scenario_key or "base",
            ),
            revision_reason=payload.reason,
            manual_allocations_by_line_override=manual_allocations_override,
        )
        session.flush()
        session.execute(
            delete(ForecastPhasingDraft).where(
                ForecastPhasingDraft.forecast_version_id == editable_version.id,
                ForecastPhasingDraft.row_key == row_key,
            )
        )
        session.flush()
        session.expire_all()

        updated_lines = list(
            session.scalars(
                select(ForecastLine)
                .where(ForecastLine.forecast_version_id == editable_version.id)
                .order_by(ForecastLine.sort_order)
            )
        )
        if normalized_row_mode == "discipline":
            updated_lines = [
                line for line in updated_lines if line.discipline_id == payload.discipline_id
            ]
        updated_allocations = list(
            session.scalars(
                select(MonthlyForecastAllocation)
                .where(MonthlyForecastAllocation.forecast_line_id.in_([line.id for line in updated_lines]))
                .order_by(MonthlyForecastAllocation.month)
            )
        )
        changed_months = sorted(
            {
                *row_before.keys(),
                *{_month_key(allocation.month) for allocation in updated_allocations},
            }
        )
        row_after = self._aggregate_phasing_months(
            updated_lines,
            probability_percent=float(editable_version.probability_percent),
            months=changed_months,
            editable=True,
        )
        for month in changed_months:
            before_values = row_before.get(month, {})
            after_values = row_after.get(month, {})
            before_amount = round(float(before_values.get("amount", 0.0)), 2)
            after_amount = round(float(after_values.get("amount", 0.0)), 2)
            before_locked = bool(before_values.get("is_locked", False))
            after_locked = bool(after_values.get("is_locked", False))
            if (
                abs(before_amount - after_amount) <= 0.009
                and before_locked == after_locked
            ):
                continue
            session.add(
                ForecastPhasingChange(
                    forecast_version_id=editable_version.id,
                    project_id=project_id,
                    discipline_id=payload.discipline_id,
                    row_mode=normalized_row_mode,
                    month=_month_date(month),
                    before_amount=before_amount,
                    after_amount=after_amount,
                    before_locked=before_locked,
                    after_locked=after_locked,
                    source_method=payload.source_method,
                    reason=payload.reason,
                    note=effective_cells_by_month.get(month).note
                    if month in effective_cells_by_month
                    else None,
                    actor_id=actor_id,
                    created_at=datetime.now(UTC),
                )
            )

        audit_service.record(
            session,
            action="forecast.phasing.updated",
            entity_type="forecast_version",
            entity_id=editable_version.id,
            actor_id=actor_id,
            project_id=project_id,
            summary=(
                f"Updated {normalized_row_mode} revenue phasing for {project_id}."
            ),
            metadata={
                "disciplineId": payload.discipline_id,
                "cellCount": len(payload.cells),
                "effectiveCellCount": len(effective_cells),
                "saveMode": (
                    "replace" if payload.replace_existing_overrides else "merge"
                ),
                "sourceMethod": payload.source_method,
                "replaceExistingOverrides": payload.replace_existing_overrides,
            },
        )
        return self.get_phasing_workspace(
            session,
            from_month=min(changed_months) if changed_months else None,
            to_month=max(changed_months) if changed_months else None,
            client_id=None,
            project_id=project_id,
            discipline_id=payload.discipline_id if normalized_row_mode == "discipline" else None,
            status=None,
            scenario_key=editable_version.scenario_key,
            row_mode=normalized_row_mode,
        )

    def _normalize_phasing_row_mode(self, row_mode: str) -> str:
        if row_mode not in {"project", "discipline"}:
            raise ApiProblemException(
                422,
                "Revenue phasing row mode must be project or discipline.",
                "Invalid Revenue Phasing Row Mode",
            )
        return row_mode

    def _normalize_phasing_save_mode(self, save_mode: str) -> str:
        if save_mode not in {"replace", "merge"}:
            raise ApiProblemException(
                422,
                "Revenue phasing save mode must be replace or merge.",
                "Invalid Revenue Phasing Save Mode",
            )
        return save_mode

    def _make_phasing_row_key(
        self,
        row_mode: str,
        project_id: str,
        discipline_id: str | None,
    ) -> str:
        return f"{row_mode}:{project_id}:{discipline_id or 'all'}"

    def _serialize_phasing_draft_state(
        self,
        state: ForecastPhasingDraftStateRead | ForecastPhasingDraftStateWrite,
    ) -> dict[str, object]:
        return {
            "forecastVersionId": state.forecast_version_id,
            "expectedUpdatedAt": state.expected_updated_at.isoformat(),
            "reason": state.reason,
            "cells": [
                {
                    "month": cell.month,
                    "amount": round(cell.amount, 2),
                    "isLocked": cell.is_locked,
                    "note": cell.note,
                }
                for cell in state.cells
            ],
        }

    def _deserialize_phasing_draft_state(
        self,
        payload: dict[str, object] | None,
    ) -> ForecastPhasingDraftStateRead:
        if not payload:
            raise ApiProblemException(
                500,
                "Revenue phasing draft state was missing.",
                "Revenue Phasing Draft Corrupt",
            )
        return ForecastPhasingDraftStateRead.model_validate(payload)

    def _select_workspace_version(
        self,
        project: Project,
        *,
        scenario_key: str,
    ) -> ForecastVersion | None:
        if project.forecast is None or not project.forecast.versions:
            return None
        versions = sorted(
            project.forecast.versions,
            key=lambda item: (item.version_number, item.updated_at),
            reverse=True,
        )
        matching_draft = next(
            (
                version
                for version in versions
                if version.status == ForecastVersionStatus.draft
                and version.scenario_key == scenario_key
            ),
            None,
        )
        if matching_draft is not None:
            return matching_draft
        current_version = next(
            (
                version
                for version in versions
                if version.id == project.forecast.current_version_id
                and (version.scenario_key == scenario_key or scenario_key == "base")
            ),
            None,
        )
        if current_version is not None:
            return current_version
        return next((version for version in versions if version.scenario_key == scenario_key), None)

    def _assert_dashboard_forecast_month(self, month: str) -> None:
        if len(month) != 7 or month[4] != "-":
            raise ApiProblemException(
                422,
                f"Dashboard forecast month '{month}' is not in YYYY-MM format.",
                "Invalid Dashboard Forecast Month",
            )
        try:
            _month_date(month)
        except ValueError as exc:
            raise ApiProblemException(
                422,
                f"Dashboard forecast month '{month}' is not valid.",
                "Invalid Dashboard Forecast Month",
            ) from exc

    def _map_dashboard_forecast_status(
        self,
        outcome_type_snapshot: str,
    ) -> str:
        status_map = {
            "bid": "estimated",
            "awarded": "awarded",
            "lost": "lost",
        }
        mapped_status = status_map.get(outcome_type_snapshot)
        if mapped_status is None:
            raise ApiProblemException(
                409,
                (
                    "Dashboard forecast dataset encountered an unknown mapped status "
                    f"'{outcome_type_snapshot}'."
                ),
                "Invalid Dashboard Forecast Dataset",
            )
        return mapped_status

    def _dashboard_project_currency_code(
        self,
        project: Project,
        version_read: ForecastVersionRead,
    ) -> str:
        line_currency_codes = sorted(
            {
                line.currency_code
                for line in version_read.lines
                if line.currency_code
            }
        )
        if line_currency_codes:
            return line_currency_codes[0]
        return project.quote_currency_code or "GBP"

    def _summarize_dashboard_values(
        self,
        values: set[str | None],
        *,
        default: str | None,
    ) -> str | None:
        normalized = {value for value in values if value}
        if not normalized:
            return default
        if len(normalized) == 1:
            return next(iter(normalized))
        return "mixed"

    def _project_quote_total(self, project: ProjectSeed) -> float:
        return round(
            sum(_from_cents(line.amount_in_cents) for line in project.quote_lines),
            2,
        )

    def _build_dashboard_project_months(
        self,
        version_read: ForecastVersionRead,
        *,
        project_status: str,
        months: list[str],
    ) -> list[ForecastDashboardMonthValueRead]:
        month_set = set(months)
        return [
            ForecastDashboardMonthValueRead(
                month=item.month,
                amount=round(item.amount, 2),
                weighted_amount=round(item.weighted_amount, 2),
                actual_amount=round(item.actual_amount or 0.0, 2),
                booked_amount=(
                    round(item.amount, 2)
                    if project_status in DASHBOARD_BOOKED_STATUSES
                    else 0.0
                ),
            )
            for item in version_read.project_monthly_rollups
            if item.month in month_set
        ]

    def _build_dashboard_discipline_rows(
        self,
        version_read: ForecastVersionRead,
        *,
        project_status: str,
        months: list[str],
        discipline_lookup: dict[str, tuple[str, str]],
    ) -> list[ForecastDashboardDisciplineRowRead]:
        month_set = set(months)
        grouped: dict[str, dict[str, object]] = {}

        for line in version_read.lines:
            discipline_key = line.discipline_id or "unassigned"
            _discipline_code, discipline_name = discipline_lookup.get(
                line.discipline_id or "",
                ("unassigned", "Unassigned"),
            )
            bucket = grouped.setdefault(
                discipline_key,
                {
                    "discipline_name": discipline_name,
                    "allocation_methods": set(),
                    "allocation_profiles": set(),
                    "line_count": 0,
                    "manual_override_line_count": 0,
                    "total_amount": 0.0,
                    "weighted_total_amount": 0.0,
                    "month_values": [],
                },
            )
            allocation_methods = bucket["allocation_methods"]
            if isinstance(allocation_methods, set):
                allocation_methods.add(line.allocation_method)
            allocation_profiles = bucket["allocation_profiles"]
            if isinstance(allocation_profiles, set):
                allocation_profiles.add(line.allocation_profile_key)
            bucket["line_count"] = int(bucket["line_count"]) + 1
            if any(allocation.is_manual_override for allocation in line.allocations):
                bucket["manual_override_line_count"] = (
                    int(bucket["manual_override_line_count"]) + 1
                )
            bucket["total_amount"] = float(bucket["total_amount"]) + line.total_amount
            bucket["weighted_total_amount"] = (
                float(bucket["weighted_total_amount"]) + line.weighted_total_amount
            )

        for rollup in version_read.discipline_monthly_rollups:
            if rollup.month not in month_set:
                continue
            discipline_key = rollup.discipline_id or "unassigned"
            _discipline_code, discipline_name = discipline_lookup.get(
                rollup.discipline_id or "",
                ("unassigned", "Unassigned"),
            )
            bucket = grouped.setdefault(
                discipline_key,
                {
                    "discipline_name": discipline_name,
                    "allocation_methods": set(),
                    "allocation_profiles": set(),
                    "line_count": 0,
                    "manual_override_line_count": 0,
                    "total_amount": 0.0,
                    "weighted_total_amount": 0.0,
                    "month_values": [],
                },
            )
            month_values = bucket["month_values"]
            if isinstance(month_values, list):
                month_values.append(
                    ForecastDashboardMonthValueRead(
                        month=rollup.month,
                        amount=round(rollup.amount, 2),
                        weighted_amount=round(rollup.weighted_amount, 2),
                        actual_amount=round(rollup.actual_amount or 0.0, 2),
                        booked_amount=(
                            round(rollup.amount, 2)
                            if project_status in DASHBOARD_BOOKED_STATUSES
                            else 0.0
                        ),
                    )
                )

        rows: list[ForecastDashboardDisciplineRowRead] = []
        for discipline_id, values in sorted(
            grouped.items(),
            key=lambda item: (
                -float(item[1]["total_amount"]),
                str(item[1]["discipline_name"]),
            ),
        ):
            allocation_methods = values["allocation_methods"]
            allocation_profiles = values["allocation_profiles"]
            month_values = values["month_values"]
            rows.append(
                ForecastDashboardDisciplineRowRead(
                    discipline_id=discipline_id,
                    discipline_name=str(values["discipline_name"]),
                    allocation_method_used=self._summarize_dashboard_values(
                        allocation_methods if isinstance(allocation_methods, set) else set(),
                        default="none",
                    )
                    or "none",
                    allocation_profile_key=self._summarize_dashboard_values(
                        allocation_profiles if isinstance(allocation_profiles, set) else set(),
                        default=None,
                    ),
                    line_count=int(values["line_count"]),
                    manual_override_line_count=int(values["manual_override_line_count"]),
                    total_amount=round(float(values["total_amount"]), 2),
                    weighted_total_amount=round(float(values["weighted_total_amount"]), 2),
                    month_values=sorted(
                        month_values if isinstance(month_values, list) else [],
                        key=lambda item: item.month,
                    ),
                )
            )
        return rows

    def _dashboard_source_version_candidates(
        self,
        project: Project,
        *,
        scenario_key: str,
    ) -> list[ForecastVersion]:
        if project.forecast is None or not project.forecast.versions:
            return []
        versions = sorted(
            project.forecast.versions,
            key=lambda item: (item.version_number, item.updated_at),
            reverse=True,
        )
        candidates: list[ForecastVersion] = []
        seen_version_ids: set[str] = set()

        def append_candidate(version: ForecastVersion | None) -> None:
            if version is None or version.id in seen_version_ids:
                return
            seen_version_ids.add(version.id)
            candidates.append(version)

        for version in versions:
            if version.status == ForecastVersionStatus.draft and version.scenario_key == scenario_key:
                append_candidate(version)

        current_version = next(
            (
                version
                for version in versions
                if version.id == project.forecast.current_version_id
                and version.scenario_key == scenario_key
            ),
            None,
        )
        append_candidate(current_version)

        for version in versions:
            if version.scenario_key == scenario_key:
                append_candidate(version)

        return candidates

    def _version_has_blocking_dashboard_sanity_checks(
        self,
        version_read: ForecastVersionRead,
    ) -> bool:
        if any(check.blocking for check in version_read.sanity_checks):
            return True
        return any(
            check.blocking
            for line in version_read.lines
            for check in line.sanity_checks
        )

    def _select_dashboard_source_version(
        self,
        session: Session,
        project: Project,
        *,
        scenario_key: str,
    ) -> ForecastVersionRead | None:
        candidates = self._dashboard_source_version_candidates(
            project,
            scenario_key=scenario_key,
        )
        if not candidates:
            return None

        project_seed = self._get_project_seed(session, project.id)
        invalid_candidate_found = False
        for candidate in candidates:
            version_read = self._build_version_read(session, project_seed, candidate)
            if not self._version_has_blocking_dashboard_sanity_checks(version_read):
                return version_read
            invalid_candidate_found = True

        if invalid_candidate_found:
            return None
        return None

    def _validate_dashboard_forecast_dataset(
        self,
        dataset: DashboardForecastDatasetRead,
    ) -> None:
        if len(dataset.currency_code) != 3:
            raise ApiProblemException(
                409,
                "Dashboard forecast dataset currency code must be a three-letter ISO code.",
                "Invalid Dashboard Forecast Dataset",
            )

        expected_months = _month_keys_between(dataset.from_month, dataset.to_month)
        declared_months = [item.month for item in dataset.aggregations.totals_by_month]
        if declared_months != expected_months:
            raise ApiProblemException(
                409,
                "Dashboard forecast month totals must include every month in the requested window.",
                "Invalid Dashboard Forecast Dataset",
            )

        project_ids: set[str] = set()
        projects_by_id: dict[str, DashboardForecastProjectRead] = {}
        for project in dataset.projects:
            if project.project_id in project_ids:
                raise ApiProblemException(
                    409,
                    f"Dashboard forecast dataset contains duplicate project '{project.project_id}'.",
                    "Invalid Dashboard Forecast Dataset",
                )
            if project.total_forecast_value <= 0.009:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast dataset project '{project.project_id}' must not "
                        "have a zero total."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            declared_project_months: set[str] = set()
            project_month_total = 0.0
            project_month_weighted_total = 0.0
            for month_value in project.project_months:
                self._assert_dashboard_forecast_month(month_value.month)
                if month_value.month not in expected_months:
                    raise ApiProblemException(
                        409,
                        (
                            f"Dashboard forecast project month '{month_value.month}' for "
                            f"project '{project.project_id}' falls outside the requested window."
                        ),
                        "Invalid Dashboard Forecast Dataset",
                    )
                if month_value.month in declared_project_months:
                    raise ApiProblemException(
                        409,
                        (
                            "Dashboard forecast project months must be unique per project and "
                            f"month for '{project.project_id}'."
                        ),
                        "Invalid Dashboard Forecast Dataset",
                    )
                declared_project_months.add(month_value.month)
                project_month_total = round(project_month_total + month_value.amount, 2)
                project_month_weighted_total = round(
                    project_month_weighted_total + month_value.weighted_amount,
                    2,
                )
            if abs(project_month_total - project.window_forecast_value) > 0.01:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast project window total for '{project.project_id}' "
                        "does not reconcile to the project month values."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            if abs(project_month_weighted_total - project.window_weighted_forecast_value) > 0.01:
                raise ApiProblemException(
                    409,
                    (
                        "Dashboard forecast project weighted window total for "
                        f"'{project.project_id}' does not reconcile to the project month values."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )

            declared_discipline_ids: set[str] = set()
            discipline_window_total = 0.0
            discipline_total = 0.0
            discipline_weighted_total = 0.0
            for discipline_row in project.discipline_rows:
                if discipline_row.discipline_id in declared_discipline_ids:
                    raise ApiProblemException(
                        409,
                        (
                            "Dashboard forecast discipline rows must be unique per project and "
                            f"discipline for '{project.project_id}'."
                        ),
                        "Invalid Dashboard Forecast Dataset",
                    )
                declared_discipline_ids.add(discipline_row.discipline_id)
                discipline_total = round(discipline_total + discipline_row.total_amount, 2)
                discipline_weighted_total = round(
                    discipline_weighted_total + discipline_row.weighted_total_amount,
                    2,
                )

                declared_discipline_months: set[str] = set()
                discipline_month_total = 0.0
                for month_value in discipline_row.month_values:
                    self._assert_dashboard_forecast_month(month_value.month)
                    if month_value.month not in expected_months:
                        raise ApiProblemException(
                            409,
                            (
                                f"Dashboard forecast discipline month '{month_value.month}' for "
                                f"project '{project.project_id}' falls outside the requested window."
                            ),
                            "Invalid Dashboard Forecast Dataset",
                        )
                    if month_value.month in declared_discipline_months:
                        raise ApiProblemException(
                            409,
                            (
                                "Dashboard forecast discipline month values must be unique per "
                                f"project, discipline, and month for '{project.project_id}'."
                            ),
                            "Invalid Dashboard Forecast Dataset",
                        )
                    declared_discipline_months.add(month_value.month)
                    discipline_month_total = round(
                        discipline_month_total + month_value.amount,
                        2,
                    )
                discipline_window_total = round(
                    discipline_window_total + discipline_month_total,
                    2,
                )

            if project.discipline_rows and abs(discipline_window_total - project.window_forecast_value) > 0.01:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast discipline window totals for '{project.project_id}' "
                        "do not reconcile to the project window total."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            if project.discipline_rows and abs(discipline_total - project.total_forecast_value) > 0.01:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast discipline totals for '{project.project_id}' do "
                        "not reconcile to the project forecast total."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            if project.discipline_rows and abs(
                discipline_weighted_total - project.weighted_total_forecast_value
            ) > 0.01:
                raise ApiProblemException(
                    409,
                    (
                        "Dashboard forecast discipline weighted totals for "
                        f"'{project.project_id}' do not reconcile to the project forecast total."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            project_ids.add(project.project_id)
            projects_by_id[project.project_id] = project

        row_keys: set[tuple[str, str, str | None, str, bool]] = set()
        totals_by_project_window: dict[str, float] = defaultdict(float)
        totals_by_month: dict[str, float] = {month: 0.0 for month in expected_months}
        totals_by_status: dict[str, float] = {
            "estimated": 0.0,
            "awarded": 0.0,
            "lost": 0.0,
        }
        totals_by_discipline: dict[str | None, float] = defaultdict(float)

        for row in dataset.monthly_rows:
            self._assert_dashboard_forecast_month(row.month)
            if row.month not in totals_by_month:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast row for month '{row.month}' falls outside the "
                        "requested window."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            if row.revenue_value < -0.009:
                raise ApiProblemException(
                    409,
                    "Dashboard forecast row revenue values cannot be negative.",
                    "Invalid Dashboard Forecast Dataset",
                )
            if row.allocation_method not in {"schedule", "manual"}:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast row uses unknown allocation method "
                        f"'{row.allocation_method}'."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            if row.project_id not in projects_by_id:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast row references unknown project '{row.project_id}'."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )

            row_key = (
                row.project_id,
                row.month,
                row.discipline,
                row.allocation_method,
                row.override_flag,
            )
            if row_key in row_keys:
                raise ApiProblemException(
                    409,
                    "Dashboard forecast monthly rows must be unique by project, month, discipline, method, and override flag.",
                    "Invalid Dashboard Forecast Dataset",
                )
            row_keys.add(row_key)

            totals_by_project_window[row.project_id] = round(
                totals_by_project_window.get(row.project_id, 0.0) + row.revenue_value,
                2,
            )
            totals_by_month[row.month] = round(
                totals_by_month.get(row.month, 0.0) + row.revenue_value,
                2,
            )
            totals_by_status[projects_by_id[row.project_id].status] = round(
                totals_by_status.get(projects_by_id[row.project_id].status, 0.0)
                + row.revenue_value,
                2,
            )
            totals_by_discipline[row.discipline] = round(
                totals_by_discipline.get(row.discipline, 0.0) + row.revenue_value,
                2,
            )

        for project_id, project in projects_by_id.items():
            if abs(
                totals_by_project_window.get(project_id, 0.0) - project.window_forecast_value
            ) > 0.01:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast project window total for '{project_id}' does not "
                        "reconcile to the monthly rows."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )

        declared_statuses: set[str] = set()
        declared_status_totals: dict[str, float] = {}
        for total in dataset.aggregations.totals_by_status:
            if total.status in declared_statuses:
                raise ApiProblemException(
                    409,
                    "Dashboard forecast status totals must be unique per status.",
                    "Invalid Dashboard Forecast Dataset",
                )
            declared_statuses.add(total.status)
            declared_status_totals[total.status] = total.revenue_value
        if declared_statuses != {"estimated", "awarded", "lost"}:
            raise ApiProblemException(
                409,
                "Dashboard forecast status totals must include estimated, awarded, and lost.",
                "Invalid Dashboard Forecast Dataset",
            )

        declared_month_totals: dict[str, float] = {}
        for total in dataset.aggregations.totals_by_month:
            if total.month in declared_month_totals:
                raise ApiProblemException(
                    409,
                    "Dashboard forecast month totals must be unique per month.",
                    "Invalid Dashboard Forecast Dataset",
                )
            declared_month_totals[total.month] = total.revenue_value

        declared_discipline_totals: dict[str | None, float] = {}
        seen_disciplines: set[str | None] = set()
        for total in dataset.aggregations.totals_by_discipline:
            if total.discipline in seen_disciplines:
                raise ApiProblemException(
                    409,
                    "Dashboard forecast discipline totals must be unique per discipline.",
                    "Invalid Dashboard Forecast Dataset",
                )
            seen_disciplines.add(total.discipline)
            declared_discipline_totals[total.discipline] = total.revenue_value

        for month in expected_months:
            if abs(declared_month_totals.get(month, 0.0) - totals_by_month.get(month, 0.0)) > 0.01:
                raise ApiProblemException(
                    409,
                    f"Dashboard forecast month total for '{month}' does not reconcile.",
                    "Invalid Dashboard Forecast Dataset",
                )

        for status_key in ("estimated", "awarded", "lost"):
            if abs(
                declared_status_totals.get(status_key, 0.0) - totals_by_status.get(status_key, 0.0)
            ) > 0.01:
                raise ApiProblemException(
                    409,
                    f"Dashboard forecast status total for '{status_key}' does not reconcile.",
                    "Invalid Dashboard Forecast Dataset",
                )

        if set(declared_discipline_totals) != set(totals_by_discipline):
            raise ApiProblemException(
                409,
                "Dashboard forecast discipline totals do not match the monthly-row disciplines.",
                "Invalid Dashboard Forecast Dataset",
            )
        for discipline_code, computed_total in totals_by_discipline.items():
            if abs(declared_discipline_totals.get(discipline_code, 0.0) - computed_total) > 0.01:
                raise ApiProblemException(
                    409,
                    (
                        "Dashboard forecast discipline total does not reconcile for "
                        f"'{discipline_code or 'unassigned'}'."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )

        raw_total = round(sum(row.revenue_value for row in dataset.monthly_rows), 2)
        project_total = round(sum(project.window_forecast_value for project in dataset.projects), 2)
        month_total = round(sum(item.revenue_value for item in dataset.aggregations.totals_by_month), 2)
        status_total = round(sum(item.revenue_value for item in dataset.aggregations.totals_by_status), 2)
        discipline_total = round(
            sum(item.revenue_value for item in dataset.aggregations.totals_by_discipline),
            2,
        )
        if (
            abs(raw_total - project_total) > 0.01
            or abs(raw_total - month_total) > 0.01
            or abs(raw_total - status_total) > 0.01
            or abs(raw_total - discipline_total) > 0.01
        ):
            raise ApiProblemException(
                409,
                "Dashboard forecast grand totals do not reconcile across the contract.",
                "Invalid Dashboard Forecast Dataset",
            )

    def _validate_dashboard_forecast_contract_dataset(
        self,
        dataset: DashboardForecastDatasetContractRead,
    ) -> None:
        if len(dataset.currency_code) != 3:
            raise ApiProblemException(
                409,
                "Dashboard forecast dataset currency code must be a three-letter ISO code.",
                "Invalid Dashboard Forecast Dataset",
            )

        expected_months = _month_keys_between(dataset.from_month, dataset.to_month)
        declared_months = [item.month for item in dataset.aggregations.totals_by_month]
        if declared_months != expected_months:
            raise ApiProblemException(
                409,
                "Dashboard forecast month totals must include every month in the requested window.",
                "Invalid Dashboard Forecast Dataset",
            )

        project_ids: set[str] = set()
        projects_by_id: dict[str, DashboardForecastProjectContractRead] = {}
        for project in dataset.projects:
            if project.project_id in project_ids:
                raise ApiProblemException(
                    409,
                    f"Dashboard forecast dataset contains duplicate project '{project.project_id}'.",
                    "Invalid Dashboard Forecast Dataset",
                )
            if project.total_forecast_value <= 0.009:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast dataset project '{project.project_id}' must not "
                        "have a zero total."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            project_ids.add(project.project_id)
            projects_by_id[project.project_id] = project

        row_keys: set[tuple[str, str, str | None, str, bool]] = set()
        totals_by_project: dict[str, float] = defaultdict(float)
        totals_by_month: dict[str, float] = {month: 0.0 for month in expected_months}
        totals_by_status: dict[str, float] = {
            "estimated": 0.0,
            "awarded": 0.0,
            "lost": 0.0,
        }
        totals_by_discipline: dict[str | None, float] = defaultdict(float)

        for row in dataset.monthly_rows:
            self._assert_dashboard_forecast_month(row.month)
            if row.month not in totals_by_month:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast row for month '{row.month}' falls outside the "
                        "requested window."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            if row.revenue_value < -0.009:
                raise ApiProblemException(
                    409,
                    "Dashboard forecast row revenue values cannot be negative.",
                    "Invalid Dashboard Forecast Dataset",
                )
            if row.allocation_method not in {"schedule", "manual"}:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast row uses unknown allocation method "
                        f"'{row.allocation_method}'."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )
            if row.project_id not in projects_by_id:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast row references unknown project '{row.project_id}'."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )

            row_key = (
                row.project_id,
                row.month,
                row.discipline,
                row.allocation_method,
                row.override_flag,
            )
            if row_key in row_keys:
                raise ApiProblemException(
                    409,
                    "Dashboard forecast monthly rows must be unique by project, month, discipline, method, and override flag.",
                    "Invalid Dashboard Forecast Dataset",
                )
            row_keys.add(row_key)

            totals_by_project[row.project_id] = round(
                totals_by_project.get(row.project_id, 0.0) + row.revenue_value,
                2,
            )
            totals_by_month[row.month] = round(
                totals_by_month.get(row.month, 0.0) + row.revenue_value,
                2,
            )
            totals_by_status[projects_by_id[row.project_id].status] = round(
                totals_by_status.get(projects_by_id[row.project_id].status, 0.0)
                + row.revenue_value,
                2,
            )
            totals_by_discipline[row.discipline] = round(
                totals_by_discipline.get(row.discipline, 0.0) + row.revenue_value,
                2,
            )

        for project_id, project in projects_by_id.items():
            if abs(totals_by_project.get(project_id, 0.0) - project.total_forecast_value) > 0.01:
                raise ApiProblemException(
                    409,
                    (
                        f"Dashboard forecast project total for '{project_id}' does not "
                        "reconcile to the monthly rows."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )

        declared_statuses: set[str] = set()
        declared_status_totals: dict[str, float] = {}
        for total in dataset.aggregations.totals_by_status:
            if total.status in declared_statuses:
                raise ApiProblemException(
                    409,
                    "Dashboard forecast status totals must be unique per status.",
                    "Invalid Dashboard Forecast Dataset",
                )
            declared_statuses.add(total.status)
            declared_status_totals[total.status] = total.revenue_value
        if declared_statuses != {"estimated", "awarded", "lost"}:
            raise ApiProblemException(
                409,
                "Dashboard forecast status totals must include estimated, awarded, and lost.",
                "Invalid Dashboard Forecast Dataset",
            )

        declared_month_totals: dict[str, float] = {}
        for total in dataset.aggregations.totals_by_month:
            if total.month in declared_month_totals:
                raise ApiProblemException(
                    409,
                    "Dashboard forecast month totals must be unique per month.",
                    "Invalid Dashboard Forecast Dataset",
                )
            declared_month_totals[total.month] = total.revenue_value

        declared_discipline_totals: dict[str | None, float] = {}
        seen_disciplines: set[str | None] = set()
        for total in dataset.aggregations.totals_by_discipline:
            if total.discipline in seen_disciplines:
                raise ApiProblemException(
                    409,
                    "Dashboard forecast discipline totals must be unique per discipline.",
                    "Invalid Dashboard Forecast Dataset",
                )
            seen_disciplines.add(total.discipline)
            declared_discipline_totals[total.discipline] = total.revenue_value

        for month in expected_months:
            if abs(declared_month_totals.get(month, 0.0) - totals_by_month.get(month, 0.0)) > 0.01:
                raise ApiProblemException(
                    409,
                    f"Dashboard forecast month total for '{month}' does not reconcile.",
                    "Invalid Dashboard Forecast Dataset",
                )

        for status_key in ("estimated", "awarded", "lost"):
            if abs(
                declared_status_totals.get(status_key, 0.0) - totals_by_status.get(status_key, 0.0)
            ) > 0.01:
                raise ApiProblemException(
                    409,
                    f"Dashboard forecast status total for '{status_key}' does not reconcile.",
                    "Invalid Dashboard Forecast Dataset",
                )

        if set(declared_discipline_totals) != set(totals_by_discipline):
            raise ApiProblemException(
                409,
                "Dashboard forecast discipline totals do not match the monthly-row disciplines.",
                "Invalid Dashboard Forecast Dataset",
            )
        for discipline_code, computed_total in totals_by_discipline.items():
            if abs(declared_discipline_totals.get(discipline_code, 0.0) - computed_total) > 0.01:
                raise ApiProblemException(
                    409,
                    (
                        "Dashboard forecast discipline total does not reconcile for "
                        f"'{discipline_code or 'unassigned'}'."
                    ),
                    "Invalid Dashboard Forecast Dataset",
                )

        raw_total = round(sum(row.revenue_value for row in dataset.monthly_rows), 2)
        project_total = round(sum(project.total_forecast_value for project in dataset.projects), 2)
        month_total = round(sum(item.revenue_value for item in dataset.aggregations.totals_by_month), 2)
        status_total = round(sum(item.revenue_value for item in dataset.aggregations.totals_by_status), 2)
        discipline_total = round(
            sum(item.revenue_value for item in dataset.aggregations.totals_by_discipline),
            2,
        )
        if (
            abs(raw_total - project_total) > 0.01
            or abs(raw_total - month_total) > 0.01
            or abs(raw_total - status_total) > 0.01
            or abs(raw_total - discipline_total) > 0.01
        ):
            raise ApiProblemException(
                409,
                "Dashboard forecast grand totals do not reconcile across the contract.",
                "Invalid Dashboard Forecast Dataset",
            )

    def _resolve_project_client(self, project: Project) -> tuple[str | None, str | None]:
        primary_client = next(
            (
                party
                for party in project.parties
                if party.role.value == "client"
                and party.is_primary
                and party.company is not None
            ),
            None,
        )
        if primary_client is not None and primary_client.company is not None:
            return primary_client.company.id, primary_client.company.name
        fallback_client = next(
            (
                party
                for party in project.parties
                if party.role.value == "client" and party.company is not None
            ),
            None,
        )
        if fallback_client is not None and fallback_client.company is not None:
            return fallback_client.company.id, fallback_client.company.name
        return None, None

    def _aggregate_phasing_months(
        self,
        lines: list[ForecastLine],
        *,
        probability_percent: float,
        months: list[str],
        editable: bool,
    ) -> dict[str, dict[str, object]]:
        month_set = set(months)
        aggregated: dict[str, dict[str, object]] = {
            month: {
                "amount": 0.0,
                "weighted_amount": 0.0,
                "actual_amount": 0.0,
                "low_amount": 0.0,
                "high_amount": 0.0,
                "sources": set(),
                "is_manual_override": False,
                "is_locked": False,
                "editable": editable,
                "manual_notes": set(),
            }
            for month in months
        }
        for line in lines:
            for allocation in line.allocations:
                month = _month_key(allocation.month)
                if month not in month_set:
                    continue
                values = aggregated[month]
                amount = float(allocation.amount)
                weighted_amount = round(amount * (probability_percent / 100), 2)
                values["amount"] = round(float(values["amount"]) + amount, 2)
                values["weighted_amount"] = round(
                    float(values["weighted_amount"]) + weighted_amount,
                    2,
                )
                values["actual_amount"] = round(
                    float(values["actual_amount"]) + float(allocation.actual_amount or 0.0),
                    2,
                )
                values["low_amount"] = round(
                    float(values["low_amount"])
                    + float(allocation.low_amount if allocation.low_amount is not None else amount),
                    2,
                )
                values["high_amount"] = round(
                    float(values["high_amount"])
                    + float(
                        allocation.high_amount if allocation.high_amount is not None else amount
                    ),
                    2,
                )
                if allocation.allocation_source:
                    cast_sources = values["sources"]
                    if isinstance(cast_sources, set):
                        cast_sources.add(allocation.allocation_source)
                values["is_manual_override"] = bool(values["is_manual_override"]) or bool(
                    allocation.is_manual_override
                )
                values["is_locked"] = bool(values["is_locked"]) or bool(allocation.is_locked)
                values["editable"] = bool(values["editable"]) and not (
                    allocation.actual_amount is not None and float(allocation.actual_amount) > 0.009
                )
                if allocation.manual_note:
                    cast_notes = values["manual_notes"]
                    if isinstance(cast_notes, set):
                        cast_notes.add(allocation.manual_note)
        return aggregated

    def _build_workspace_month_totals(
        self,
        rows: list[ForecastPhasingRowRead],
        months: list[str],
    ) -> list[ForecastPhasingMonthTotalRead]:
        totals: dict[str, dict[str, float]] = {
            month: {"amount": 0.0, "weighted_amount": 0.0} for month in months
        }
        for row in rows:
            for cell in row.cells:
                totals[cell.month]["amount"] += cell.amount
                totals[cell.month]["weighted_amount"] += cell.weighted_amount
        return [
            ForecastPhasingMonthTotalRead(
                month=month,
                amount=round(values["amount"], 2),
                weighted_amount=round(values["weighted_amount"], 2),
            )
            for month, values in totals.items()
        ]

    def _build_phasing_row(
        self,
        *,
        project_entity: Project,
        selected_version: ForecastVersion,
        row_mode: str,
        client_id: str | None,
        client_name: str | None,
        discipline_id: str | None,
        discipline_name: str | None,
        lines: list[ForecastLine],
        months: list[str],
        active_draft: ForecastPhasingDraftRead | None,
    ) -> ForecastPhasingRowRead:
        probability_percent = float(selected_version.probability_percent)
        aggregated_months = self._aggregate_phasing_months(
            lines,
            probability_percent=probability_percent,
            months=months,
            editable=selected_version.status == ForecastVersionStatus.draft,
        )
        cells = [
            ForecastPhasingCellRead(
                month=month,
                amount=round(float(values["amount"]), 2),
                weighted_amount=round(float(values["weighted_amount"]), 2),
                actual_amount=round(float(values["actual_amount"]), 2)
                if float(values["actual_amount"]) > 0.0
                else None,
                low_amount=round(float(values["low_amount"]), 2)
                if float(values["amount"]) > 0.0
                else None,
                high_amount=round(float(values["high_amount"]), 2)
                if float(values["amount"]) > 0.0
                else None,
                allocation_source=_aggregate_allocation_source(values["sources"])
                if isinstance(values["sources"], set)
                else None,
                is_manual_override=bool(values["is_manual_override"]),
                is_locked=bool(values["is_locked"]),
                editable=bool(values["editable"]),
                manual_note=(
                    "; ".join(sorted(values["manual_notes"]))
                    if isinstance(values["manual_notes"], set) and values["manual_notes"]
                    else None
                ),
            )
            for month, values in aggregated_months.items()
        ]
        total_amount = round(sum(cell.amount for cell in cells), 2)
        weighted_total_amount = round(sum(cell.weighted_amount for cell in cells), 2)
        row_key = self._make_phasing_row_key(row_mode, project_entity.id, discipline_id)
        execution_start_date, execution_end_date = self.resolve_execution_window(
            project_entity,
            month_values=[cell.month for cell in cells if cell.amount > 0.009],
        )
        return ForecastPhasingRowRead(
            row_key=row_key,
            row_mode=row_mode,
            project_id=project_entity.id,
            project_name=project_entity.name,
            client_id=client_id,
            client_name=client_name,
            status=project_entity.status.value,
            discipline_id=discipline_id,
            discipline_name=discipline_name,
            forecast_version_id=selected_version.id,
            forecast_version_status=selected_version.status.value,
            forecast_version_updated_at=selected_version.updated_at,
            scenario_key=selected_version.scenario_key,
            currency_code=lines[0].currency_code if lines else project_entity.quote_currency_code or "GBP",
            base_phasing_profile=self.resolve_base_phasing_profile(project_entity),
            execution_start_date=execution_start_date,
            execution_end_date=execution_end_date,
            total_amount=total_amount,
            weighted_total_amount=weighted_total_amount,
            can_edit=selected_version.status == ForecastVersionStatus.draft,
            cells=cells,
            active_draft=active_draft,
        )

    def _build_phasing_filter_options(
        self,
        projects: list[Project],
    ) -> ForecastPhasingFilterOptions:
        clients = sorted(
            {
                client
                for client in (self._resolve_project_client(project) for project in projects)
                if client[0] and client[1]
            },
            key=lambda item: item[1] or "",
        )
        project_options = sorted(
            [(project.id, project.name) for project in projects],
            key=lambda item: item[1],
        )
        discipline_options = sorted(
            {
                (
                    project_discipline.discipline_id,
                    project_discipline.discipline.name,
                )
                for project in projects
                for project_discipline in project.disciplines
                if project_discipline.discipline_id is not None
                and project_discipline.discipline is not None
            },
            key=lambda item: item[1],
        )
        scenario_options = sorted(
            {
                version.scenario_key
                for project in projects
                if project.forecast is not None
                for version in project.forecast.versions
                if version.scenario_key
            }
            | {"base"}
        )
        return ForecastPhasingFilterOptions(
            clients=[
                ForecastPhasingFilterOption(id=client_key, label=client_label)
                for client_key, client_label in clients
            ],
            projects=[
                ForecastPhasingFilterOption(id=project_key, label=project_label)
                for project_key, project_label in project_options
            ],
            disciplines=[
                ForecastPhasingFilterOption(id=discipline_key, label=discipline_label)
                for discipline_key, discipline_label in discipline_options
            ],
            statuses=[
                ForecastPhasingFilterOption(id=status_key, label=status_key.replace("_", " ").title())
                for status_key in ["bid", "awarded", "lost", "active", "complete", "archived"]
            ],
            scenarios=[
                ForecastPhasingFilterOption(id=scenario, label=scenario.replace("_", " ").title())
                for scenario in scenario_options
            ],
        )

    def _build_phasing_draft_read(
        self,
        draft: ForecastPhasingDraft,
        *,
        updated_by_email: str | None,
    ) -> ForecastPhasingDraftRead:
        return ForecastPhasingDraftRead(
            id=draft.id,
            forecast_version_id=draft.forecast_version_id,
            project_id=draft.project_id,
            row_mode=draft.row_mode,
            discipline_id=draft.discipline_id,
            save_mode=draft.save_mode,
            current_state=self._deserialize_phasing_draft_state(draft.current_state_json),
            past_states=[
                self._deserialize_phasing_draft_state(item) for item in draft.past_states_json or []
            ],
            future_states=[
                self._deserialize_phasing_draft_state(item)
                for item in draft.future_states_json or []
            ],
            updated_by_id=draft.updated_by_id,
            updated_by_email=updated_by_email,
            updated_at=draft.updated_at,
        )

    def _load_phasing_drafts(
        self,
        session: Session,
        *,
        forecast_version_ids: list[str],
    ) -> dict[tuple[str, str], ForecastPhasingDraftRead]:
        if not forecast_version_ids:
            return {}
        rows = session.execute(
            select(ForecastPhasingDraft, User.email)
            .outerjoin(User, User.id == ForecastPhasingDraft.updated_by_id)
            .where(ForecastPhasingDraft.forecast_version_id.in_(sorted(set(forecast_version_ids))))
            .order_by(desc(ForecastPhasingDraft.updated_at))
        ).all()
        return {
            (draft.forecast_version_id, draft.row_key): self._build_phasing_draft_read(
                draft,
                updated_by_email=updated_by_email,
            )
            for draft, updated_by_email in rows
        }

    def _load_recent_phasing_changes(
        self,
        session: Session,
        *,
        project_ids: list[str],
    ) -> list[ForecastPhasingChangeRead]:
        if not project_ids:
            return []
        rows = session.execute(
            select(ForecastPhasingChange, User.email)
            .outerjoin(User, User.id == ForecastPhasingChange.actor_id)
            .where(ForecastPhasingChange.project_id.in_(sorted(set(project_ids))))
            .order_by(desc(ForecastPhasingChange.created_at))
            .limit(20)
        ).all()
        return [
            ForecastPhasingChangeRead(
                id=change.id,
                project_id=change.project_id,
                forecast_version_id=change.forecast_version_id,
                row_mode=change.row_mode,
                month=_month_key(change.month),
                discipline_id=change.discipline_id,
                before_amount=float(change.before_amount),
                after_amount=float(change.after_amount),
                before_locked=change.before_locked,
                after_locked=change.after_locked,
                source_method=change.source_method,
                reason=change.reason,
                note=change.note,
                actor_id=change.actor_id,
                actor_email=actor_email,
                created_at=change.created_at,
            )
            for change, actor_email in rows
        ]

    def _preview_profile_weights(
        self,
        profile_key: str,
        cells: list[ForecastPhasingCellRead],
    ) -> list[tuple[str, float]]:
        month_count = max(len(cells), 1)
        weights: list[tuple[str, float]] = []
        for index, cell in enumerate(cells):
            position = 0.0 if month_count == 1 else index / (month_count - 1)
            if profile_key == "front_loaded":
                weight = 1.35 - (0.7 * position)
            elif profile_key == "back_loaded":
                weight = 0.65 + (0.9 * position)
            elif profile_key == "mid_loaded":
                weight = 0.7 + (1 - abs(position - 0.5) * 2)
            elif profile_key == "milestone_based":
                weight = 0.5 if position < 0.66 else 2.2
            elif profile_key == "episodic":
                weight = 1.0 + (0.65 if index % 2 == 0 else 0.0)
            elif profile_key == "discipline_sequenced":
                weight = 0.8 + (0.6 * position)
            else:
                weight = 1.0
            weights.append((cell.month, weight))
        return weights

    def _ensure_editable_phasing_version(
        self,
        session: Session,
        project_id: str,
        *,
        source_version: ForecastVersion | None,
        actor_id: str,
    ) -> ForecastVersion:
        forecast = self._get_or_create_forecast(session, project_id)
        if source_version is not None and source_version.status == ForecastVersionStatus.draft:
            return source_version
        existing_draft = self._find_draft(session, forecast.id)
        if existing_draft is not None:
            return existing_draft
        created_version = self.create_or_clone_version(
            session,
            project_id,
            ForecastVersionCreateRequest(
                base_version_id=source_version.id if source_version is not None else None,
                title=source_version.title if source_version is not None else "Forecast Draft",
                notes_text=source_version.notes_text if source_version is not None else None,
                probability_percent=(
                    float(source_version.probability_percent)
                    if source_version is not None
                    else None
                ),
                revision_reason="Created for revenue phasing update.",
            ),
            actor_id=actor_id,
        )
        return self._get_version_entity(session, created_version.id)

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
        existing_allocations = list(
            session.scalars(
                select(MonthlyForecastAllocation)
                .where(MonthlyForecastAllocation.forecast_line_id == line.id)
                .order_by(MonthlyForecastAllocation.month)
            )
        )
        manual_allocations_override: dict[str, list[ForecastEngineManualAllocationInput]] = {
            line.id: []
        }

        if payload.allocation_method == "manual":
            effective_cells = _normalize_manual_override_cells(
                cells=[
                    ForecastPhasingCellWrite(
                        month=allocation.month,
                        amount=round(allocation.amount, 2),
                        is_locked=True,
                        note=payload.reason,
                    )
                    for allocation in payload.allocations
                ],
                expected_total_amount=round(float(line.total_amount), 2),
                existing_manual_cells=None,
                replace_existing_overrides=True,
                allowed_months={
                    _month_key(allocation.month) for allocation in existing_allocations
                },
                actual_months={
                    _month_key(allocation.month)
                    for allocation in existing_allocations
                    if allocation.actual_amount is not None
                    and float(allocation.actual_amount) > 0.009
                },
                require_total_match=True,
                invalid_months_message=(
                    "Manual allocation months are outside the current forecast window: {months}."
                ),
                actual_months_message=(
                    "Actual months cannot be manually overridden for this forecast line."
                ),
                exceed_message="Manual allocations exceed the line total and cannot be saved.",
                total_mismatch_message=(
                    "Manual allocations total {total} but expected {expected}."
                ),
                title="Invalid Manual Allocations",
            )
            line.allocation_method = ForecastAllocationMethod.manual
            if "schedule_range_id" in payload.model_fields_set:
                line.schedule_range_id = payload.schedule_range_id
            manual_allocations_override[line.id] = [
                ForecastEngineManualAllocationInput(
                    month=cell.month,
                    amount=cell.amount,
                    is_locked=cell.is_locked,
                    note=cell.note or payload.reason,
                )
                for cell in effective_cells
            ]
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
            manual_allocations_by_line_override=manual_allocations_override,
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
            start_date=project.estimated_execution_start_date or project.start_date,
            end_date=project.estimated_execution_end_date or project.end_date,
            estimated_execution_start_date=project.estimated_execution_start_date,
            estimated_execution_end_date=project.estimated_execution_end_date,
            revenue_allocation_method=project.revenue_allocation_method.value
            if project.revenue_allocation_method is not None
            else RevenueAllocationMethod.cadence_profile.value,
            cadence_profile_type=project.cadence_profile_type,
            cadence_profile_data=project.cadence_profile_data_json,
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
        scenario_assumptions = (
            scenario.get("assumptionOverrides")
            if isinstance(scenario, dict) and isinstance(scenario.get("assumptionOverrides"), dict)
            else {}
        )

        return ForecastEngineProjectContext(
            project_id=project.id,
            project_format_key=project.project_format_key,
            metadata_json=project.metadata_json,
            episode_count=project.episode_count,
            duration_weeks=project.duration_weeks,
            start_date=project.start_date,
            end_date=project.end_date,
            revenue_allocation_method=project.revenue_allocation_method,
            cadence_profile_type=project.cadence_profile_type,
            cadence_profile_data=project.cadence_profile_data,
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
            scenario_assumptions=scenario_assumptions,
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
        manual_allocations_by_line_override: dict[
            str, list[ForecastEngineManualAllocationInput]
        ]
        | None = None,
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
        manual_allocations_by_line: dict[str, list[ForecastEngineManualAllocationInput]] = {}
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
                if not allocation.is_manual_override and allocation.allocation_source != "manual_override":
                    continue
                manual_allocations_by_line.setdefault(allocation.forecast_line_id, []).append(
                    ForecastEngineManualAllocationInput(
                        month=_month_key(allocation.month),
                        amount=float(allocation.amount),
                        is_locked=allocation.is_locked,
                        note=allocation.manual_note,
                    )
                )
            if manual_allocations_by_line_override is not None:
                manual_allocations_by_line.update(
                    {
                        line_id: list(items)
                        for line_id, items in manual_allocations_by_line_override.items()
                    }
                )
            session.execute(
                delete(MonthlyForecastAllocation).where(
                    MonthlyForecastAllocation.forecast_line_id.in_(line_ids)
                )
            )
            session.flush()
        elif manual_allocations_by_line_override is not None:
            manual_allocations_by_line.update(
                {
                    line_id: list(items)
                    for line_id, items in manual_allocations_by_line_override.items()
                }
            )

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
                    allocation_method=line.allocation_method.value,
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
                        is_manual_override=allocation_source == "manual_override",
                        is_locked=bool(source_context.get("lockedFlag"))
                        if allocation_source == "manual_override"
                        else False,
                        manual_note=(
                            str(source_context.get("note"))
                            if allocation_source == "manual_override"
                            and source_context.get("note")
                            else "Manual override"
                            if allocation_source == "manual_override"
                            else None
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
                        allocation_source="manual_override",
                        source_context_json={"reason": "manual_override", "lockedFlag": True},
                        is_manual_override=True,
                        is_locked=True,
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
                        low_amount=allocation.low_amount,
                        high_amount=allocation.high_amount,
                        actual_amount=allocation.actual_amount,
                        allocation_source=allocation.allocation_source,
                        source_context_json=allocation.source_context_json,
                        is_manual_override=allocation.is_manual_override,
                        is_locked=allocation.is_locked,
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
                    is_manual_override=source_row.is_manual_override if source_row else False,
                    is_locked=source_row.is_locked if source_row else False,
                    manual_note=source_row.manual_note if source_row else None,
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
