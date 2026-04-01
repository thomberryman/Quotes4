from __future__ import annotations

from typing import Any

from app.models.enums import ProjectStatus
from app.modules.predictions.types import PredictionContext, PredictionModuleResult
from app.modules.predictions.utils import (
    amount_or_none,
    classify_budget_band,
    confidence_label,
    month_count,
)


def determine_maturity_stage(context: PredictionContext) -> str:
    has_actuals = context.actuals.current_revenue_total > 0
    has_quote_structure = context.target_quote_version is not None and len(context.quote_line_items) > 0
    has_schedule = bool(context.schedule_ranges) or (
        context.project.start_date is not None and context.project.end_date is not None
    )
    has_forecast = context.current_forecast_version is not None
    if has_actuals:
        return "stage_4"
    if context.project.status in {ProjectStatus.awarded, ProjectStatus.active, ProjectStatus.complete} or has_forecast:
        return "stage_3"
    if has_quote_structure or has_schedule or context.project.disciplines:
        return "stage_2"
    return "stage_1"


def build_feature_snapshot(context: PredictionContext) -> tuple[PredictionModuleResult, dict[str, Any]]:
    metadata_record = context.project.metadata_record
    pricing_context = (
        context.target_quote_version.pricing_context_json
        if context.target_quote_version is not None
        else None
    ) or {}
    quote_amount = amount_or_none(context.target_snapshot.get("targetAmount"))
    discipline_count = len(
        {
            line.discipline_id
            for line in context.quote_line_items
            if line.discipline_id is not None
        }
        | {link.discipline_id for link in context.project.disciplines}
    )
    comparable_count = len(context.eligible_items)
    actual_history_count = len(
        [
            item
            for item in context.eligible_items
            if item["benchmarkSummary"].get("actualsStatus") == "complete"
            and item["benchmarkSummary"].get("quoteToActualVariancePct") is not None
        ]
    )
    current_month_count = month_count(
        context.project.start_date,
        context.project.end_date,
        int(metadata_record.duration_weeks) if metadata_record and metadata_record.duration_weeks else None,
    )
    maturity_stage = determine_maturity_stage(context)

    missing_critical_inputs: list[str] = []
    if quote_amount is None:
        missing_critical_inputs.append("quote_or_budget_amount")
    if context.target_snapshot.get("clientId") is None:
        missing_critical_inputs.append("primary_client")
    if not context.target_snapshot.get("projectFormatKey"):
        missing_critical_inputs.append("project_format_key")
    if discipline_count == 0:
        missing_critical_inputs.append("disciplines")
    if current_month_count is None:
        missing_critical_inputs.append("schedule_dates")

    readiness_components = [
        18 if quote_amount is not None else 0,
        10 if context.target_snapshot.get("clientId") is not None else 0,
        10 if context.target_snapshot.get("projectFormatKey") else 0,
        10 if current_month_count is not None else 0,
        8 if metadata_record and metadata_record.duration_weeks else 0,
        8 if metadata_record and metadata_record.episode_count else 0,
        10 if discipline_count > 0 else 0,
        10 if len(context.quote_line_items) > 0 else 0,
        8 if pricing_context else 0,
        8 if context.actuals.current_revenue_total > 0 else 0,
    ]
    feature_readiness_score = round(sum(readiness_components), 2)

    sufficiency_components = [
        min(20, comparable_count * 4),
        min(20, actual_history_count * 5),
        min(15, discipline_count * 4),
        15 if current_month_count is not None else 0,
        15 if len(context.quote_line_items) > 0 else 0,
        15 if context.actuals.current_revenue_total > 0 else 0,
    ]
    data_sufficiency_score = round(sum(sufficiency_components), 2)
    confidence_score = round((feature_readiness_score * 0.45) + (data_sufficiency_score * 0.55), 2)
    primary_evidence_source = (
        "partial_actuals"
        if context.actuals.current_revenue_total > 0
        else "comparables"
        if comparable_count >= 3
        else "project_specific"
        if len(context.quote_line_items) > 0
        else "defaults"
    )

    snapshot: dict[str, Any] = {
        "projectId": context.project.id,
        "projectName": context.project.name,
        "projectStatus": context.project.status.value,
        "maturityStage": maturity_stage,
        "pipelineStageKey": context.project.pipeline_stage_key,
        "quoteCurrencyCode": context.target_snapshot.get("quoteCurrencyCode"),
        "clientId": context.target_snapshot.get("clientId"),
        "clientName": context.target_snapshot.get("clientName"),
        "projectFormatKey": context.target_snapshot.get("projectFormatKey"),
        "budgetBand": classify_budget_band(quote_amount),
        "quoteAmount": quote_amount,
        "quoteVersionId": context.target_quote_version.id if context.target_quote_version else None,
        "disciplineCount": discipline_count,
        "lineItemCount": len(context.quote_line_items),
        "currentMonthCount": current_month_count,
        "comparableCount": comparable_count,
        "actualHistoryCount": actual_history_count,
        "currentRevenueActuals": context.actuals.current_revenue_total,
        "currentCostActuals": context.actuals.current_cost_total,
        "thirdPartyCostSharePct": context.actuals.third_party_cost_share_pct,
        "featureReadinessScore": feature_readiness_score,
        "dataSufficiencyScore": data_sufficiency_score,
        "confidenceScore": confidence_score,
        "primaryEvidenceSource": primary_evidence_source,
        "missingCriticalInputs": missing_critical_inputs,
        "pricingContext": pricing_context,
        "metadata": metadata_record.metadata_json if metadata_record is not None else None,
    }
    explanations = [
        {
            "key": "maturity_stage",
            "label": "Maturity stage",
            "impact": maturity_stage,
            "detail": f"Prediction maturity is currently {maturity_stage.replace('_', ' ')}.",
        },
        {
            "key": "comparable_count",
            "label": "Comparable coverage",
            "impact": str(comparable_count),
            "detail": f"{comparable_count} eligible comparable projects are available for prediction.",
        },
    ]
    if context.actuals.current_revenue_total > 0:
        explanations.append(
            {
                "key": "partial_actuals",
                "label": "In-flight actuals",
                "impact": f"{context.actuals.current_revenue_total:.2f}",
                "detail": "Partial actuals are available and will anchor stage 4 reforecasting.",
            }
        )

    result = PredictionModuleResult(
        module_key="feature_snapshot",
        model_module="feature_snapshot.build_feature_snapshot",
        fallback_tier="system_default",
        confidence_score=confidence_score,
        data_sufficiency_score=data_sufficiency_score,
        confidence_label=confidence_label(confidence_score),
        output=snapshot,
        explanations=explanations,
        warning_codes=["missing_critical_inputs"] if missing_critical_inputs else [],
    )
    return result, snapshot
