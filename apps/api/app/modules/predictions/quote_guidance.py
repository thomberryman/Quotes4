from __future__ import annotations

from typing import Any

from app.modules.comparables.service import _round, _weighted_range
from app.modules.predictions.types import PredictionContext, PredictionModuleResult
from app.modules.predictions.utils import confidence_label


def build_quote_guidance(
    context: PredictionContext,
    *,
    comparable_quote_range: dict[str, Any] | None,
    actual_informed_quote_range: dict[str, Any] | None,
    fallback_tier: str,
    feature_snapshot: dict[str, Any],
) -> PredictionModuleResult:
    quoted_amount = float(context.target_snapshot["targetAmount"]) if context.target_snapshot.get("targetAmount") else None
    maturity_stage = str(feature_snapshot["maturityStage"])
    confidence_score = min(
        92.0,
        round(
            (float(feature_snapshot["dataSufficiencyScore"]) * 0.55)
            + (float(feature_snapshot["featureReadinessScore"]) * 0.35)
            + (10 if actual_informed_quote_range is not None else 0),
            2,
        ),
    )

    if actual_informed_quote_range is not None:
        base_range = actual_informed_quote_range
        basis = "actual_informed_history"
        reasoning = [
            "Starts from weighted comparable quote history for similar completed or won work.",
            (
                "Applies observed quote-to-actual uplift from complete benchmark history to "
                "produce a commercially safer recommendation."
            ),
        ]
    elif comparable_quote_range is not None:
        base_range = comparable_quote_range
        basis = "comparable_quote_history"
        reasoning = [
            "Uses weighted comparable quote history because actual-informed uplift is still thin.",
        ]
    elif quoted_amount is not None:
        base_range = {
            "low": quoted_amount,
            "median": quoted_amount,
            "high": quoted_amount,
            "currencyCode": context.target_snapshot["quoteCurrencyCode"],
            "sampleSize": 0,
            "comparableProjectIds": [],
            "methodology": "target_amount_anchor",
        }
        basis = "target_amount_anchor"
        reasoning = [
            "Comparable history is too thin, so guidance is temporarily anchored to the current target amount.",
        ]
    else:
        base_range = None
        basis = "no_numeric_basis"
        reasoning = ["No quote or budget anchor was available."]

    output: dict[str, Any]
    if base_range is None:
        output = {
            "comparableQuoteRange": comparable_quote_range,
            "actualInformedQuoteRange": actual_informed_quote_range,
            "basis": basis,
            "confidence": "low",
            "low": 0.0,
            "median": 0.0,
            "high": 0.0,
            "currencyCode": context.target_snapshot["quoteCurrencyCode"],
            "sampleSize": 0,
            "comparableProjectIds": [],
            "methodology": "insufficient_data",
            "appliedVarianceMedianPct": None,
            "quotedAmount": quoted_amount,
            "recommendedLow": None,
            "recommendedMedian": None,
            "recommendedHigh": None,
            "quotePosition": None,
            "omittedDisciplineIds": [],
            "acceptanceStatus": None,
            "reasoning": reasoning,
        }
    else:
        contingency_pct = 0.0
        if actual_informed_quote_range is not None:
            contingency_pct += max(0.0, float(actual_informed_quote_range["varianceMedianPct"])) * 0.5
        if maturity_stage in {"stage_1", "stage_2"}:
            contingency_pct += 3.0
        if confidence_score < 55:
            contingency_pct += 4.0
        recommended_low = _round(float(base_range["low"]))
        recommended_median = _round(float(base_range["median"]) * (1 + contingency_pct / 100))
        recommended_high = _round(float(base_range["high"]) * (1 + contingency_pct / 100))

        quote_position = None
        if quoted_amount is not None:
            if quoted_amount < recommended_low * 0.97:
                quote_position = "underquoted"
            elif quoted_amount > recommended_high * 1.03:
                quote_position = "overquoted"
            else:
                quote_position = "within_range"

        output = {
            "comparableQuoteRange": comparable_quote_range,
            "actualInformedQuoteRange": actual_informed_quote_range,
            "basis": basis,
            "confidence": confidence_label(confidence_score),
            "low": _round(float(base_range["low"])),
            "median": _round(float(base_range["median"])),
            "high": _round(float(base_range["high"])),
            "currencyCode": base_range["currencyCode"],
            "sampleSize": int(base_range["sampleSize"]),
            "comparableProjectIds": list(base_range["comparableProjectIds"]),
            "methodology": str(base_range["methodology"]),
            "appliedVarianceMedianPct": (
                float(actual_informed_quote_range["varianceMedianPct"])
                if actual_informed_quote_range is not None
                else None
            ),
            "quotedAmount": quoted_amount,
            "recommendedLow": recommended_low,
            "recommendedMedian": recommended_median,
            "recommendedHigh": recommended_high,
            "quotePosition": quote_position,
            "omittedDisciplineIds": [],
            "acceptanceStatus": None,
            "reasoning": reasoning
            + [
                f"Fallback tier for this quote recommendation is {fallback_tier.replace('_', ' ')}.",
                f"Contingency uplift applied to the median recommendation is {contingency_pct:.1f}%.",
            ],
        }

    explanations = [
        {
            "key": "quote_basis",
            "label": "Quote basis",
            "impact": basis,
            "detail": f"Primary quote basis is {basis.replace('_', ' ')}.",
        },
        {
            "key": "current_quote_position",
            "label": "Current quote position",
            "impact": output.get("quotePosition") or "unquoted",
            "detail": "Shows whether the working quote sits below, within, or above the recommended band.",
        },
    ]
    return PredictionModuleResult(
        module_key="quote_guidance",
        model_module="quote_guidance.build_quote_guidance",
        fallback_tier=fallback_tier,
        confidence_score=confidence_score,
        data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
        confidence_label=confidence_label(confidence_score),
        output=output,
        explanations=explanations,
        warning_codes=["quote_anchor_only"] if basis == "target_amount_anchor" else [],
    )


def comparable_discipline_range(
    values: list[dict[str, float | str]],
    currency_code: str,
) -> dict[str, Any] | None:
    return _weighted_range(values, currency_code)
