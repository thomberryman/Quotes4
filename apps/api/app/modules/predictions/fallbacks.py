from __future__ import annotations

from app.modules.predictions.types import PredictionContext, PredictionModuleResult
from app.modules.predictions.utils import classify_budget_band, confidence_label


def select_fallback_tier(
    context: PredictionContext, feature_snapshot: dict[str, object]
) -> PredictionModuleResult:
    quote_amount = (
        float(feature_snapshot["quoteAmount"])
        if feature_snapshot.get("quoteAmount") is not None
        else None
    )
    target_budget_band = classify_budget_band(quote_amount)
    target_client_id = context.target_snapshot.get("clientId")
    target_format = context.target_snapshot.get("projectFormatKey")

    high_similarity_count = len(
        [item for item in context.eligible_items if float(item["similarityScore"]) >= 75]
    )
    same_client_format_budget_count = 0
    same_project_type_count = 0
    for item in context.eligible_items:
        benchmark = item.get("benchmarkSummary") or {}
        project = context.projects_by_id.get(item["projectId"])
        project_client_id = None
        project_format = None
        if project is not None:
            client_party = next(
                (party for party in project.parties if party.role.value == "client" and party.is_primary),
                None,
            )
            project_client_id = client_party.company_id if client_party is not None else None
            if project.metadata_record is not None:
                project_format = (
                    project.metadata_record.project_format_key
                    or project.metadata_record.format_type
                )
        project_budget_band = classify_budget_band(
            float(benchmark["quotedAmount"]) if benchmark.get("quotedAmount") else None
        )
        if project_client_id == target_client_id and project_format == target_format:
            if target_budget_band is None or project_budget_band == target_budget_band:
                same_client_format_budget_count += 1
        if project_format == target_format:
            same_project_type_count += 1

    if context.actuals.current_revenue_total > 0:
        tier = "in_flight_actuals"
        evidence_strength = 85
    elif high_similarity_count >= 3:
        tier = "high_similarity_history"
        evidence_strength = 75
    elif same_client_format_budget_count >= 2:
        tier = "same_client_format_budget_band"
        evidence_strength = 62
    elif same_project_type_count >= 3:
        tier = "same_project_type_all_clients"
        evidence_strength = 54
    elif context.eligible_items:
        tier = "discipline_baseline"
        evidence_strength = 42
    else:
        tier = "system_default"
        evidence_strength = 25

    explanations = [
        {
            "key": "selected_tier",
            "label": "Fallback tier",
            "impact": tier,
            "detail": f"Selected {tier.replace('_', ' ')} based on currently available evidence.",
        },
        {
            "key": "high_similarity_count",
            "label": "High-similarity comparables",
            "impact": str(high_similarity_count),
            "detail": f"{high_similarity_count} eligible comparable projects scored at least 75% similarity.",
        },
        {
            "key": "same_client_format_budget_count",
            "label": "Client/format/budget matches",
            "impact": str(same_client_format_budget_count),
            "detail": (
                "Comparable count matching the same client, project format, and budget band."
            ),
        },
    ]

    output = {
        "selectedTier": tier,
        "highSimilarityCount": high_similarity_count,
        "sameClientFormatBudgetCount": same_client_format_budget_count,
        "sameProjectTypeCount": same_project_type_count,
        "evidenceSource": feature_snapshot.get("primaryEvidenceSource"),
    }
    return PredictionModuleResult(
        module_key="fallbacks",
        model_module="fallbacks.select_fallback_tier",
        fallback_tier=tier,
        confidence_score=round(evidence_strength, 2),
        data_sufficiency_score=round(float(feature_snapshot["dataSufficiencyScore"]), 2),
        confidence_label=confidence_label(evidence_strength),
        output=output,
        explanations=explanations,
        warning_codes=["fallback_system_default"] if tier == "system_default" else [],
    )
