from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.modules.comparables.service import _round, _weighted_percentile
from app.modules.predictions.types import ActualsSummary, PredictionContext, PredictionModuleResult
from app.modules.predictions.utils import confidence_label


def _discipline_identity_maps(
    context: PredictionContext,
) -> tuple[dict[str, str], dict[str, dict[str, str | None]]]:
    code_to_id: dict[str, str] = {}
    labels_by_key: dict[str, dict[str, str | None]] = {}

    for project in context.projects_by_id.values():
        for link in project.disciplines:
            if link.discipline is None:
                continue
            code_to_id[link.discipline.code] = link.discipline_id
            labels_by_key[link.discipline_id] = {
                "code": link.discipline.code,
                "name": link.discipline.name,
            }

    for line in context.quote_line_items:
        if line.discipline_id is None or line.discipline is None:
            continue
        code_to_id[line.discipline.code] = line.discipline_id
        labels_by_key[line.discipline_id] = {
            "code": line.discipline.code,
            "name": line.discipline.name,
        }

    return code_to_id, labels_by_key


def _canonical_discipline_key(raw_key: object, code_to_id: dict[str, str]) -> str:
    text_key = str(raw_key)
    return code_to_id.get(text_key, text_key)


def _normalize_weights(values: dict[str, float]) -> dict[str, float]:
    filtered = {key: float(value) for key, value in values.items() if float(value) > 0}
    total = sum(filtered.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in filtered.items()}


def _distribute_amount(total_amount: float, weights: dict[str, float]) -> dict[str, float]:
    normalized_weights = _normalize_weights(weights)
    if total_amount <= 0 or not normalized_weights:
        return {key: 0.0 for key in weights}

    ordered = sorted(
        normalized_weights.items(),
        key=lambda item: (-item[1], item[0]),
    )
    distributed: dict[str, float] = {}
    remaining = _round(total_amount)
    for index, (key, weight) in enumerate(ordered):
        if index == len(ordered) - 1:
            distributed[key] = _round(remaining)
            break
        amount = _round(total_amount * weight)
        distributed[key] = amount
        remaining = _round(remaining - amount)
    return distributed


def _quote_amounts_by_discipline(
    context: PredictionContext,
    code_to_id: dict[str, str],
) -> dict[str, float]:
    quoted_by_discipline: dict[str, float] = defaultdict(float)
    for line in context.quote_line_items:
        if line.discipline_id is None:
            continue
        discipline_key = _canonical_discipline_key(
            line.discipline.code if line.discipline is not None else line.discipline_id,
            code_to_id,
        )
        quoted_by_discipline[discipline_key] += float(line.amount)
    return dict(quoted_by_discipline)


def _rounded_actual_costs_by_discipline(
    actuals: ActualsSummary,
    code_to_id: dict[str, str],
) -> dict[str, float]:
    costs_by_discipline: dict[str, float] = defaultdict(float)
    for discipline_id, amount in actuals.discipline_costs.items():
        costs_by_discipline[_canonical_discipline_key(discipline_id, code_to_id)] += float(amount)
    return {key: _round(value) for key, value in costs_by_discipline.items() if value > 0}


def build_spend_prediction(
    context: PredictionContext,
    *,
    quote_guidance: dict[str, Any] | None,
    fallback_tier: str,
    feature_snapshot: dict[str, Any],
) -> PredictionModuleResult:
    code_to_id, discipline_labels = _discipline_identity_maps(context)
    quoted_by_discipline = _quote_amounts_by_discipline(context, code_to_id)
    current_cost_by_discipline = _rounded_actual_costs_by_discipline(context.actuals, code_to_id)
    current_actual_cost = _round(float(context.actuals.current_cost_total or 0))

    total_cost_samples: list[dict[str, float | str]] = []
    share_samples_by_discipline: dict[str, list[dict[str, float | str]]] = defaultdict(list)

    for item in context.eligible_items:
        actuals = context.project_actuals_by_project_id.get(str(item["projectId"]))
        if actuals is None or actuals.current_cost_total <= 0:
            continue
        total_cost = _round(float(actuals.current_cost_total))
        total_cost_samples.append(
            {
                "projectId": str(item["projectId"]),
                "value": total_cost,
                "weight": float(item["similarityScore"]),
            }
        )
        for discipline_id, amount in _rounded_actual_costs_by_discipline(actuals, code_to_id).items():
            discipline_labels.setdefault(
                discipline_id,
                {"code": None, "name": discipline_id},
            )
            share_samples_by_discipline[discipline_id].append(
                {
                    "projectId": str(item["projectId"]),
                    "value": _round((amount / total_cost) * 100) if total_cost > 0 else 0,
                    "weight": float(item["similarityScore"]),
                }
            )

    comparable_cost_sample_size = len(total_cost_samples)
    predicted_total_cost: float | None = None
    basis = "insufficient_cost_history"
    if comparable_cost_sample_size >= 2:
        predicted_total_cost = max(
            current_actual_cost,
            _round(_weighted_percentile(total_cost_samples, 0.5)),
        )
        basis = "comparable_cost_history"
    elif current_actual_cost > 0:
        predicted_total_cost = current_actual_cost
        basis = "current_cost_actuals_only"

    if comparable_cost_sample_size >= 2:
        confidence_score = min(
            92.0,
            _round(
                46
                + (comparable_cost_sample_size * 8)
                + (10 if current_actual_cost > 0 else 0)
                + (float(feature_snapshot["dataSufficiencyScore"]) * 0.15)
            ),
        )
    elif current_actual_cost > 0:
        confidence_score = min(
            60.0,
            _round(36 + (float(feature_snapshot["dataSufficiencyScore"]) * 0.18)),
        )
    else:
        confidence_score = min(
            38.0,
            _round(float(feature_snapshot["dataSufficiencyScore"]) * 0.22),
        )

    discipline_keys = sorted(
        set(quoted_by_discipline)
        | set(current_cost_by_discipline)
        | set(share_samples_by_discipline)
    )
    quote_total = sum(float(value) for value in quoted_by_discipline.values())
    remaining_cost = (
        _round(max(0.0, float(predicted_total_cost) - current_actual_cost))
        if predicted_total_cost is not None
        else 0.0
    )
    weight_by_discipline: dict[str, float] = {}
    for discipline_key in discipline_keys:
        comparable_shares = share_samples_by_discipline.get(discipline_key, [])
        comparable_share = (
            _weighted_percentile(comparable_shares, 0.5) if comparable_shares else None
        )
        quote_share = (
            _round((float(quoted_by_discipline[discipline_key]) / quote_total) * 100)
            if quote_total > 0 and discipline_key in quoted_by_discipline
            else None
        )
        current_share = (
            _round((float(current_cost_by_discipline[discipline_key]) / current_actual_cost) * 100)
            if current_actual_cost > 0 and discipline_key in current_cost_by_discipline
            else None
        )
        seed_share = comparable_share
        if seed_share in (None, 0):
            seed_share = quote_share
        if seed_share in (None, 0):
            seed_share = current_share
        if seed_share not in (None, 0):
            weight_by_discipline[discipline_key] = float(seed_share)

    if not weight_by_discipline and current_cost_by_discipline:
        weight_by_discipline = {
            key: float(value) for key, value in current_cost_by_discipline.items()
        }

    remaining_by_discipline = _distribute_amount(remaining_cost, weight_by_discipline)

    discipline_rows: list[dict[str, Any]] = []
    if predicted_total_cost is not None or current_cost_by_discipline:
        for discipline_key in discipline_keys:
            current_cost = _round(float(current_cost_by_discipline.get(discipline_key, 0.0)))
            predicted_cost = (
                _round(current_cost + float(remaining_by_discipline.get(discipline_key, 0.0)))
                if predicted_total_cost is not None
                else current_cost
                if current_cost > 0
                else None
            )
            if predicted_cost is None or predicted_cost <= 0:
                continue
            sample_size = len(share_samples_by_discipline.get(discipline_key, []))
            row_confidence_score = (
                min(
                    88.0,
                    _round(
                        40
                        + (sample_size * 12)
                        + (8 if current_cost > 0 else 0)
                        + (6 if discipline_key in quoted_by_discipline else 0)
                    ),
                )
                if sample_size > 0
                else 55.0
                if current_cost > 0
                else 38.0
            )
            reasoning: list[str] = []
            if sample_size > 0:
                reasoning.append(
                    f"Cost-share history available in {sample_size} comparable project(s)."
                )
            else:
                reasoning.append(
                    "Comparable cost evidence is thin, so allocation falls back to quote structure or current actual mix."
                )
            if current_cost > 0:
                reasoning.append(
                    f"Current posted cost actuals already total {current_cost:.2f} for this discipline."
                )
            if discipline_key in quoted_by_discipline:
                reasoning.append(
                    f"Quote structure contributes {quoted_by_discipline[discipline_key]:.2f} of planned value for fallback weighting."
                )
            discipline_rows.append(
                {
                    "disciplineId": discipline_key,
                    "disciplineCode": discipline_labels.get(discipline_key, {}).get("code"),
                    "disciplineName": discipline_labels.get(discipline_key, {}).get("name"),
                    "currentActualCost": current_cost,
                    "predictedTotalCost": predicted_cost,
                    "predictedRemainingCost": _round(max(0.0, predicted_cost - current_cost)),
                    "costSharePct": (
                        _round((predicted_cost / float(predicted_total_cost)) * 100)
                        if predicted_total_cost not in (None, 0)
                        else _round((predicted_cost / current_actual_cost) * 100)
                        if current_actual_cost > 0
                        else 0.0
                    ),
                    "confidence": confidence_label(row_confidence_score),
                    "sampleSize": sample_size,
                    "reasoning": reasoning,
                }
            )

    discipline_rows.sort(
        key=lambda item: (
            -float(item["predictedTotalCost"] or 0),
            str(item["disciplineName"] or item["disciplineCode"] or item["disciplineId"]),
        )
    )

    if predicted_total_cost is not None and discipline_rows:
        predicted_total_cost = _round(
            sum(float(item["predictedTotalCost"] or 0) for item in discipline_rows)
        )

    predicted_remaining_cost = (
        _round(max(0.0, float(predicted_total_cost) - current_actual_cost))
        if predicted_total_cost is not None
        else None
    )
    quote_anchor = None
    if quote_guidance is not None:
        quote_anchor = quote_guidance.get("recommendedMedian") or quote_guidance.get("median")
    if quote_anchor is None:
        quote_anchor = context.target_snapshot.get("targetAmount")
    implied_margin_amount = (
        _round(float(quote_anchor) - float(predicted_total_cost))
        if quote_anchor not in (None, 0) and predicted_total_cost is not None
        else None
    )
    implied_margin_pct = (
        _round((float(implied_margin_amount) / float(quote_anchor)) * 100)
        if implied_margin_amount is not None and quote_anchor not in (None, 0)
        else None
    )

    summary = {
        "currentActualCost": current_actual_cost,
        "predictedTotalCost": predicted_total_cost,
        "predictedRemainingCost": predicted_remaining_cost,
        "impliedMarginAmount": implied_margin_amount,
        "impliedMarginPct": implied_margin_pct,
        "confidence": confidence_label(confidence_score),
        "confidenceScore": confidence_score,
        "fallbackTier": fallback_tier if comparable_cost_sample_size >= 2 else basis,
        "basis": basis,
        "disciplineSpend": discipline_rows,
    }
    explanations = [
        {
            "key": "spend_prediction_basis",
            "label": "Spend prediction basis",
            "impact": basis,
            "detail": (
                "Spend guidance uses comparable project cost actuals when enough history exists and "
                "never drops below posted target cost actuals."
            ),
        }
    ]
    warning_codes = ["spend_history_insufficient"] if comparable_cost_sample_size < 2 else []
    return PredictionModuleResult(
        module_key="spend_prediction",
        model_module="spend_prediction.build_spend_prediction",
        fallback_tier=fallback_tier if comparable_cost_sample_size >= 2 else basis,
        confidence_score=confidence_score,
        data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
        confidence_label=confidence_label(confidence_score),
        output=summary,
        explanations=explanations,
        warning_codes=warning_codes,
    )
