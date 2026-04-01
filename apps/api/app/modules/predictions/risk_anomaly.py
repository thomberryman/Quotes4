from __future__ import annotations

from statistics import median
from typing import Any

from app.modules.predictions.types import PredictionContext, PredictionModuleResult
from app.modules.predictions.utils import confidence_label, weighted_band


def _risk_level(flags: list[dict[str, Any]]) -> str:
    if any(flag["severity"] == "high" for flag in flags):
        return "high"
    if any(flag["severity"] in {"warning", "medium"} for flag in flags):
        return "medium"
    return "low"


def build_risk_and_anomalies(
    context: PredictionContext,
    *,
    quote_guidance: dict[str, Any] | None,
    discipline_predictions: list[dict[str, Any]],
    monthly_revenue_spread: list[dict[str, Any]],
    fallback_tier: str,
    feature_snapshot: dict[str, Any],
    comparable_risk_signals: list[dict[str, Any]],
) -> PredictionModuleResult:
    flags: list[dict[str, Any]] = []
    risk_signals = list(comparable_risk_signals)

    actual_variance_values = [
        {
            "projectId": item["projectId"],
            "value": item["benchmarkSummary"]["quoteToActualVariancePct"],
            "weight": item["similarityScore"],
        }
        for item in context.eligible_items
        if item["benchmarkSummary"].get("actualsStatus") == "complete"
        and item["benchmarkSummary"].get("quoteToActualVariancePct") is not None
    ]
    variance_band = weighted_band(actual_variance_values)
    if variance_band is not None and variance_band["median"] >= 5:
        flags.append(
            {
                "key": "historical_overrun_pattern",
                "severity": "high" if variance_band["median"] >= 10 else "warning",
                "title": "Historical overrun pattern",
                "detail": f"Comparable complete projects landed at a weighted median {variance_band['median']}% above quote.",
                "confidence": confidence_label(72.0),
                "comparableProjectIds": variance_band["comparableProjectIds"],
                "reasoning": [
                    f"Observed variance band spans {variance_band['low']}% to {variance_band['high']}%.",
                    "Only complete projects with approved actuals were included.",
                ],
            }
        )

    if quote_guidance is not None and quote_guidance.get("quotePosition") == "underquoted":
        flags.append(
            {
                "key": "underquoted_scope",
                "severity": "high" if quote_guidance.get("confidence") == "high" else "warning",
                "title": "Likely underquoted",
                "detail": "The current quote sits below the recommended range for comparable evidence and current maturity.",
                "confidence": quote_guidance["confidence"],
                "comparableProjectIds": quote_guidance["comparableProjectIds"],
                "reasoning": quote_guidance["reasoning"],
            }
        )

    target_duration_weeks = (
        int(context.project.metadata_record.duration_weeks)
        if context.project.metadata_record is not None
        and context.project.metadata_record.duration_weeks is not None
        else None
    )
    comparable_duration_values = [
        int(project.metadata_record.duration_weeks)
        for item in context.eligible_items
        if (project := context.projects_by_id.get(item["projectId"])) is not None
        and project.metadata_record is not None
        and project.metadata_record.duration_weeks is not None
    ]
    if (
        target_duration_weeks is not None
        and comparable_duration_values
        and target_duration_weeks < (median(comparable_duration_values) * 0.85)
    ):
        median_duration_weeks = float(median(comparable_duration_values))
        flags.append(
            {
                "key": "schedule_compression",
                "severity": "warning",
                "title": "Schedule compression",
                "detail": (
                    f"Target duration is {target_duration_weeks} week(s) versus a "
                    f"{median_duration_weeks:.1f}-week comparable median, increasing delivery pressure."
                ),
                "confidence": "medium",
                "comparableProjectIds": [item["projectId"] for item in context.eligible_items],
                "reasoning": [
                    "Comparable projects with similar commercial shape generally ran for longer durations.",
                    "Compressed schedules typically amplify change-order, review, and overrun risk.",
                ],
            }
        )

    pricing_context = (
        context.target_quote_version.pricing_context_json
        if context.target_quote_version is not None and context.target_quote_version.pricing_context_json
        else {}
    )
    discount_pct = pricing_context.get("discountPercent")
    if isinstance(discount_pct, (int, float)) and float(discount_pct) >= 15:
        flags.append(
            {
                "key": "unusual_discounting",
                "severity": "warning",
                "title": "Unusual discounting",
                "detail": f"Discounting is currently {float(discount_pct):.1f}%, which is materially above typical quoting tolerance.",
                "confidence": "medium",
                "comparableProjectIds": [],
                "reasoning": ["Large discounts can distort quote-to-actual variance and reduce commercial resilience."],
            }
        )

    third_party_share = context.actuals.third_party_cost_share_pct
    if third_party_share is None:
        raw_share = pricing_context.get("thirdPartyCostPercent")
        if isinstance(raw_share, (int, float)):
            third_party_share = float(raw_share)
    if third_party_share is not None and third_party_share >= 35:
        flags.append(
            {
                "key": "high_third_party_exposure",
                "severity": "warning",
                "title": "High third-party exposure",
                "detail": f"Third-party costs are running or planned at {third_party_share:.1f}% of tracked commercial value.",
                "confidence": "medium",
                "comparableProjectIds": [],
                "reasoning": ["Vendor-heavy delivery reduces internal recovery margin and can amplify schedule risk."],
            }
        )

    if discipline_predictions:
        top_two_share = sum(float(item["predictedSharePct"]) for item in discipline_predictions[:2])
        if top_two_share >= 80:
            flags.append(
                {
                    "key": "atypical_quote_composition",
                    "severity": "warning",
                    "title": "Atypical quote composition",
                    "detail": f"The top two disciplines account for {top_two_share:.1f}% of predicted value, increasing concentration risk.",
                    "confidence": discipline_predictions[0]["confidence"],
                    "comparableProjectIds": discipline_predictions[0]["comparableProjectIds"],
                    "reasoning": ["Heavy concentration in a narrow set of disciplines increases exposure to slippage or reruns."],
                }
            )

    if monthly_revenue_spread:
        first_month_share = float(monthly_revenue_spread[0]["medianSharePct"])
        last_month_share = float(monthly_revenue_spread[-1]["medianSharePct"])
        if abs(first_month_share - last_month_share) >= 35 and monthly_revenue_spread[0].get("spreadProfile") == "even":
            flags.append(
                {
                    "key": "unrealistic_monthly_shape",
                    "severity": "warning",
                    "title": "Unrealistic monthly spread",
                    "detail": "The projected monthly shape is much more skewed than the current project profile suggests.",
                    "confidence": "medium",
                    "comparableProjectIds": monthly_revenue_spread[0]["comparableProjectIds"],
                    "reasoning": ["Monthly concentration is materially different from the inferred target spread profile."],
                }
            )

    if context.actuals.current_revenue_total > 0 and context.project.end_date is not None:
        latest_actual_month = max(context.actuals.monthly_revenue) if context.actuals.monthly_revenue else None
        if latest_actual_month is not None:
            risk_signals.append(
                {
                    "key": "in_flight_actuals_present",
                    "severity": "info",
                    "detail": f"Stage 4 reforecasting is anchored by actual revenue through {latest_actual_month}.",
                }
            )

    if float(feature_snapshot["dataSufficiencyScore"]) < 45:
        flags.append(
            {
                "key": "sparse_data_warning",
                "severity": "warning",
                "title": "Sparse data",
                "detail": "Prediction quality is constrained by missing inputs or thin historical evidence.",
                "confidence": "low",
                "comparableProjectIds": [],
                "reasoning": ["Low data sufficiency means the system is relying on broader fallbacks than normal."],
            }
        )

    output = {
        "overrunRisk": {"level": _risk_level(flags), "flags": flags},
        "riskSignals": risk_signals,
    }
    confidence_score = min(92.0, round((float(feature_snapshot["dataSufficiencyScore"]) * 0.5) + (len(flags) * 5), 2))
    return PredictionModuleResult(
        module_key="risk_anomaly",
        model_module="risk_anomaly.build_risk_and_anomalies",
        fallback_tier=fallback_tier,
        confidence_score=confidence_score,
        data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
        confidence_label=confidence_label(confidence_score),
        output=output,
        explanations=[
            {
                "key": "risk_flag_count",
                "label": "Risk flags",
                "impact": str(len(flags)),
                "detail": "Risk scoring combines overrun history, commercial context, schedule shape, and sparse-data warnings.",
            }
        ],
        warning_codes=["risk_flags_present"] if flags else [],
    )
