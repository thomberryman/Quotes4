from __future__ import annotations

from typing import Any

from app.models.enums import ProjectStatus
from app.modules.predictions.types import PredictionContext, PredictionModuleResult
from app.modules.predictions.utils import clamp, confidence_label


PIPELINE_STAGE_BASE = {
    "lead": 22.0,
    "budgetary": 32.0,
    "estimate": 38.0,
    "quoted": 46.0,
    "submitted": 56.0,
    "shortlist": 68.0,
    "final_bid": 62.0,
}


def _resolved_outcome(project_status: str) -> int | None:
    if project_status in {"awarded", "active", "complete"}:
        return 1
    if project_status == "lost":
        return 0
    return None


def build_win_probability(
    context: PredictionContext,
    *,
    quote_guidance: dict[str, Any] | None,
    fallback_tier: str,
    feature_snapshot: dict[str, Any],
) -> PredictionModuleResult:
    project_status = context.project.status.value
    resolved_outcome = _resolved_outcome(project_status)
    if resolved_outcome is not None:
        probability_pct = 100.0 if resolved_outcome == 1 else 0.0
        key_factors = [
            {
                "key": "resolved_status",
                "label": "Resolved status",
                "effect": 0.0,
                "detail": "The project outcome is already known, so win probability is fully resolved.",
            }
        ]
        return PredictionModuleResult(
            module_key="win_probability",
            model_module="win_probability.build_win_probability",
            fallback_tier=fallback_tier,
            confidence_score=100.0,
            data_sufficiency_score=100.0,
            confidence_label="high",
            output={
                "probabilityPct": probability_pct,
                "probabilityBand": "resolved",
                "confidence": "high",
                "confidenceScore": 100.0,
                "fallbackTier": fallback_tier,
                "keyFactors": key_factors,
                "overrideStatus": None,
                "reasoning": ["The project status already resolves the commercial outcome."],
            },
            explanations=key_factors,
            warning_codes=[],
        )

    score = PIPELINE_STAGE_BASE.get(context.project.pipeline_stage_key or "", 42.0)
    factors: list[dict[str, Any]] = []

    target_client_id = context.target_snapshot.get("clientId")
    comparable_history = [
        project
        for project in context.projects_by_id.values()
        if project.id != context.project.id and _resolved_outcome(project.status.value) is not None
    ]
    same_client_history = []
    for project in comparable_history:
        for party in project.parties:
            if party.role.value == "client" and party.company_id == target_client_id:
                same_client_history.append(project)
                break
    if same_client_history:
        wins = sum(1 for project in same_client_history if _resolved_outcome(project.status.value) == 1)
        same_client_rate = (wins / len(same_client_history)) * 100
        delta = (same_client_rate - 50) * 0.18
        score += delta
        factors.append(
            {
                "key": "same_client_history",
                "label": "Client history",
                "effect": round(delta, 2),
                "detail": f"Historical same-client win rate is {same_client_rate:.1f}% across {len(same_client_history)} opportunity records.",
            }
        )

    if context.project.strategic_account_flag:
        score += 6.0
        factors.append(
            {
                "key": "strategic_account",
                "label": "Strategic account",
                "effect": 6.0,
                "detail": "Strategic accounts receive a positive weight because commercial flexibility is typically higher.",
            }
        )

    if quote_guidance is not None and quote_guidance.get("quotePosition") == "underquoted":
        score += 3.0
        factors.append(
            {
                "key": "pricing_position",
                "label": "Pricing position",
                "effect": 3.0,
                "detail": "The working quote sits below the recommended range, which can improve win likelihood but may raise margin risk.",
            }
        )
    elif quote_guidance is not None and quote_guidance.get("quotePosition") == "overquoted":
        score -= 7.0
        factors.append(
            {
                "key": "pricing_position",
                "label": "Pricing position",
                "effect": -7.0,
                "detail": "The working quote is above the recommended range, which historically reduces win probability.",
            }
        )

    quote_revision_count = 0
    if context.project.quotes:
        quote_revision_count = max((len(quote.versions) for quote in context.project.quotes), default=0)
    if quote_revision_count >= 3:
        score += 2.0
        factors.append(
            {
                "key": "revision_activity",
                "label": "Revision activity",
                "effect": 2.0,
                "detail": "Active quote revision usually indicates a live commercial dialogue.",
            }
        )

    if feature_snapshot.get("currentMonthCount") and context.project.metadata_record and context.project.metadata_record.duration_weeks:
        duration_weeks = int(context.project.metadata_record.duration_weeks)
        if duration_weeks <= 4:
            score -= 4.0
            factors.append(
                {
                    "key": "timeline_realism",
                    "label": "Timeline realism",
                    "effect": -4.0,
                    "detail": "Short schedules reduce operational recovery margin and can weaken bid confidence.",
                }
            )

    probability_pct = round(clamp(score, 5.0, 95.0), 2)
    confidence_score = round(
        min(
            92.0,
            (float(feature_snapshot["dataSufficiencyScore"]) * 0.45)
            + (len(comparable_history) * 4)
            + (len(factors) * 5),
        ),
        2,
    )
    if probability_pct >= 70:
        band = "high"
    elif probability_pct >= 45:
        band = "medium"
    else:
        band = "low"

    output = {
        "probabilityPct": probability_pct,
        "probabilityBand": band,
        "confidence": confidence_label(confidence_score),
        "confidenceScore": confidence_score,
        "fallbackTier": fallback_tier,
        "keyFactors": factors,
        "overrideStatus": None,
        "reasoning": [
            "Win probability uses transparent weighted commercial factors rather than an opaque model.",
            "Relationship history, pricing position, pipeline stage, and timeline realism are combined into a bounded score.",
        ],
    }
    return PredictionModuleResult(
        module_key="win_probability",
        model_module="win_probability.build_win_probability",
        fallback_tier=fallback_tier,
        confidence_score=confidence_score,
        data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
        confidence_label=confidence_label(confidence_score),
        output=output,
        explanations=factors,
        warning_codes=["win_probability_sparse_history"] if len(comparable_history) < 3 else [],
    )
