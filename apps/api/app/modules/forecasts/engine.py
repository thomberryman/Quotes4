from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _month_date(month: str) -> date:
    year_text, month_text = month.split("-", maxsplit=1)
    return date(int(year_text), int(month_text), 1)


def _first_day_next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _month_starts_between(start_date: date, end_date: date) -> list[date]:
    current = date(start_date.year, start_date.month, 1)
    result: list[date] = []
    while current <= end_date:
        result.append(current)
        current = _first_day_next_month(current)
    return result


def _round(amount: float) -> float:
    return round(amount, 2)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _weighted_values(
    months: list[str],
    weights: dict[str, float],
    total_amount: float,
) -> dict[str, float]:
    positive_total = sum(max(0.0, weights.get(month, 0.0)) for month in months)
    if total_amount <= 0 or positive_total <= 0:
        return {month: 0.0 for month in months}

    raw_values = {
        month: total_amount * (max(0.0, weights.get(month, 0.0)) / positive_total)
        for month in months
    }
    rounded_values = {month: _round(amount) for month, amount in raw_values.items()}
    remainder = _round(total_amount - sum(rounded_values.values()))
    if not months or abs(remainder) < 0.01:
        return rounded_values

    ordered_months = sorted(
        months,
        key=lambda month: (
            -(raw_values[month] - int(raw_values[month])),
            month,
        ),
    )
    cents = int(round(remainder * 100))
    increment = 0.01 if cents > 0 else -0.01
    for month in ordered_months:
        if cents == 0:
            break
        rounded_values[month] = _round(rounded_values[month] + increment)
        cents += -1 if cents > 0 else 1
    return rounded_values


def _timeline_position(index: int, count: int) -> float:
    if count <= 1:
        return 0.0
    return index / (count - 1)


DEFAULT_CURVE_PROFILES: dict[str, dict[str, object]] = {
    "even": {
        "shapeKey": "even",
        "description": "Evenly spread remaining revenue across the active schedule window.",
        "flatMultiplier": 1.0,
    },
    "front_loaded": {
        "shapeKey": "front_loaded",
        "description": "Bias revenue toward earlier schedule months.",
        "startMultiplier": 1.3,
        "endMultiplier": 0.7,
        "defaultDisciplineCodes": ["dailies", "offline", "editorial"],
    },
    "mid_loaded": {
        "shapeKey": "mid_loaded",
        "description": "Concentrate revenue through the middle of the schedule.",
        "baseMultiplier": 0.78,
        "peakMultiplier": 1.6,
        "defaultDisciplineCodes": ["vfx", "online"],
    },
    "back_loaded": {
        "shapeKey": "back_loaded",
        "description": "Bias revenue toward finishing and delivery months.",
        "startMultiplier": 0.72,
        "endMultiplier": 1.4,
        "defaultDisciplineCodes": ["grade", "sound", "audio", "delivery"],
    },
    "episodic": {
        "shapeKey": "episodic",
        "description": "Pulse revenue around repeated episodic delivery beats.",
        "baseMultiplier": 0.7,
        "pulseMultiplier": 0.65,
        "pulseSharpness": 3.2,
    },
    "milestone": {
        "shapeKey": "milestone",
        "description": "Allocate revenue to milestone months with a non-zero floor elsewhere.",
        "minimumMultiplier": 0.25,
    },
}


DEFAULT_SEQUENCE_TEMPLATES: dict[str, dict[str, dict[str, float | str]]] = {
    "default": {
        "dailies": {"stage": "dailies", "start_pct": 0.0, "end_pct": 0.18, "overlap_pct": 10.0},
        "offline": {"stage": "editorial", "start_pct": 0.0, "end_pct": 0.48, "overlap_pct": 25.0},
        "editorial": {"stage": "editorial", "start_pct": 0.0, "end_pct": 0.48, "overlap_pct": 25.0},
        "vfx": {"stage": "vfx", "start_pct": 0.18, "end_pct": 0.82, "overlap_pct": 55.0},
        "online": {"stage": "online", "start_pct": 0.62, "end_pct": 0.92, "overlap_pct": 20.0},
        "grade": {"stage": "grade", "start_pct": 0.76, "end_pct": 0.97, "overlap_pct": 18.0},
        "sound": {"stage": "audio", "start_pct": 0.7, "end_pct": 0.98, "overlap_pct": 24.0},
        "audio": {"stage": "audio", "start_pct": 0.7, "end_pct": 0.98, "overlap_pct": 24.0},
        "delivery": {"stage": "delivery", "start_pct": 0.92, "end_pct": 1.0, "overlap_pct": 8.0},
    },
    "trailer_promo": {
        "offline": {"stage": "editorial", "start_pct": 0.0, "end_pct": 0.45, "overlap_pct": 20.0},
        "vfx": {"stage": "vfx", "start_pct": 0.18, "end_pct": 0.8, "overlap_pct": 52.0},
        "online": {"stage": "online", "start_pct": 0.64, "end_pct": 0.9, "overlap_pct": 18.0},
        "grade": {"stage": "grade", "start_pct": 0.8, "end_pct": 0.97, "overlap_pct": 12.0},
        "sound": {"stage": "audio", "start_pct": 0.72, "end_pct": 0.97, "overlap_pct": 20.0},
    },
    "episodic_localisation": {
        "localisation": {
            "stage": "localisation",
            "start_pct": 0.12,
            "end_pct": 0.95,
            "overlap_pct": 70.0,
        },
        "qc": {"stage": "qc", "start_pct": 0.18, "end_pct": 1.0, "overlap_pct": 60.0},
        "delivery": {"stage": "delivery", "start_pct": 0.25, "end_pct": 1.0, "overlap_pct": 55.0},
    },
}


@dataclass
class ForecastEngineScheduleRange:
    id: str
    label: str
    start_date: date
    end_date: date
    discipline_id: str | None = None


@dataclass
class ForecastEngineProjectContext:
    project_id: str
    project_format_key: str | None
    metadata_json: dict[str, object] | None
    episode_count: int | None
    duration_weeks: int | None
    start_date: date | None
    end_date: date | None
    schedule_ranges: list[ForecastEngineScheduleRange]
    project_curve: list[dict[str, Any]] = field(default_factory=list)
    discipline_predictions: dict[str, dict[str, Any]] = field(default_factory=dict)
    actuals_by_discipline_month: dict[str, dict[str, float]] = field(default_factory=dict)
    actuals_by_project_month: dict[str, float] = field(default_factory=dict)
    prediction_run_id: str | None = None
    prediction_scenario_key: str | None = None
    fallback_tier: str | None = None
    confidence_score: float | None = None
    data_sufficiency_score: float | None = None
    curve_profiles: dict[str, dict[str, object]] = field(default_factory=dict)
    sequence_templates: dict[str, dict[str, dict[str, float | str]]] = field(
        default_factory=dict
    )


@dataclass
class ForecastEngineLineInput:
    line_id: str
    label: str
    total_amount: float
    discipline_id: str | None
    discipline_code: str | None
    schedule_range_id: str | None
    manual_allocations: list[tuple[str, float]] = field(default_factory=list)
    notes: str | None = None


@dataclass
class ForecastEngineMonthlyAllocation:
    month: str
    amount: float
    low_amount: float
    high_amount: float
    allocation_source: str
    actual_amount: float | None = None
    source_context: dict[str, object] = field(default_factory=dict)


@dataclass
class ForecastEngineLinePlan:
    forecast_method_key: str
    allocation_profile_key: str
    sequencing_template_key: str | None
    sequencing_stage_key: str | None
    overlap_percent: float | None
    confidence_score: float | None
    data_sufficiency_score: float | None
    fallback_tier: str | None
    actuals_to_date_amount: float
    remaining_amount: float
    forecast_inputs: dict[str, object]
    explanations: list[dict[str, object]]
    allocations: list[ForecastEngineMonthlyAllocation]


def _resolve_template_key(context: ForecastEngineProjectContext) -> str:
    templates = context.sequence_templates or DEFAULT_SEQUENCE_TEMPLATES
    project_format_key = context.project_format_key or ""
    if project_format_key in templates:
        return project_format_key
    if context.episode_count and context.episode_count > 1 and "episodic_localisation" in templates:
        return "episodic_localisation"
    return "default"


def _metadata_dict(context: ForecastEngineProjectContext) -> dict[str, object]:
    return context.metadata_json if isinstance(context.metadata_json, dict) else {}


def _resolve_sequence_window(
    context: ForecastEngineProjectContext,
    line_input: ForecastEngineLineInput,
) -> tuple[str | None, str | None, float, float, float | None]:
    metadata = _metadata_dict(context)
    forecasting = metadata.get("forecasting")
    overrides = forecasting.get("sequencingOverrides") if isinstance(forecasting, dict) else None
    if isinstance(overrides, dict):
        override_key = line_input.discipline_code or line_input.discipline_id or ""
        override = overrides.get(override_key)
        if isinstance(override, dict):
            start_pct = _clamp(float(override.get("startPct", 0.0)), 0.0, 1.0)
            end_pct = _clamp(float(override.get("endPct", 1.0)), start_pct, 1.0)
            overlap_pct = float(override.get("overlapPct", 0.0))
            return (
                str(override.get("templateKey", "project_override")),
                str(override.get("stageKey", override_key or "override")),
                start_pct,
                end_pct,
                overlap_pct,
            )

    template_key = _resolve_template_key(context)
    templates = context.sequence_templates or DEFAULT_SEQUENCE_TEMPLATES
    template = templates.get(
        template_key,
        templates.get("default", DEFAULT_SEQUENCE_TEMPLATES["default"]),
    )
    entry = template.get(line_input.discipline_code or "")
    if entry is None:
        default_template = templates.get("default", DEFAULT_SEQUENCE_TEMPLATES["default"])
        entry = default_template.get(line_input.discipline_code or "")
    if entry is None:
        return (template_key, None, 0.0, 1.0, None)
    return (
        template_key,
        str(entry["stage"]),
        float(entry["start_pct"]),
        float(entry["end_pct"]),
        float(entry["overlap_pct"]),
    )


def _resolve_profile_key(
    context: ForecastEngineProjectContext,
    line_input: ForecastEngineLineInput,
) -> str:
    profiles = context.curve_profiles or DEFAULT_CURVE_PROFILES
    spread_profile = next(
        (
            str(item.get("spreadProfile"))
            for item in context.project_curve
            if item.get("spreadProfile") and str(item.get("spreadProfile")) in profiles
        ),
        None,
    )
    if spread_profile:
        return spread_profile

    metadata = _metadata_dict(context)
    milestones = metadata.get("milestones")
    if isinstance(milestones, list) and milestones:
        return "milestone"
    if context.episode_count and context.episode_count > 1:
        return "episodic"

    discipline_code = line_input.discipline_code or ""
    for profile_key, profile in profiles.items():
        default_discipline_codes = profile.get("defaultDisciplineCodes")
        if isinstance(default_discipline_codes, list) and discipline_code in {
            str(item) for item in default_discipline_codes
        }:
            return profile_key

    if discipline_code in {"dailies", "offline", "editorial"} and "front_loaded" in profiles:
        return "front_loaded"
    if discipline_code in {"grade", "sound", "delivery"} and "back_loaded" in profiles:
        return "back_loaded"
    if discipline_code in {"vfx", "online"} and "mid_loaded" in profiles:
        return "mid_loaded"
    return "even"


def _milestone_weights(
    context: ForecastEngineProjectContext,
) -> dict[str, float]:
    metadata = _metadata_dict(context)
    raw_milestones = metadata.get("milestones")
    if not isinstance(raw_milestones, list):
        return {}
    weights: dict[str, float] = {}
    for milestone in raw_milestones:
        if not isinstance(milestone, dict):
            continue
        month = milestone.get("month") or milestone.get("targetMonth")
        if not month and milestone.get("date"):
            try:
                month = _month_key(date.fromisoformat(str(milestone["date"])))
            except ValueError:
                month = None
        if not month:
            continue
        weight = float(
            milestone.get(
                "weight", milestone.get("revenueWeightPct", 100 / max(len(raw_milestones), 1))
            )
        )
        weights[str(month)] = max(0.0, weights.get(str(month), 0.0) + weight)
    return weights


def _episodic_factor(
    position: float,
    episode_count: int,
    *,
    base_multiplier: float,
    pulse_multiplier: float,
    pulse_sharpness: float,
) -> float:
    if episode_count <= 1:
        return 1.0
    pulse_count = max(1, episode_count)
    pulse_strength = 0.0
    for episode_index in range(pulse_count):
        center = episode_index / max(pulse_count - 1, 1)
        distance = abs(position - center)
        pulse_strength = max(pulse_strength, max(0.0, 1.0 - (distance * pulse_sharpness)))
    return base_multiplier + (pulse_strength * pulse_multiplier)


def _profile_definition(
    context: ForecastEngineProjectContext,
    profile_key: str,
) -> dict[str, object]:
    profiles = context.curve_profiles or DEFAULT_CURVE_PROFILES
    if profile_key in profiles:
        return profiles[profile_key]
    if profile_key in DEFAULT_CURVE_PROFILES:
        return DEFAULT_CURVE_PROFILES[profile_key]
    return {"shapeKey": profile_key}


def _profile_factor(
    context: ForecastEngineProjectContext,
    profile_key: str,
    position: float,
    *,
    episode_count: int | None,
    milestone_weight: float | None,
    month_count: int,
) -> float:
    definition = _profile_definition(context, profile_key)
    shape_key = str(definition.get("shapeKey") or profile_key)
    if shape_key == "front_loaded":
        start_multiplier = float(definition.get("startMultiplier", 1.3))
        end_multiplier = float(definition.get("endMultiplier", 0.7))
        return start_multiplier - ((start_multiplier - end_multiplier) * position)
    if shape_key == "mid_loaded":
        base_multiplier = float(definition.get("baseMultiplier", 0.78))
        peak_multiplier = float(definition.get("peakMultiplier", 1.6))
        return base_multiplier + (
            (peak_multiplier - base_multiplier) * (1 - abs(position - 0.5) * 2)
        )
    if shape_key == "back_loaded":
        start_multiplier = float(definition.get("startMultiplier", 0.72))
        end_multiplier = float(definition.get("endMultiplier", 1.4))
        return start_multiplier + ((end_multiplier - start_multiplier) * position)
    if shape_key == "episodic":
        return _episodic_factor(
            position,
            episode_count or month_count,
            base_multiplier=float(definition.get("baseMultiplier", 0.7)),
            pulse_multiplier=float(definition.get("pulseMultiplier", 0.65)),
            pulse_sharpness=float(definition.get("pulseSharpness", 3.2)),
        )
    if shape_key == "milestone":
        return max(float(definition.get("minimumMultiplier", 0.25)), milestone_weight or 0.0)
    return float(definition.get("flatMultiplier", 1.0))


def _sequence_factor(position: float, start_pct: float, end_pct: float) -> float:
    if position < start_pct:
        if start_pct <= 0:
            return 0.15
        distance = (start_pct - position) / start_pct
        return max(0.12, 1 - (distance * 0.9))
    if position > end_pct:
        if end_pct >= 1:
            return 0.15
        distance = (position - end_pct) / max(1 - end_pct, 0.001)
        return max(0.12, 1 - (distance * 0.9))
    return 1.0


def _project_curve_weights(
    context: ForecastEngineProjectContext,
    months: list[str],
) -> dict[str, float]:
    weights: dict[str, float] = {}
    for month in months:
        matching = next(
            (item for item in context.project_curve if item.get("month") == month), None
        )
        if matching is None:
            weights[month] = 1.0
            continue
        if matching.get("predictedAmountMedian") is not None:
            weights[month] = max(0.0, float(matching["predictedAmountMedian"]))
        elif matching.get("medianSharePct") is not None:
            weights[month] = max(0.0, float(matching["medianSharePct"]))
        else:
            weights[month] = 1.0
    return weights


def _resolve_months(
    context: ForecastEngineProjectContext,
    line_input: ForecastEngineLineInput,
) -> list[str]:
    if line_input.schedule_range_id is not None:
        selected_range = next(
            (item for item in context.schedule_ranges if item.id == line_input.schedule_range_id),
            None,
        )
        if selected_range is not None:
            return [
                _month_key(item)
                for item in _month_starts_between(
                    selected_range.start_date, selected_range.end_date
                )
            ]

    discipline_ranges = [
        item for item in context.schedule_ranges if item.discipline_id == line_input.discipline_id
    ]
    if discipline_ranges:
        start_date = min(item.start_date for item in discipline_ranges)
        end_date = max(item.end_date for item in discipline_ranges)
        return [_month_key(item) for item in _month_starts_between(start_date, end_date)]

    if context.project_curve:
        return sorted({str(item["month"]) for item in context.project_curve if item.get("month")})

    if context.start_date is not None and context.end_date is not None:
        return [
            _month_key(item) for item in _month_starts_between(context.start_date, context.end_date)
        ]

    actual_months = context.actuals_by_discipline_month.get(line_input.discipline_id or "", {})
    if actual_months:
        return sorted(actual_months)
    if context.actuals_by_project_month:
        return sorted(context.actuals_by_project_month)
    return []


def _build_low_high(
    context: ForecastEngineProjectContext,
    month: str,
    amount: float,
    *,
    allocation_source: str,
) -> tuple[float, float]:
    if allocation_source == "actual":
        rounded = _round(amount)
        return rounded, rounded

    row = next((item for item in context.project_curve if item.get("month") == month), None)
    if row and row.get("predictedAmountMedian"):
        median = float(row["predictedAmountMedian"])
        if median > 0:
            low_ratio = (
                float(row.get("predictedAmountLow") or median) / median
                if row.get("predictedAmountLow") is not None
                else None
            )
            high_ratio = (
                float(row.get("predictedAmountHigh") or median) / median
                if row.get("predictedAmountHigh") is not None
                else None
            )
            if low_ratio is not None and high_ratio is not None:
                return (_round(amount * low_ratio), _round(amount * high_ratio))

    confidence_score = context.confidence_score or 55.0
    sufficiency_score = context.data_sufficiency_score or 50.0
    variance_pct = _clamp(
        4.0 + ((100 - confidence_score) * 0.09) + ((100 - sufficiency_score) * 0.06),
        4.0,
        24.0,
    )
    return (
        _round(amount * (1 - (variance_pct / 100))),
        _round(amount * (1 + (variance_pct / 100))),
    )


def build_line_plan(
    context: ForecastEngineProjectContext,
    line_input: ForecastEngineLineInput,
) -> ForecastEngineLinePlan:
    if line_input.manual_allocations:
        allocations = [
            ForecastEngineMonthlyAllocation(
                month=month,
                amount=_round(amount),
                low_amount=_round(amount),
                high_amount=_round(amount),
                allocation_source="manual_override",
                actual_amount=None,
                source_context={
                    "reason": "manual_override",
                    "predictionRunId": context.prediction_run_id,
                    "scenarioKey": context.prediction_scenario_key,
                },
            )
            for month, amount in sorted(line_input.manual_allocations, key=lambda item: item[0])
        ]
        total_amount = sum(item.amount for item in allocations)
        return ForecastEngineLinePlan(
            forecast_method_key="manual",
            allocation_profile_key="manual",
            sequencing_template_key=None,
            sequencing_stage_key=None,
            overlap_percent=None,
            confidence_score=100.0,
            data_sufficiency_score=100.0,
            fallback_tier="manual_override",
            actuals_to_date_amount=0.0,
            remaining_amount=max(0.0, _round(line_input.total_amount - total_amount)),
            forecast_inputs={
                "lineId": line_input.line_id,
                "manualAllocationCount": len(allocations),
            },
            explanations=[
                {
                    "key": "manual_override",
                    "label": "Manual override",
                    "impact": "operator_controlled",
                    "detail": (
                        "Operator-entered month values override automatic "
                        "forecast timing for this line."
                    ),
                }
            ],
            allocations=allocations,
        )

    months = _resolve_months(context, line_input)
    if not months:
        return ForecastEngineLinePlan(
            forecast_method_key="linear",
            allocation_profile_key="even",
            sequencing_template_key=None,
            sequencing_stage_key=None,
            overlap_percent=None,
            confidence_score=context.confidence_score,
            data_sufficiency_score=context.data_sufficiency_score,
            fallback_tier=context.fallback_tier,
            actuals_to_date_amount=0.0,
            remaining_amount=line_input.total_amount,
            forecast_inputs={"lineId": line_input.line_id},
            explanations=[
                {
                    "key": "missing_calendar",
                    "label": "Missing calendar",
                    "impact": "fallback_linear",
                    "detail": (
                        "The project is missing enough schedule structure to "
                        "produce a monthly forecast."
                    ),
                }
            ],
            allocations=[],
        )

    profile_key = _resolve_profile_key(context, line_input)
    template_key, stage_key, start_pct, end_pct, overlap_pct = _resolve_sequence_window(
        context, line_input
    )
    milestone_weights = _milestone_weights(context)
    project_curve_weights = _project_curve_weights(context, months)
    weights: dict[str, float] = {}
    for index, month in enumerate(months):
        position = _timeline_position(index, len(months))
        milestone_weight = milestone_weights.get(month)
        weight = project_curve_weights.get(month, 1.0)
        weight *= _profile_factor(
            context,
            profile_key,
            position,
            episode_count=context.episode_count,
            milestone_weight=milestone_weight,
            month_count=len(months),
        )
        weight *= _sequence_factor(position, start_pct, end_pct)
        if overlap_pct:
            weight *= 1 + (overlap_pct / 400)
        if context.duration_weeks is not None and context.duration_weeks <= 4:
            weight *= 1.08 if profile_key in {"front_loaded", "back_loaded", "mid_loaded"} else 1.0
        weights[month] = max(0.05, weight)

    discipline_actuals = (
        context.actuals_by_discipline_month.get(line_input.discipline_id or "")
        if line_input.discipline_id is not None
        else None
    ) or {}
    actual_months = sorted(month for month in months if month in discipline_actuals)
    actual_total = _round(sum(discipline_actuals.get(month, 0.0) for month in actual_months))
    remaining_total = max(0.0, _round(line_input.total_amount - actual_total))
    remaining_months = [month for month in months if month not in actual_months]
    remaining_amounts = _weighted_values(remaining_months, weights, remaining_total)

    method_key = "curve"
    if context.project_curve:
        method_key = "hybrid"
    if profile_key == "milestone":
        method_key = "milestone"
    if not context.project_curve and profile_key == "even":
        method_key = "linear"

    allocations: list[ForecastEngineMonthlyAllocation] = []
    for month in months:
        if month in discipline_actuals:
            amount = _round(discipline_actuals[month])
            allocation_source = "actual"
            actual_amount = amount
        else:
            amount = _round(remaining_amounts.get(month, 0.0))
            allocation_source = "forecast"
            actual_amount = None
        low_amount, high_amount = _build_low_high(
            context,
            month,
            amount,
            allocation_source=allocation_source,
        )
        allocations.append(
            ForecastEngineMonthlyAllocation(
                month=month,
                amount=amount,
                low_amount=low_amount,
                high_amount=high_amount,
                allocation_source=allocation_source,
                actual_amount=actual_amount,
                source_context={
                    "predictionRunId": context.prediction_run_id,
                    "scenarioKey": context.prediction_scenario_key,
                    "profileKey": profile_key,
                    "stageKey": stage_key,
                    "templateKey": template_key,
                },
            )
        )

    explanations = [
        {
            "key": "forecast_method",
            "label": "Forecast method",
            "impact": method_key,
            "detail": (
                "Monthly timing blends predictive project curve evidence with sequencing-aware "
                "discipline timing."
                if method_key == "hybrid"
                else "Monthly timing uses the selected project curve profile."
            ),
        },
        {
            "key": "sequence_window",
            "label": "Sequencing window",
            "impact": stage_key or "full_timeline",
            "detail": (
                f"Discipline timing is biased into the {stage_key} window between "
                f"{start_pct * 100:.0f}% and {end_pct * 100:.0f}% of the project timeline."
                if stage_key is not None
                else (
                    "No discipline-specific sequence window was available, so "
                    "the full timeline is used."
                )
            ),
        },
    ]
    if actual_total > 0:
        explanations.append(
            {
                "key": "partial_actuals",
                "label": "Partial actuals",
                "impact": f"{actual_total:.2f}",
                "detail": (
                    "Posted actual revenue replaces forecast values for "
                    "completed months before remaining work is reforecast."
                ),
            }
        )

    return ForecastEngineLinePlan(
        forecast_method_key=method_key,
        allocation_profile_key=profile_key,
        sequencing_template_key=template_key,
        sequencing_stage_key=stage_key,
        overlap_percent=overlap_pct,
        confidence_score=context.confidence_score,
        data_sufficiency_score=context.data_sufficiency_score,
        fallback_tier=context.fallback_tier,
        actuals_to_date_amount=actual_total,
        remaining_amount=remaining_total,
        forecast_inputs={
            "lineId": line_input.line_id,
            "disciplineCode": line_input.discipline_code,
            "profileKey": profile_key,
            "projectCurveMonthCount": len(context.project_curve),
            "actualMonthCount": len(actual_months),
        },
        explanations=explanations,
        allocations=allocations,
    )


def summarize_version_delta(
    *,
    previous_total_amount: float | None,
    current_total_amount: float,
    previous_weighted_total_amount: float | None,
    current_weighted_total_amount: float,
    previous_months: dict[str, float] | None,
    current_months: dict[str, float],
    reason: str | None,
    scenario_key: str,
) -> dict[str, object]:
    previous_total = previous_total_amount or 0.0
    previous_weighted = previous_weighted_total_amount or 0.0
    previous_month_values = previous_months or {}
    changed_months = sorted(
        {
            month
            for month in set(previous_month_values) | set(current_months)
            if _round(previous_month_values.get(month, 0.0))
            != _round(current_months.get(month, 0.0))
        }
    )
    return {
        "reason": reason,
        "scenarioKey": scenario_key,
        "totalAmountDelta": _round(current_total_amount - previous_total),
        "weightedTotalAmountDelta": _round(current_weighted_total_amount - previous_weighted),
        "changedMonthCount": len(changed_months),
        "changedMonths": changed_months[:12],
    }
