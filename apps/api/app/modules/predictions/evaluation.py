from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.modules.predictions.types import PredictionContext, PredictionModuleResult
from app.modules.predictions.utils import confidence_label


def build_evaluations(
    context: PredictionContext,
    *,
    quote_guidance: dict[str, Any] | None,
    win_probability: dict[str, Any] | None,
    scenarios: list[dict[str, Any]],
    data_sufficiency_score: float,
) -> PredictionModuleResult:
    items: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    if quote_guidance is not None and context.target_snapshot.get("targetAmount") is not None:
        current_quote = float(context.target_snapshot["targetAmount"])
        recommended = quote_guidance.get("recommendedMedian")
        if recommended is not None:
            items.append(
                {
                    "moduleKey": "quote_guidance",
                    "scenarioKey": None,
                    "metricKey": "suggested_vs_current_quote",
                    "predictedValue": {"recommendedMedian": float(recommended)},
                    "actualValue": {"currentQuote": current_quote},
                    "errorValue": round(float(recommended) - current_quote, 2),
                    "calibrationBucket": None,
                    "note": "Tracks the working quote against the system recommendation.",
                    "outcomeRecordedAt": now,
                }
            )

    if win_probability is not None and context.project.status.value in {"awarded", "active", "complete", "lost"}:
        actual_outcome = 100.0 if context.project.status.value != "lost" else 0.0
        probability_pct = float(win_probability["probabilityPct"])
        items.append(
            {
                "moduleKey": "win_probability",
                "scenarioKey": None,
                "metricKey": "win_probability_outcome",
                "predictedValue": {"probabilityPct": probability_pct},
                "actualValue": {"outcomePct": actual_outcome},
                "errorValue": round(abs(probability_pct - actual_outcome), 2),
                "calibrationBucket": win_probability["probabilityBand"],
                "note": "Tracks resolved commercial outcome against the predicted win probability.",
                "outcomeRecordedAt": now,
            }
        )

    if context.project.benchmark_summary is not None and context.project.benchmark_summary.actual_amount is not None:
        base_scenario = next((scenario for scenario in scenarios if scenario["scenarioKey"] == "base"), None)
        if base_scenario is not None:
            items.append(
                {
                    "moduleKey": "scenario_builder",
                    "scenarioKey": "base",
                    "metricKey": "projected_revenue_vs_actual",
                    "predictedValue": {"projectedTotalRevenue": base_scenario["projectedTotalRevenue"]},
                    "actualValue": {"actualRevenue": float(context.project.benchmark_summary.actual_amount)},
                    "errorValue": round(
                        float(base_scenario["projectedTotalRevenue"])
                        - float(context.project.benchmark_summary.actual_amount),
                        2,
                    ),
                    "calibrationBucket": None,
                    "note": "Compares the base-case revenue projection to complete benchmark actuals when they exist.",
                    "outcomeRecordedAt": now,
                }
            )

    return PredictionModuleResult(
        module_key="evaluation",
        model_module="evaluation.build_evaluations",
        fallback_tier="system_default",
        confidence_score=min(88.0, round((data_sufficiency_score * 0.35) + (len(items) * 10), 2)),
        data_sufficiency_score=data_sufficiency_score,
        confidence_label=confidence_label((data_sufficiency_score * 0.35) + (len(items) * 10)),
        output={"items": items},
        explanations=[
            {
                "key": "evaluation_records",
                "label": "Evaluation records",
                "impact": str(len(items)),
                "detail": "Evaluation foundations track available predicted-versus-realized comparisons without requiring an external ML pipeline.",
            }
        ],
        warning_codes=[],
    )
