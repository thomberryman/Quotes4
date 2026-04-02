from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from app.modules.predictions.constants import SCENARIO_DEFAULTS, SCENARIO_TITLES
from app.modules.predictions.types import PredictionModuleResult
from app.modules.predictions.utils import clamp, confidence_label, month_date, month_key


def _shift_months(month: str, shift: int) -> str:
    current = month_date(month)
    year = current.year + ((current.month - 1 + shift) // 12)
    month_value = ((current.month - 1 + shift) % 12) + 1
    return f"{year:04d}-{month_value:02d}"


def _scenario_risk(base_risk: dict[str, Any], variance_delta_pct: float, schedule_shift_months: int) -> dict[str, Any]:
    risk = deepcopy(base_risk)
    if not risk["flags"] and variance_delta_pct <= 0 and schedule_shift_months <= 0:
        return risk
    if variance_delta_pct > 0 or schedule_shift_months > 0:
        if risk["level"] == "low":
            risk["level"] = "medium"
        elif risk["level"] == "medium":
            risk["level"] = "high"
        risk["flags"].append(
            {
                "key": "scenario_pressure",
                "severity": "warning" if risk["level"] != "high" else "high",
                "title": "Scenario downside pressure",
                "detail": "Scenario assumptions increase timing or variance pressure relative to the base case.",
                "confidence": "medium",
                "comparableProjectIds": [],
                "reasoning": ["Scenario levers explicitly increase delay or variance assumptions."],
            }
        )
    return risk


def build_scenarios(
    *,
    quote_guidance: dict[str, Any] | None,
    spend_prediction: dict[str, Any] | None,
    discipline_predictions: list[dict[str, Any]],
    monthly_revenue_spread: list[dict[str, Any]],
    overrun_risk: dict[str, Any],
    win_probability: dict[str, Any] | None,
    scenario_assumptions: dict[str, dict[str, object]] | None,
    fallback_tier: str,
    data_sufficiency_score: float,
) -> PredictionModuleResult:
    scenarios: list[dict[str, Any]] = []
    for scenario_key, defaults in SCENARIO_DEFAULTS.items():
        merged = {**defaults, **(scenario_assumptions or {}).get(scenario_key, {})}
        quote_multiplier = float(merged.get("quoteMultiplier", 1.0))
        actual_multiplier = float(merged.get("actualMultiplier", 1.0))
        variance_delta_pct = float(merged.get("varianceDeltaPct", 0.0))
        win_delta_pct = float(merged.get("winProbabilityDeltaPct", 0.0))
        schedule_shift_months = int(merged.get("scheduleShiftMonths", 0))

        scenario_quote = deepcopy(quote_guidance) if quote_guidance is not None else None
        if scenario_quote is not None:
            scenario_quote.pop("comparableQuoteRange", None)
            scenario_quote.pop("actualInformedQuoteRange", None)
            for key in ("low", "median", "high", "recommendedLow", "recommendedMedian", "recommendedHigh"):
                if scenario_quote.get(key) is not None:
                    scenario_quote[key] = round(float(scenario_quote[key]) * quote_multiplier, 2)

        scenario_spend = deepcopy(spend_prediction) if spend_prediction is not None else None
        if scenario_spend is not None:
            base_confidence_score = float(scenario_spend.get("confidenceScore") or 0)
            adjusted_confidence_score = clamp(
                base_confidence_score
                - max(0.0, variance_delta_pct * 0.8)
                + max(0.0, abs(min(variance_delta_pct, 0.0)) * 0.2),
                0.0,
                100.0,
            )
            discipline_spend = scenario_spend.get("disciplineSpend") or []
            for item in discipline_spend:
                current_actual_cost = round(float(item.get("currentActualCost") or 0), 2)
                if item.get("predictedTotalCost") is not None:
                    scaled_total = round(float(item["predictedTotalCost"]) * actual_multiplier, 2)
                    scaled_total = max(current_actual_cost, scaled_total)
                    item["predictedTotalCost"] = scaled_total
                    item["predictedRemainingCost"] = round(
                        max(0.0, scaled_total - current_actual_cost),
                        2,
                    )
            predicted_total_cost = (
                round(
                    sum(float(item.get("predictedTotalCost") or 0) for item in discipline_spend),
                    2,
                )
                if discipline_spend
                else round(float(scenario_spend["predictedTotalCost"]) * actual_multiplier, 2)
                if scenario_spend.get("predictedTotalCost") is not None
                else None
            )
            current_actual_cost = round(float(scenario_spend.get("currentActualCost") or 0), 2)
            if predicted_total_cost is not None:
                predicted_total_cost = max(current_actual_cost, predicted_total_cost)
            scenario_quote_median = (
                scenario_quote.get("recommendedMedian") or scenario_quote.get("median")
                if scenario_quote is not None
                else None
            )
            implied_margin_amount = (
                round(float(scenario_quote_median) - float(predicted_total_cost), 2)
                if scenario_quote_median not in (None, 0) and predicted_total_cost is not None
                else None
            )
            scenario_spend["predictedTotalCost"] = predicted_total_cost
            scenario_spend["predictedRemainingCost"] = (
                round(max(0.0, float(predicted_total_cost) - current_actual_cost), 2)
                if predicted_total_cost is not None
                else None
            )
            scenario_spend["impliedMarginAmount"] = implied_margin_amount
            scenario_spend["impliedMarginPct"] = (
                round((float(implied_margin_amount) / float(scenario_quote_median)) * 100, 2)
                if implied_margin_amount is not None and scenario_quote_median not in (None, 0)
                else None
            )
            scenario_spend["confidenceScore"] = round(adjusted_confidence_score, 2)
            scenario_spend["confidence"] = confidence_label(adjusted_confidence_score)

        scenario_disciplines = deepcopy(discipline_predictions)
        for item in scenario_disciplines:
            for key in ("predictedAmountLow", "predictedAmountMedian", "predictedAmountHigh", "quotedAmount"):
                if item.get(key) is not None:
                    item[key] = round(float(item[key]) * quote_multiplier, 2)
            if item.get("predictedActualAmount") is not None:
                item["predictedActualAmount"] = round(float(item["predictedActualAmount"]) * actual_multiplier, 2)
            if item.get("predictedVariancePct") is not None:
                item["predictedVariancePct"] = round(float(item["predictedVariancePct"]) + variance_delta_pct, 2)
            if item.get("predictedVariancePct") is not None and item["predictedVariancePct"] >= 10:
                item["overrunRisk"] = "high"
            elif item.get("predictedVariancePct") is not None and item["predictedVariancePct"] >= 4:
                item["overrunRisk"] = "medium"
            else:
                item["overrunRisk"] = "low"

        scenario_monthly = deepcopy(monthly_revenue_spread)
        for row in scenario_monthly:
            row["month"] = _shift_months(row["month"], schedule_shift_months)
            for key in ("predictedAmountLow", "predictedAmountMedian", "predictedAmountHigh"):
                if row.get(key) is not None:
                    row[key] = round(float(row[key]) * actual_multiplier, 2)

        scenario_win_probability = deepcopy(win_probability) if win_probability is not None else None
        projected_weighted_revenue = None
        if scenario_win_probability is not None:
            probability_pct = clamp(float(scenario_win_probability["probabilityPct"]) + win_delta_pct, 0.0, 100.0)
            scenario_win_probability["probabilityPct"] = round(probability_pct, 2)
            if probability_pct >= 70:
                scenario_win_probability["probabilityBand"] = "high"
            elif probability_pct >= 45:
                scenario_win_probability["probabilityBand"] = "medium"
            else:
                scenario_win_probability["probabilityBand"] = "low"
            scenario_win_probability["confidence"] = confidence_label(float(scenario_win_probability["confidenceScore"]))
            scenario_win_probability["fallbackTier"] = fallback_tier
            scenario_win_probability["reasoning"] = list(scenario_win_probability["reasoning"]) + [
                f"Scenario adjustment changes win probability by {win_delta_pct:.1f} percentage points."
            ]

        projected_total_revenue = round(
            sum(float(row["predictedAmountMedian"] or 0) for row in scenario_monthly),
            2,
        )
        if scenario_win_probability is not None:
            projected_weighted_revenue = round(
                projected_total_revenue * (float(scenario_win_probability["probabilityPct"]) / 100),
                2,
            )
        scenario = {
            "id": None,
            "scenarioKey": scenario_key,
            "title": SCENARIO_TITLES[scenario_key],
            "isExpected": scenario_key == "base",
            "assumptionOverrides": merged,
            "likelyQuoteRange": scenario_quote,
            "spendSummary": scenario_spend,
            "disciplineUsage": scenario_disciplines,
            "monthlyRevenueSpread": sorted(scenario_monthly, key=lambda item: item["month"]),
            "overrunRisk": _scenario_risk(overrun_risk, variance_delta_pct, schedule_shift_months),
            "winProbability": scenario_win_probability,
            "projectedTotalRevenue": projected_total_revenue,
            "projectedWeightedRevenue": projected_weighted_revenue,
            "promotedForecastVersionId": None,
            "promotedAt": None,
        }
        scenarios.append(scenario)

    return PredictionModuleResult(
        module_key="scenario_builder",
        model_module="scenario_builder.build_scenarios",
        fallback_tier=fallback_tier,
        confidence_score=min(92.0, round((data_sufficiency_score * 0.55) + 18, 2)),
        data_sufficiency_score=data_sufficiency_score,
        confidence_label=confidence_label((data_sufficiency_score * 0.55) + 18),
        output={"items": scenarios},
        explanations=[
            {
                "key": "scenario_framework",
                "label": "Scenario framework",
                "impact": "base/upside/downside",
                "detail": "Scenarios vary quote level, delivery timing, usage, and win probability using explicit editable levers.",
            }
        ],
        warning_codes=[],
    )
