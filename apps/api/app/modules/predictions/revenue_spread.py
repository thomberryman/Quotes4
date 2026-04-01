from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import ceil, floor
from typing import Any

from app.models import Forecast, ForecastLine, Project, ProjectBenchmarkDisciplineSummary, ProjectBenchmarkSummary, ProjectDiscipline, ProjectScheduleRange
from app.models.enums import ForecastVersionStatus
from app.modules.comparables.service import _float, _round
from app.modules.predictions.types import PredictionContext, PredictionModuleResult
from app.modules.predictions.utils import (
    confidence_label,
    diff_days_inclusive,
    first_day_next_month,
    from_cents,
    last_day_of_month,
    month_key,
    month_starts_between,
    normalize_share_bands,
    to_cents,
    weighted_band,
)


def _current_forecast_version(project: Project):
    if project.forecast is None:
        return None
    if project.forecast.current_version_id is not None:
        for version in project.forecast.versions:
            if version.id == project.forecast.current_version_id:
                return version
    eligible_versions = [
        version
        for version in project.forecast.versions
        if version.status in {ForecastVersionStatus.locked, ForecastVersionStatus.submitted}
    ]
    if eligible_versions:
        return max(eligible_versions, key=lambda item: (item.version_number, item.updated_at))
    if project.forecast.versions:
        return max(project.forecast.versions, key=lambda item: (item.version_number, item.updated_at))
    return None


def _forecast_monthly_amounts(project: Project) -> tuple[list[tuple[str, float]], str] | None:
    version = _current_forecast_version(project)
    if version is None:
        return None
    by_month_in_cents: dict[str, int] = {}
    for line in version.lines:
        for allocation in line.allocations:
            key = month_key(allocation.month)
            by_month_in_cents[key] = by_month_in_cents.get(key, 0) + to_cents(float(allocation.amount))
    if not by_month_in_cents:
        return None
    return ([(month, from_cents(amount)) for month, amount in sorted(by_month_in_cents.items())], "forecast_allocations")


def _sort_with_remainder(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(items, key=lambda item: (-float(item["remainder"]), str(item["sortKey"])))


def _schedule_monthly_allocations(start_date: date, end_date: date, amount_in_cents: int) -> list[tuple[str, int]]:
    total_days = diff_days_inclusive(start_date, end_date)
    current_start = start_date
    allocations: list[dict[str, object]] = []
    while current_start <= end_date:
        current_end = min(last_day_of_month(current_start), end_date)
        days_in_slice = diff_days_inclusive(current_start, current_end)
        raw_amount = (amount_in_cents * days_in_slice) / total_days
        floor_amount = int(raw_amount // 1)
        allocations.append(
            {
                "month": month_key(current_start),
                "floorAmount": floor_amount,
                "remainder": raw_amount - floor_amount,
                "sortKey": month_key(current_start),
            }
        )
        current_start = first_day_next_month(current_start)
    remainder = amount_in_cents - sum(int(item["floorAmount"]) for item in allocations)
    for item in _sort_with_remainder(allocations):
        if remainder <= 0:
            break
        item["floorAmount"] = int(item["floorAmount"]) + 1
        remainder -= 1
    return [(str(item["month"]), int(item["floorAmount"])) for item in sorted(allocations, key=lambda item: str(item["month"]))]


def _allocate_range_amounts(ranges: list[ProjectScheduleRange], total_amount: float) -> dict[str, int]:
    weights: list[dict[str, object]] = []
    for schedule_range in sorted(ranges, key=lambda item: (item.start_date, item.end_date, item.label)):
        duration_days = diff_days_inclusive(schedule_range.start_date, schedule_range.end_date)
        weights.append(
            {
                "id": schedule_range.id,
                "weight": float(schedule_range.allocation_percent) if schedule_range.allocation_percent is not None else float(duration_days),
                "remainder": 0.0,
                "sortKey": f"{schedule_range.start_date.isoformat()}:{schedule_range.label}",
            }
        )
    total_weight = sum(float(item["weight"]) for item in weights)
    if total_weight <= 0:
        return {}
    total_cents = to_cents(total_amount)
    distributed: list[dict[str, object]] = []
    for item in weights:
        raw_cents = total_cents * (float(item["weight"]) / total_weight)
        floor_cents = int(raw_cents // 1)
        distributed.append(
            {
                "id": item["id"],
                "floorCents": floor_cents,
                "remainder": raw_cents - floor_cents,
                "sortKey": item["sortKey"],
            }
        )
    remainder = total_cents - sum(int(item["floorCents"]) for item in distributed)
    for item in _sort_with_remainder(distributed):
        if remainder <= 0:
            break
        item["floorCents"] = int(item["floorCents"]) + 1
        remainder -= 1
    return {str(item["id"]): int(item["floorCents"]) for item in distributed}


def _schedule_monthly_amounts(project: Project) -> tuple[list[tuple[str, float]], str] | None:
    benchmark_summary = project.benchmark_summary
    if benchmark_summary is None or not project.schedule_ranges:
        return None
    range_amounts = _allocate_range_amounts(project.schedule_ranges, float(benchmark_summary.quoted_amount))
    if not range_amounts:
        return None
    by_month_in_cents: dict[str, int] = {}
    for schedule_range in project.schedule_ranges:
        allocated_cents = range_amounts.get(schedule_range.id)
        if allocated_cents is None or allocated_cents <= 0:
            continue
        for month, amount_in_cents in _schedule_monthly_allocations(
            schedule_range.start_date,
            schedule_range.end_date,
            allocated_cents,
        ):
            by_month_in_cents[month] = by_month_in_cents.get(month, 0) + amount_in_cents
    if not by_month_in_cents:
        return None
    return ([(month, from_cents(amount)) for month, amount in sorted(by_month_in_cents.items())], "schedule_ranges")


def _date_span_monthly_amounts(project: Project) -> tuple[list[tuple[str, float]], str] | None:
    benchmark_summary = project.benchmark_summary
    if benchmark_summary is None or project.start_date is None or project.end_date is None:
        return None
    allocations = _schedule_monthly_allocations(
        project.start_date,
        project.end_date,
        to_cents(float(benchmark_summary.quoted_amount)),
    )
    return ([(month, from_cents(amount)) for month, amount in allocations], "project_dates")


def _relative_duration_profile(project: Project):
    duration_weeks = (
        int(project.metadata_record.duration_weeks)
        if project.metadata_record is not None and project.metadata_record.duration_weeks is not None
        else None
    )
    benchmark_summary = project.benchmark_summary
    if benchmark_summary is None or duration_weeks is None or duration_weeks <= 0:
        return None
    month_count = max(1, ceil(duration_weeks / 4))
    share = _round(100 / month_count) / 100
    shares = [share for _ in range(month_count)]
    total_share = sum(shares)
    if total_share != 1:
        shares[-1] = _round(shares[-1] + (1 - total_share))
    return {"projectId": project.id, "shares": shares, "source": "duration_weeks"}


def _relative_monthly_profile(project: Project):
    monthly_amounts = _forecast_monthly_amounts(project)
    if monthly_amounts is None:
        monthly_amounts = _schedule_monthly_amounts(project)
    if monthly_amounts is None:
        monthly_amounts = _date_span_monthly_amounts(project)
    if monthly_amounts is not None:
        values, source = monthly_amounts
        total_amount = sum(amount for _, amount in values)
        if total_amount > 0:
            return {
                "projectId": project.id,
                "shares": [_round(amount / total_amount) for _, amount in values],
                "source": source,
            }
    return _relative_duration_profile(project)


def _target_months(project: Project, context: PredictionContext) -> tuple[list[str], str] | None:
    forecast_monthly_amounts = _forecast_monthly_amounts(project)
    if forecast_monthly_amounts is not None:
        return ([month for month, _ in forecast_monthly_amounts[0]], forecast_monthly_amounts[1])
    if project.schedule_ranges:
        start_date = min(item.start_date for item in project.schedule_ranges)
        end_date = max(item.end_date for item in project.schedule_ranges)
        return ([_month for _month in [month_key(month) for month in month_starts_between(start_date, end_date)]], "schedule_ranges")
    if project.start_date is not None and project.end_date is not None:
        return ([month_key(month) for month in month_starts_between(project.start_date, project.end_date)], "project_dates")
    if context.actuals.monthly_revenue:
        return (sorted(context.actuals.monthly_revenue), "in_flight_actuals")
    return None


def _interpolated_share(shares: list[float], position: float) -> float:
    if not shares:
        return 0.0
    if len(shares) == 1:
        return shares[0]
    scaled_position = position * (len(shares) - 1)
    lower_index = floor(scaled_position)
    upper_index = min(len(shares) - 1, ceil(scaled_position))
    if lower_index == upper_index:
        return shares[lower_index]
    lower_value = shares[lower_index]
    upper_value = shares[upper_index]
    fraction = scaled_position - lower_index
    return lower_value + (upper_value - lower_value) * fraction


def _profile_key(target_project: Project) -> str:
    metadata_record = target_project.metadata_record
    episode_count = int(metadata_record.episode_count) if metadata_record and metadata_record.episode_count else 0
    if metadata_record and metadata_record.metadata_json and metadata_record.metadata_json.get("milestones"):
        return "milestone"
    if episode_count > 1:
        return "episodic"
    if target_project.schedule_ranges:
        ordered = sorted(target_project.schedule_ranges, key=lambda item: item.start_date)
        if ordered and ordered[0].allocation_percent and float(ordered[0].allocation_percent) >= 55:
            return "front_loaded"
        if ordered and ordered[-1].allocation_percent and float(ordered[-1].allocation_percent) >= 55:
            return "back_loaded"
    return "even"


def build_revenue_spread(
    context: PredictionContext,
    *,
    quote_guidance: dict[str, Any] | None,
    fallback_tier: str,
    feature_snapshot: dict[str, Any],
) -> PredictionModuleResult:
    target_months = _target_months(context.project, context)
    if target_months is None:
        return PredictionModuleResult(
            module_key="revenue_spread",
            model_module="revenue_spread.build_revenue_spread",
            fallback_tier=fallback_tier,
            confidence_score=25.0,
            data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
            confidence_label="low",
            output={"items": [], "profileKey": None, "profileCount": 0, "warningSignals": [{"key": "missing_target_schedule_calendar", "severity": "info", "detail": "Target project is missing enough timing structure for monthly spread guidance."}]},
            explanations=[],
            warning_codes=["missing_target_schedule_calendar"],
        )

    month_labels, target_timeline_source = target_months
    profiles: list[dict[str, Any]] = []
    for item in context.eligible_items:
        project = context.projects_by_id.get(item["projectId"])
        if project is None:
            continue
        profile = _relative_monthly_profile(project)
        if profile is None:
            continue
        profiles.append(
            {
                "projectId": item["projectId"],
                "weight": item["similarityScore"],
                "shares": profile["shares"],
                "source": profile["source"],
            }
        )

    if len(profiles) < 3:
        return PredictionModuleResult(
            module_key="revenue_spread",
            model_module="revenue_spread.build_revenue_spread",
            fallback_tier=fallback_tier,
            confidence_score=38.0,
            data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
            confidence_label="low",
            output={"items": [], "profileKey": _profile_key(context.project), "profileCount": len(profiles), "warningSignals": [{"key": "insufficient_monthly_history", "severity": "info", "detail": "Fewer than three comparable projects had usable timing history."}]},
            explanations=[],
            warning_codes=["insufficient_monthly_history"],
        )

    profile_key = _profile_key(context.project)
    rows: list[dict[str, Any]] = []
    target_length = len(month_labels)
    total_amount = (
        float(quote_guidance["recommendedMedian"])
        if quote_guidance and quote_guidance.get("recommendedMedian") is not None
        else float(context.target_snapshot["targetAmount"])
        if context.target_snapshot.get("targetAmount") is not None
        else 0.0
    )
    current_actuals_total = context.actuals.current_revenue_total
    remaining_total = max(total_amount - current_actuals_total, 0.0)
    actual_months = sorted(context.actuals.monthly_revenue)

    for index, month in enumerate(month_labels):
        position = 0 if target_length == 1 else index / (target_length - 1)
        share_values = [
            {
                "projectId": profile["projectId"],
                "value": _interpolated_share(profile["shares"], position) * 100,
                "weight": profile["weight"],
            }
            for profile in profiles
        ]
        band = weighted_band(share_values)
        if band is None:
            continue
        row = {
            "month": month,
            "sampleSize": band["sampleSize"],
            "lowSharePct": band["low"],
            "medianSharePct": band["median"],
            "highSharePct": band["high"],
            "confidence": confidence_label(min(90.0, 45 + (len(profiles) * 8))),
            "fallbackTier": fallback_tier,
            "spreadProfile": profile_key,
            "comparableProjectIds": band["comparableProjectIds"],
            "reasoning": [
                "Monthly timing is aligned from comparable forecast or schedule curves.",
                f"Target month mapping is based on {target_timeline_source.replace('_', ' ')}.",
            ],
        }
        rows.append(row)

    rows = normalize_share_bands(rows)
    if current_actuals_total > 0:
        remaining_rows = [row for row in rows if row["month"] not in actual_months]
        remaining_share_total = sum(float(row["medianSharePct"]) for row in remaining_rows)
        for row in rows:
            if row["month"] in context.actuals.monthly_revenue:
                actual_amount = context.actuals.monthly_revenue[row["month"]]
                row["predictedAmountLow"] = _round(actual_amount)
                row["predictedAmountMedian"] = _round(actual_amount)
                row["predictedAmountHigh"] = _round(actual_amount)
                row["reasoning"].append("In-flight actual revenue overrides the predicted amount for this month.")
            else:
                normalized_share = (
                    float(row["medianSharePct"]) / remaining_share_total if remaining_share_total > 0 else 0
                )
                row["predictedAmountLow"] = _round(remaining_total * normalized_share * 0.9)
                row["predictedAmountMedian"] = _round(remaining_total * normalized_share)
                row["predictedAmountHigh"] = _round(remaining_total * normalized_share * 1.1)
                row["reasoning"].append("Remaining value is reforecast after blending actuals to date.")
    else:
        for row in rows:
            row["predictedAmountLow"] = _round(total_amount * float(row["lowSharePct"]) / 100)
            row["predictedAmountMedian"] = _round(total_amount * float(row["medianSharePct"]) / 100)
            row["predictedAmountHigh"] = _round(total_amount * float(row["highSharePct"]) / 100)

    confidence_score = min(95.0, round((len(profiles) * 10) + (12 if current_actuals_total > 0 else 0) + (float(feature_snapshot["dataSufficiencyScore"]) * 0.25), 2))
    return PredictionModuleResult(
        module_key="revenue_spread",
        model_module="revenue_spread.build_revenue_spread",
        fallback_tier=fallback_tier,
        confidence_score=confidence_score,
        data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
        confidence_label=confidence_label(confidence_score),
        output={"items": rows, "profileKey": profile_key, "profileCount": len(profiles), "warningSignals": []},
        explanations=[
            {
                "key": "spread_profile",
                "label": "Spread profile",
                "impact": profile_key,
                "detail": f"The target project currently behaves most like a {profile_key.replace('_', ' ')} revenue profile.",
            }
        ],
        warning_codes=[],
    )
