from __future__ import annotations

from datetime import UTC, date, datetime

from app.modules.forecasts.schemas import (
    ForecastDisciplineMonthlyRollupRead,
    ForecastLineRead,
    ForecastMonthlyAllocationRead,
    ForecastProjectMonthlyRollupRead,
    ForecastVersionRead,
)
from app.modules.forecasts.validation import (
    ForecastValidationProjectContext,
    ForecastValidationQuoteLine,
    ForecastValidationScheduleRange,
    collect_detail_sanity_checks,
    collect_line_sanity_checks,
    collect_version_sanity_checks,
)


def _allocation(
    month: str,
    amount: float,
    *,
    low: float | None = None,
    high: float | None = None,
    actual_amount: float | None = None,
    source: str | None = "forecast",
) -> ForecastMonthlyAllocationRead:
    return ForecastMonthlyAllocationRead(
        month=month,
        amount=amount,
        weighted_amount=round(amount * 0.6, 2),
        low_amount=low if low is not None else amount,
        high_amount=high if high is not None else amount,
        actual_amount=actual_amount,
        allocation_source=source,
        source_context=None,
    )


def _line(
    line_id: str,
    label: str,
    total_amount: float,
    *,
    discipline_id: str | None,
    forecast_method_key: str | None = "curve",
    allocation_profile_key: str | None = "back_loaded",
    confidence_score: float | None = 55.0,
    data_sufficiency_score: float | None = 55.0,
    allocations: list[ForecastMonthlyAllocationRead],
) -> ForecastLineRead:
    return ForecastLineRead(
        id=line_id,
        source_line_id=line_id,
        label=label,
        total_amount=total_amount,
        weighted_total_amount=round(total_amount * 0.6, 2),
        currency_code="GBP",
        allocation_method="schedule",
        discipline_id=discipline_id,
        schedule_range_id=None,
        notes=None,
        forecast_method_key=forecast_method_key,
        allocation_profile_key=allocation_profile_key,
        sequencing_template_key=None,
        sequencing_stage_key=None,
        overlap_percent=None,
        confidence_score=confidence_score,
        data_sufficiency_score=data_sufficiency_score,
        fallback_tier=None,
        actuals_to_date_amount=None,
        remaining_amount=None,
        forecast_inputs=None,
        explanations=[],
        sanity_checks=[],
        issues=[],
        allocations=allocations,
    )


def _version(
    *,
    scenario_key: str = "base",
    total_amount: float = 10000,
    weighted_total_amount: float = 6000,
    probability_percent: float = 60,
    outcome_type_snapshot: str = "bid",
    confidence_score: float | None = 82.0,
    data_sufficiency_score: float | None = 32.0,
    fallback_tier: str | None = None,
    prediction_run_id: str | None = None,
    explanation_summary: dict[str, object] | None = None,
    change_summary: dict[str, object] | None = None,
    lines: list[ForecastLineRead] | None = None,
    discipline_rollups: list[ForecastDisciplineMonthlyRollupRead] | None = None,
    project_rollups: list[ForecastProjectMonthlyRollupRead] | None = None,
) -> ForecastVersionRead:
    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    return ForecastVersionRead(
        id=f"version_{scenario_key}",
        forecast_id="forecast_1",
        version_number=1,
        status="draft",
        title=f"{scenario_key.title()} version",
        notes_text=None,
        outcome_type_snapshot=outcome_type_snapshot,
        probability_percent=probability_percent,
        total_amount=total_amount,
        weighted_total_amount=weighted_total_amount,
        scenario_key=scenario_key,
        engine_source="unified_forecast_engine",
        prediction_run_id=prediction_run_id,
        prediction_scenario_key=scenario_key if prediction_run_id is not None else None,
        confidence_score=confidence_score,
        data_sufficiency_score=data_sufficiency_score,
        fallback_tier=fallback_tier,
        change_summary=change_summary,
        source_quote_version_id="quote_v1",
        is_source_quote_current=True,
        revision_reason=None,
        parent_version_id=None,
        created_at=now,
        updated_at=now,
        explanation_summary=explanation_summary,
        sanity_checks=[],
        issues=[],
        lines=lines or [],
        discipline_monthly_rollups=discipline_rollups or [],
        project_monthly_rollups=project_rollups or [],
    )


def test_collect_line_sanity_checks_flags_calendar_sequence_band_and_actuals_issues() -> None:
    context = ForecastValidationProjectContext(
        project_id="project_line_checks",
        project_name="Line sanity checks",
        status="active",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 4, 30),
        project_format_key="trailer_promo",
        duration_weeks=10,
        episode_count=1,
        metadata_json=None,
        current_quote_version_id="quote_v1",
        actuals_by_discipline_month={"disc_delivery": {"2026-01": 2500}},
        actuals_by_project_month={},
    )
    delivery_line = _line(
        "line_delivery",
        "Mastering",
        7500,
        discipline_id="disc_delivery",
        forecast_method_key="linear",
        allocation_profile_key="even",
        data_sufficiency_score=30,
        allocations=[
            _allocation("2026-01", 2500, low=2450, high=2550, source="forecast"),
            _allocation("2026-02", 2500, low=2450, high=2550, source="forecast"),
            _allocation("2026-03", 2500, low=2450, high=2550, source="forecast"),
        ],
    )
    online_line = _line(
        "line_online",
        "Online",
        7000,
        discipline_id="disc_online",
        forecast_method_key="curve",
        allocation_profile_key="mid_loaded",
        allocations=[
            _allocation("2026-03", 3500, low=3000, high=4000),
            _allocation("2026-04", 3500, low=3000, high=4000),
        ],
    )

    checks = collect_line_sanity_checks(
        context=context,
        line=delivery_line,
        discipline_code="mastering",
        peer_lines=[delivery_line, online_line],
        peer_codes={
            delivery_line.id: "mastering",
            online_line.id: "online",
        },
    )

    assert {check.key for check in checks} == {
        "revenue_before_project_start",
        "delivery_before_upstream",
        "flat_curve_on_shaped_project",
        "narrow_bands_sparse_data",
        "actuals_not_replacing_forecast",
    }
    assert any(check.blocking for check in checks)


def test_collect_version_sanity_checks_flags_reconciliation_confidence_and_signal_gaps() -> None:
    context = ForecastValidationProjectContext(
        project_id="project_version_checks",
        project_name="Version sanity checks",
        status="lost",
        start_date=None,
        end_date=None,
        project_format_key=None,
        duration_weeks=None,
        episode_count=3,
        metadata_json={"milestones": [{"month": "2026-06"}]},
        current_quote_version_id="quote_v1",
        schedule_ranges=[
            ForecastValidationScheduleRange(
                id="range_1",
                label="Schedule",
                start_date=date(2026, 4, 1),
                end_date=date(2026, 8, 31),
                discipline_id="disc_offline",
                discipline_code="offline",
                allocation_percent=100.0,
            )
        ],
        quote_lines=[],
        actuals_by_discipline_month={},
        actuals_by_project_month={"2026-04": 2000},
    )
    lines = [
        _line(
            "line_1",
            "Offline",
            9000,
            discipline_id="disc_offline",
            forecast_method_key="curve",
            allocation_profile_key="front_loaded",
            allocations=[
                _allocation("2026-04", 3000, low=2900, high=3100),
                _allocation("2026-05", 3000, low=2900, high=3100),
                _allocation("2026-06", 3000, low=2900, high=3100),
            ],
        )
    ]
    version = _version(
        total_amount=10000,
        weighted_total_amount=1000,
        probability_percent=10,
        outcome_type_snapshot="lost",
        confidence_score=86,
        data_sufficiency_score=32,
        fallback_tier=None,
        prediction_run_id="prediction_1",
        explanation_summary={},
        change_summary={"changedMonthCount": 0},
        lines=lines,
        discipline_rollups=[
            ForecastDisciplineMonthlyRollupRead(
                discipline_id="disc_offline",
                month="2026-04",
                amount=2500,
                weighted_amount=250,
                low_amount=2400,
                high_amount=2600,
                actual_amount=0,
            )
        ],
        project_rollups=[
            ForecastProjectMonthlyRollupRead(
                month="2026-04",
                amount=3000,
                weighted_amount=300,
                low_amount=2900,
                high_amount=3100,
                actual_amount=0,
            ),
            ForecastProjectMonthlyRollupRead(
                month="2026-05",
                amount=3000,
                weighted_amount=300,
                low_amount=2900,
                high_amount=3100,
                actual_amount=0,
            ),
            ForecastProjectMonthlyRollupRead(
                month="2026-06",
                amount=3000,
                weighted_amount=300,
                low_amount=2900,
                high_amount=3100,
                actual_amount=0,
            ),
        ],
    )

    checks = collect_version_sanity_checks(
        context=context,
        version=version,
        prediction_scenario_output={
            "disciplineUsage": [{"predictedVariancePct": 12}],
            "overrunRisk": {"flags": [{"key": "historical_overrun_pattern"}]},
        },
    )

    assert {
        "confidence_too_high_for_metadata",
        "fallback_tier_missing",
        "prediction_explanation_missing",
        "project_total_mismatch_line_total",
        "project_total_mismatch_discipline_total",
        "rollup_total_mismatch",
        "lost_opportunity_weighted_value",
        "project_actuals_not_reflected",
        "no_delta_after_schedule_shift",
        "underquote_vs_comparable_history",
        "episodic_cadence_mismatch",
        "milestone_shape_mismatch",
    } <= {check.key for check in checks}
    assert any(check.blocking for check in checks)


def test_collect_detail_sanity_checks_flags_scenarios_that_are_too_similar() -> None:
    shared_line = _line(
        "line_shared",
        "Offline",
        10000,
        discipline_id="disc_offline",
        allocations=[_allocation("2026-04", 10000)],
    )
    versions = [
        _version(
            scenario_key="base",
            total_amount=100000,
            weighted_total_amount=65000,
            lines=[shared_line],
        ),
        _version(
            scenario_key="upside",
            total_amount=101500,
            weighted_total_amount=67000,
            lines=[shared_line],
        ),
        _version(
            scenario_key="downside",
            total_amount=98500,
            weighted_total_amount=62000,
            lines=[shared_line],
        ),
    ]

    checks = collect_detail_sanity_checks(versions)

    assert [check.key for check in checks] == ["scenario_outputs_too_similar"]
