from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.modules.forecasts.schemas import (
    ForecastLineRead,
    ForecastSanityCheckRead,
    ForecastVersionRead,
)

DELIVERY_DISCIPLINE_CODES = {"delivery", "mastering"}
UPSTREAM_DELIVERY_CODES = {"online", "grade", "sound", "audio", "qc", "localisation"}
SHAPED_DISCIPLINE_CODES = {
    "dailies",
    "editorial",
    "offline",
    "vfx",
    "online",
    "grade",
    "sound",
    "audio",
    "delivery",
    "mastering",
}


@dataclass(frozen=True)
class ForecastValidationScheduleRange:
    id: str
    label: str
    start_date: date
    end_date: date
    discipline_id: str | None
    discipline_code: str | None
    allocation_percent: float | None


@dataclass(frozen=True)
class ForecastValidationQuoteLine:
    id: str
    label: str
    discipline_id: str | None
    discipline_code: str | None
    amount: float


@dataclass(frozen=True)
class ForecastValidationProjectContext:
    project_id: str
    project_name: str
    status: str
    start_date: date | None
    end_date: date | None
    project_format_key: str | None
    duration_weeks: int | None
    episode_count: int | None
    metadata_json: dict[str, object] | None
    current_quote_version_id: str | None
    schedule_ranges: list[ForecastValidationScheduleRange] = field(default_factory=list)
    quote_lines: list[ForecastValidationQuoteLine] = field(default_factory=list)
    actuals_by_discipline_month: dict[str, dict[str, float]] = field(default_factory=dict)
    actuals_by_project_month: dict[str, float] = field(default_factory=dict)


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _metadata_dict(context: ForecastValidationProjectContext) -> dict[str, object]:
    return context.metadata_json if isinstance(context.metadata_json, dict) else {}


def _positive_months(amounts: list[tuple[str, float]]) -> list[str]:
    return [month for month, amount in sorted(amounts) if amount > 0.009]


def _line_positive_months(line: ForecastLineRead) -> list[str]:
    return _positive_months(
        [(allocation.month, allocation.amount) for allocation in line.allocations]
    )


def _blocking_messages(checks: list[ForecastSanityCheckRead]) -> list[str]:
    return [f"{check.title}: {check.detail}" for check in checks if check.blocking]


def _check(
    *,
    key: str,
    severity: str,
    scope: str,
    title: str,
    detail: str,
    recommendation: str,
    line_id: str | None = None,
    month: str | None = None,
) -> ForecastSanityCheckRead:
    return ForecastSanityCheckRead(
        key=key,
        severity=severity,
        scope=scope,
        title=title,
        detail=detail,
        recommendation=recommendation,
        blocking=severity == "error",
        line_id=line_id,
        month=month,
    )


def metadata_completeness_score(context: ForecastValidationProjectContext) -> float:
    metadata = _metadata_dict(context)
    discipline_count = len(
        {
            line.discipline_id
            for line in context.quote_lines
            if line.discipline_id is not None
        }
        | {
            item.discipline_id
            for item in context.schedule_ranges
            if item.discipline_id is not None
        }
    )
    components = [
        context.project_format_key is not None,
        context.start_date is not None or bool(context.schedule_ranges),
        context.end_date is not None or bool(context.schedule_ranges),
        context.duration_weeks is not None,
        bool(context.quote_lines),
        discipline_count > 0,
        bool(metadata),
    ]
    return round((sum(1 for item in components if item) / len(components)) * 100, 2)


def _milestone_months(context: ForecastValidationProjectContext) -> list[str]:
    metadata = _metadata_dict(context)
    raw_milestones = metadata.get("milestones")
    if not isinstance(raw_milestones, list):
        return []
    months: list[str] = []
    for item in raw_milestones:
        if not isinstance(item, dict):
            continue
        month = item.get("month") or item.get("targetMonth")
        if isinstance(month, str):
            months.append(month)
            continue
        if item.get("date"):
            try:
                months.append(_month_key(date.fromisoformat(str(item["date"]))))
            except ValueError:
                continue
    return sorted(set(months))


def collect_line_sanity_checks(
    *,
    context: ForecastValidationProjectContext,
    line: ForecastLineRead,
    discipline_code: str | None,
    peer_lines: list[ForecastLineRead],
    peer_codes: dict[str, str | None],
) -> list[ForecastSanityCheckRead]:
    checks: list[ForecastSanityCheckRead] = []
    positive_months = _line_positive_months(line)
    if not positive_months:
        return checks

    if context.start_date is not None:
        start_month = _month_key(context.start_date)
        early_month = next(
            (
                allocation.month
                for allocation in line.allocations
                if allocation.amount > 0.009
                and allocation.month < start_month
                and allocation.actual_amount is None
            ),
            None,
        )
        if early_month is not None:
            checks.append(
                _check(
                    key="revenue_before_project_start",
                    severity="warning",
                    scope="line",
                    title="Revenue lands before project start",
                    detail=(
                        f"{line.label} allocates forecast revenue into {early_month} even though "
                        f"the current project start month is {start_month}."
                    ),
                    recommendation=(
                        "Review project start dates or move early revenue into posted actuals if "
                        "the work genuinely started sooner."
                    ),
                    line_id=line.id,
                    month=early_month,
                )
            )

    if discipline_code in DELIVERY_DISCIPLINE_CODES:
        upstream_first_months = sorted(
            {
                months[0]
                for peer in peer_lines
                if peer_codes.get(peer.id) in UPSTREAM_DELIVERY_CODES
                and (months := _line_positive_months(peer))
            }
        )
        if upstream_first_months and positive_months[0] < upstream_first_months[0]:
            checks.append(
                _check(
                    key="delivery_before_upstream",
                    severity="warning",
                    scope="line",
                    title="Delivery revenue appears before upstream work",
                    detail=(
                        f"{line.label} starts in {positive_months[0]} before upstream finishing "
                        f"disciplines begin in {upstream_first_months[0]}."
                    ),
                    recommendation=(
                        "Push mastering or delivery revenue toward the final project window unless "
                        "there is an explicit staged-delivery reason."
                    ),
                    line_id=line.id,
                    month=positive_months[0],
                )
            )

    should_shape = (
        len(positive_months) > 2
        and (
            context.episode_count is not None
            and context.episode_count > 1
            or bool(_milestone_months(context))
            or discipline_code in SHAPED_DISCIPLINE_CODES
        )
    )
    if should_shape and (
        line.forecast_method_key == "linear"
        or line.allocation_profile_key in {None, "even"}
    ):
        checks.append(
            _check(
                key="flat_curve_on_shaped_project",
                severity="warning",
                scope="line",
                title="Shaped work is using a flat spread",
                detail=(
                    f"{line.label} is spread with {line.forecast_method_key or 'unknown'} / "
                    f"{line.allocation_profile_key or 'no-profile'} timing even though the "
                    "project characteristics imply a shaped curve."
                ),
                recommendation=(
                    "Use a front-, mid-, back-loaded, episodic, or milestone profile that matches "
                    "how the discipline actually earns revenue."
                ),
                line_id=line.id,
            )
        )

    if line.data_sufficiency_score is not None and line.data_sufficiency_score < 45:
        total_amount = sum(allocation.amount for allocation in line.allocations)
        if total_amount > 0:
            band_width = sum(
                (allocation.high_amount or allocation.amount)
                - (allocation.low_amount or allocation.amount)
                for allocation in line.allocations
            )
            if (band_width / total_amount) < 0.12:
                checks.append(
                    _check(
                        key="narrow_bands_sparse_data",
                        severity="warning",
                        scope="line",
                        title="Forecast bands are narrow despite sparse data",
                        detail=(
                            f"{line.label} has data sufficiency {line.data_sufficiency_score:.1f} "
                            "but its forecast band remains tighter than expected."
                        ),
                        recommendation=(
                            "Widen forecast ranges or lower confidence until the quote structure, "
                            "schedule evidence, or actual coverage improves."
                        ),
                        line_id=line.id,
                    )
                )

    actual_months = context.actuals_by_discipline_month.get(line.discipline_id or "", {})
    for month, actual_amount in sorted(actual_months.items()):
        allocation = next((item for item in line.allocations if item.month == month), None)
        if allocation is None:
            checks.append(
                _check(
                    key="actuals_not_assimilated",
                    severity="error",
                    scope="line",
                    title="Completed actual month is missing from the forecast",
                    detail=(
                        f"{line.label} has posted actual revenue for {month} but no matching "
                        "forecast allocation row."
                    ),
                    recommendation=(
                        "Recalculate the forecast so completed work is represented as actuals."
                    ),
                    line_id=line.id,
                    month=month,
                )
            )
            continue
        if (
            allocation.allocation_source != "actual"
            or abs((allocation.actual_amount or 0.0) - actual_amount) > 0.01
            or allocation.amount + 0.01 < actual_amount
        ):
            checks.append(
                _check(
                    key="actuals_not_replacing_forecast",
                    severity="error",
                    scope="line",
                    title="Completed actuals are not replacing forecast values",
                    detail=(
                        f"{line.label} has {actual_amount:.2f} posted for {month}, but the "
                        "forecast row is not fully anchored to actuals."
                    ),
                    recommendation=(
                        "Replace completed-month forecast values with posted actuals before "
                        "submitting or locking the version."
                    ),
                    line_id=line.id,
                    month=month,
                )
            )

    return checks


def collect_version_sanity_checks(
    *,
    context: ForecastValidationProjectContext,
    version: ForecastVersionRead,
    prediction_scenario_output: dict[str, Any] | None,
) -> list[ForecastSanityCheckRead]:
    checks: list[ForecastSanityCheckRead] = []
    metadata_score = metadata_completeness_score(context)

    if (
        version.confidence_score is not None
        and version.confidence_score >= 75
        and metadata_score < 60
    ):
        checks.append(
            _check(
                key="confidence_too_high_for_metadata",
                severity="warning",
                scope="version",
                title="Confidence looks too high for the available metadata",
                detail=(
                    f"The forecast confidence score is {version.confidence_score:.1f} while "
                    f"metadata completeness is only {metadata_score:.1f}."
                ),
                recommendation=(
                    "Lower confidence or complete the missing project metadata before relying on "
                    "the number operationally."
                ),
            )
        )

    if version.engine_source == "unified_forecast_engine" and not version.fallback_tier:
        checks.append(
            _check(
                key="fallback_tier_missing",
                severity="warning",
                scope="version",
                title="Fallback tier is not recorded",
                detail=(
                    "The forecast engine output does not say whether it used in-flight actuals, "
                    "strong comparables, or a weaker fallback."
                ),
                recommendation=(
                    "Persist the fallback tier so operators can judge how trustworthy the "
                    "forecast shape really is."
                ),
            )
        )

    methodology_summary = (
        version.explanation_summary.get("methodologySummary")
        if isinstance(version.explanation_summary, dict)
        else None
    )
    if version.prediction_run_id is not None and not methodology_summary:
        checks.append(
            _check(
                key="prediction_explanation_missing",
                severity="warning",
                scope="version",
                title="Prediction explanation is missing",
                detail=(
                    "This forecast version is prediction-backed but does not include a methodology "
                    "summary explaining the evidence path."
                ),
                recommendation=(
                    "Surface the predictive methodology summary so operators know why the engine "
                    "chose this timing and confidence posture."
                ),
            )
        )

    line_total = round(sum(line.total_amount for line in version.lines), 2)
    if abs(line_total - version.total_amount) > 0.5:
        checks.append(
            _check(
                key="project_total_mismatch_line_total",
                severity="error",
                scope="version",
                title="Project total does not match line totals",
                detail=(
                    f"Version total is {version.total_amount:.2f} but line totals sum to "
                    f"{line_total:.2f}."
                ),
                recommendation=(
                    "Recalculate or repair the forecast version before it is used in rollups."
                ),
            )
        )

    if all(line.discipline_id is not None for line in version.lines):
        discipline_total = round(
            sum(item.amount for item in version.discipline_monthly_rollups),
            2,
        )
        if abs(discipline_total - version.total_amount) > 0.5:
            checks.append(
                _check(
                    key="project_total_mismatch_discipline_total",
                    severity="error",
                    scope="version",
                    title="Project total does not match discipline totals",
                    detail=(
                        f"Discipline rollups sum to {discipline_total:.2f} while the version "
                        f"total is {version.total_amount:.2f}."
                    ),
                    recommendation=(
                        "Repair the discipline mapping or rebuild the rollups before relying on "
                        "discipline-level reporting."
                    ),
                )
            )

    project_rollup_total = round(sum(item.amount for item in version.project_monthly_rollups), 2)
    project_rollup_weighted_total = round(
        sum(item.weighted_amount for item in version.project_monthly_rollups),
        2,
    )
    if abs(project_rollup_total - version.total_amount) > 0.5 or abs(
        project_rollup_weighted_total - version.weighted_total_amount
    ) > 0.5:
        checks.append(
            _check(
                key="rollup_total_mismatch",
                severity="error",
                scope="version",
                title="Rollup totals do not match the project totals",
                detail=(
                    "Monthly rollups no longer reconcile to the stored project totals for gross "
                    "or weighted revenue."
                ),
                recommendation=(
                    "Recalculate the rollups before using the version in portfolio reporting."
                ),
            )
        )

    if version.outcome_type_snapshot == "lost" and (
        version.weighted_total_amount > 0.5 or version.probability_percent > 0.5
    ):
        checks.append(
            _check(
                key="lost_opportunity_weighted_value",
                severity="error",
                scope="version",
                title="Lost opportunity still contributes weighted forecast value",
                detail=(
                    f"The version is marked lost but still carries weighted value of "
                    f"{version.weighted_total_amount:.2f} at {version.probability_percent:.1f}%."
                ),
                recommendation=(
                    "Set lost opportunities to zero probability so booked and weighted views stay "
                    "commercially correct."
                ),
            )
        )

    if context.actuals_by_project_month:
        actual_month_rollups = {item.month: item for item in version.project_monthly_rollups}
        for month, actual_amount in sorted(context.actuals_by_project_month.items()):
            rollup = actual_month_rollups.get(month)
            if rollup is None or abs((rollup.actual_amount or 0.0) - actual_amount) > 0.01:
                checks.append(
                    _check(
                        key="project_actuals_not_reflected",
                        severity="error",
                        scope="version",
                        title="Project-level actuals are not reflected in rollups",
                        detail=(
                            f"Posted actual revenue for {month} is {actual_amount:.2f}, but the "
                            "project rollup does not show the same actual coverage."
                        ),
                        recommendation=(
                            "Recalculate the forecast so completed months flow through into "
                            "project rollups."
                        ),
                        month=month,
                    )
                )

    schedule_months = sorted(
        {
            _month_key(item.start_date)
            for item in context.schedule_ranges
        }
        | {
            _month_key(item.end_date)
            for item in context.schedule_ranges
        }
    )
    forecast_months = [
        item.month for item in version.project_monthly_rollups if item.amount > 0.009
    ]
    if (
        schedule_months
        and forecast_months
        and version.change_summary is not None
        and int(version.change_summary.get("changedMonthCount") or 0) == 0
        and (
            schedule_months[0] != forecast_months[0]
            or schedule_months[-1] != forecast_months[-1]
        )
    ):
        checks.append(
            _check(
                key="no_delta_after_schedule_shift",
                severity="warning",
                scope="version",
                title="Schedule changed but forecast timing did not",
                detail=(
                    "The project schedule window and the forecasted revenue window no longer line "
                    "up, yet the stored delta says no months changed."
                ),
                recommendation=(
                    "Force a reforecast and review whether schedule edits are materially altering "
                    "cash timing."
                ),
            )
        )

    if prediction_scenario_output is not None:
        disciplines = prediction_scenario_output.get("disciplineUsage")
        overrun_risk = prediction_scenario_output.get("overrunRisk")
        high_variance = False
        if isinstance(disciplines, list):
            high_variance = any(
                isinstance(item, dict)
                and item.get("predictedVariancePct") is not None
                and float(item["predictedVariancePct"]) >= 10
                for item in disciplines
            )
        risk_flags = overrun_risk.get("flags") if isinstance(overrun_risk, dict) else []
        has_history_overrun_flag = any(
            isinstance(item, dict) and item.get("key") == "historical_overrun_pattern"
            for item in risk_flags
        )
        if high_variance or has_history_overrun_flag:
            checks.append(
                _check(
                    key="underquote_vs_comparable_history",
                    severity="warning",
                    scope="version",
                    title="Comparable history suggests an underquote risk",
                    detail=(
                        "Prediction evidence indicates meaningful quote-to-actual variance, so the "
                        "forecast should be reviewed as a likely underquote rather than a "
                        "neutral case."
                    ),
                    recommendation=(
                        "Surface a clear margin-risk warning and review whether commercial "
                        "assumptions need to move toward the comparable actual pattern."
                    ),
                )
            )

    if context.episode_count is not None and context.episode_count > 1:
        if not any(line.allocation_profile_key == "episodic" for line in version.lines):
            checks.append(
                _check(
                    key="episodic_cadence_mismatch",
                    severity="warning",
                    scope="version",
                    title="Episodic project is missing an episodic cash cadence",
                    detail=(
                        f"The project is marked with {context.episode_count} episodes, but the "
                        "forecast does not use an episodic allocation profile."
                    ),
                    recommendation=(
                        "Review the monthly spread so revenue pulses line up with episodic "
                        "delivery beats instead of a generic continuous curve."
                    ),
                )
            )

    milestone_months = _milestone_months(context)
    if milestone_months:
        top_months = {
            item.month
            for item in sorted(
                version.project_monthly_rollups,
                key=lambda allocation: allocation.amount,
                reverse=True,
            )[: len(milestone_months)]
        }
        if not top_months.intersection(milestone_months):
            checks.append(
                _check(
                    key="milestone_shape_mismatch",
                    severity="warning",
                    scope="version",
                    title="Milestone timing is not visible in the monthly spread",
                    detail=(
                        "Project metadata includes milestone months, but the largest forecast "
                        "months do not line up with those milestones."
                    ),
                    recommendation=(
                        "Shift revenue toward the milestone months or remove stale milestone data "
                        "if it no longer reflects the delivery plan."
                    ),
                )
            )

    return checks


def collect_detail_sanity_checks(
    versions: list[ForecastVersionRead],
) -> list[ForecastSanityCheckRead]:
    latest_by_scenario: dict[str, ForecastVersionRead] = {}
    for version in versions:
        latest_by_scenario[version.scenario_key] = version

    checks: list[ForecastSanityCheckRead] = []
    if len(latest_by_scenario) < 2:
        return checks

    scenario_versions = list(latest_by_scenario.values())
    totals = [version.total_amount for version in scenario_versions]
    base_total = next(
        (version.total_amount for version in scenario_versions if version.scenario_key == "base"),
        max(totals),
    )
    if (max(totals) - min(totals)) <= max(500.0, base_total * 0.03):
        scenario_labels = ", ".join(sorted(latest_by_scenario))
        checks.append(
            _check(
                key="scenario_outputs_too_similar",
                severity="warning",
                scope="detail",
                title="Scenario outputs are too similar to be decision-useful",
                detail=(
                    f"Scenario versions ({scenario_labels}) differ by less than 3% of the base "
                    "total, so the scenario set is not expressing meaningful commercial spread."
                ),
                recommendation=(
                    "Increase the downside/upside timing, probability, or value deltas so the "
                    "scenario comparison actually changes commercial decisions."
                ),
            )
        )
    return checks
