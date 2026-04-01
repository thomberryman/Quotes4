from __future__ import annotations

from typing import Any

from app.modules.predictions.types import PredictionContext, PredictionModuleResult
from app.modules.predictions.utils import confidence_label


def build_explanations(
    context: PredictionContext,
    *,
    feature_snapshot: dict[str, Any],
    fallback_tier: str,
    module_results: list[PredictionModuleResult],
) -> PredictionModuleResult:
    top_comparables = []
    for index, item in enumerate(context.comparable_items[:5], start=1):
        evidence = [
            {
                "key": factor["factorKey"],
                "label": factor["label"],
                "impact": f"{float(factor['awardedPoints']):.1f}/{int(factor['weight'])}",
                "detail": factor["detail"],
            }
            for factor in item.get("matchedFactors", [])[:4]
        ]
        top_comparables.append(
            {
                "projectId": item.get("projectId"),
                "projectName": item["projectName"],
                "similarityScore": float(item["similarityScore"]),
                "strength": item["strength"],
                "selectionState": item["selectionState"],
                "isPrimary": index <= 3,
                "evidence": evidence,
            }
        )

    run_explanations = [
        {
            "key": "maturity_stage",
            "label": "Maturity stage",
            "impact": str(feature_snapshot["maturityStage"]),
            "detail": "Prediction behaviour changes as the project matures from sparse opportunity through in-flight work.",
        },
        {
            "key": "fallback_tier",
            "label": "Fallback tier",
            "impact": fallback_tier,
            "detail": "Every module records which evidence fallback tier it used so outputs remain auditable.",
        },
        {
            "key": "module_count",
            "label": "Modules executed",
            "impact": str(len(module_results)),
            "detail": "Predictions are built from modular deterministic services rather than a monolithic model.",
        },
    ]

    return PredictionModuleResult(
        module_key="explanations",
        model_module="explanations.build_explanations",
        fallback_tier=fallback_tier,
        confidence_score=min(95.0, round(float(feature_snapshot["confidenceScore"]), 2)),
        data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
        confidence_label=confidence_label(float(feature_snapshot["confidenceScore"])),
        output={"topComparables": top_comparables, "runExplanations": run_explanations},
        explanations=run_explanations,
        warning_codes=[],
    )
