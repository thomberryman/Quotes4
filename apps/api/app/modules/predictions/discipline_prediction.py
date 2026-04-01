from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.modules.comparables.service import _round, _weighted_percentile
from app.modules.predictions.types import PredictionContext, PredictionModuleResult
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


def build_discipline_predictions(
    context: PredictionContext,
    *,
    quote_guidance: dict[str, Any] | None,
    fallback_tier: str,
    feature_snapshot: dict[str, Any],
    discipline_code_filter: str | None,
) -> PredictionModuleResult:
    code_to_id, discipline_labels = _discipline_identity_maps(context)
    quoted_by_discipline: dict[str, float] = defaultdict(float)
    for line in context.quote_line_items:
        if line.discipline_id is None:
            continue
        discipline_key = _canonical_discipline_key(
            line.discipline.code if line.discipline is not None else line.discipline_id,
            code_to_id,
        )
        quoted_by_discipline[discipline_key] += float(line.amount)
        if line.discipline is not None:
            discipline_labels[discipline_key] = {
                "code": line.discipline.code,
                "name": line.discipline.name,
            }
    for link in context.project.disciplines:
        if link.discipline is not None:
            discipline_labels.setdefault(
                _canonical_discipline_key(link.discipline.code, code_to_id),
                {"code": link.discipline.code, "name": link.discipline.name},
            )

    sample_buckets: dict[str, dict[str, Any]] = {}
    eligible_count = len(context.eligible_items)
    for item in context.eligible_items:
        benchmark = item.get("benchmarkSummary") or {}
        total_quoted = float(benchmark.get("quotedAmount") or 0)
        if total_quoted <= 0:
            continue
        for summary in item.get("disciplineBenchmarkSummaries", []):
            discipline_id = _canonical_discipline_key(summary["disciplineId"], code_to_id)
            label = discipline_labels.setdefault(
                discipline_id,
                {
                    "code": (
                        str(summary["disciplineId"])
                        if str(summary["disciplineId"]) in code_to_id
                        else discipline_labels.get(discipline_id, {}).get("code")
                    ),
                    "name": summary.get("disciplineName"),
                },
            )
            if discipline_code_filter is not None and label.get("code") != discipline_code_filter:
                continue
            bucket = sample_buckets.setdefault(
                discipline_id,
                {
                    "projectIds": set(),
                    "shares": [],
                    "quoted": [],
                    "variances": [],
                },
            )
            quoted_amount = float(summary["quotedAmount"])
            bucket["projectIds"].add(item["projectId"])
            bucket["shares"].append(
                {
                    "projectId": item["projectId"],
                    "value": _round((quoted_amount / total_quoted) * 100),
                    "weight": item["similarityScore"],
                }
            )
            bucket["quoted"].append(
                {
                    "projectId": item["projectId"],
                    "value": quoted_amount,
                    "weight": item["similarityScore"],
                }
            )
            if summary.get("quoteToActualVariancePct") is not None:
                bucket["variances"].append(
                    {
                        "projectId": item["projectId"],
                        "value": float(summary["quoteToActualVariancePct"]),
                        "weight": item["similarityScore"],
                    }
                )

    quote_total = None
    if quote_guidance is not None and quote_guidance.get("recommendedMedian") is not None:
        quote_total = float(quote_guidance["recommendedMedian"])
    elif context.target_snapshot.get("targetAmount") is not None:
        quote_total = float(context.target_snapshot["targetAmount"])

    target_discipline_ids = {
        _canonical_discipline_key(link.discipline.code, code_to_id)
        if link.discipline is not None
        else link.discipline_id
        for link in context.project.disciplines
    }
    results: list[dict[str, Any]] = []
    for discipline_id in sorted(set(sample_buckets) | set(quoted_by_discipline) | target_discipline_ids):
        label = discipline_labels.get(discipline_id, {})
        if discipline_code_filter is not None and label.get("code") != discipline_code_filter:
            continue
        bucket = sample_buckets.get(discipline_id, {"projectIds": set(), "shares": [], "quoted": [], "variances": []})
        sample_size = len(bucket["projectIds"])
        share_pct = _weighted_percentile(bucket["shares"], 0.5) if bucket["shares"] else 0.0
        comparable_quote_amount = (
            _weighted_percentile(bucket["quoted"], 0.5) if bucket["quoted"] else None
        )
        quoted_amount = quoted_by_discipline.get(discipline_id)
        predicted_quote_amount = comparable_quote_amount
        if quote_total is not None and share_pct > 0:
            predicted_quote_amount = _round(quote_total * share_pct / 100)
        if quoted_amount is not None and predicted_quote_amount is None:
            predicted_quote_amount = _round(quoted_amount)

        historical_variance_pct = (
            _weighted_percentile(bucket["variances"], 0.5) if len(bucket["variances"]) >= 2 else None
        )
        actual_amount = context.actuals.discipline_revenue.get(discipline_id)
        predicted_actual_amount = predicted_quote_amount
        if predicted_actual_amount is not None and historical_variance_pct is not None:
            predicted_actual_amount = _round(
                predicted_quote_amount * (1 + historical_variance_pct / 100)
            )
        if actual_amount is not None and predicted_actual_amount is not None:
            predicted_actual_amount = _round(max(actual_amount, predicted_actual_amount))
        elif actual_amount is not None:
            predicted_actual_amount = _round(actual_amount)

        predicted_variance_pct = None
        anchor_amount = quoted_amount if quoted_amount not in (None, 0) else predicted_quote_amount
        if predicted_actual_amount is not None and anchor_amount not in (None, 0):
            predicted_variance_pct = _round(((predicted_actual_amount - anchor_amount) / anchor_amount) * 100)

        confidence_score = min(
            92.0,
            round(
                (sample_size * 12)
                + (10 if quoted_amount is not None else 0)
                + (12 if actual_amount is not None else 0)
                + (float(feature_snapshot["dataSufficiencyScore"]) * 0.25),
                2,
            ),
        )
        overrun_risk = "low"
        if predicted_variance_pct is not None and predicted_variance_pct >= 10:
            overrun_risk = "high"
        elif predicted_variance_pct is not None and predicted_variance_pct >= 4:
            overrun_risk = "medium"

        result = {
            "disciplineId": discipline_id,
            "disciplineCode": label.get("code"),
            "disciplineName": label.get("name"),
            "sampleSize": sample_size,
            "usageRatePct": _round((sample_size / eligible_count) * 100) if eligible_count else 0.0,
            "predictedSharePct": share_pct,
            "quotedAmount": _round(quoted_amount) if quoted_amount is not None else None,
            "predictedAmountLow": _round(predicted_quote_amount * 0.9) if predicted_quote_amount is not None else None,
            "predictedAmountMedian": _round(predicted_quote_amount) if predicted_quote_amount is not None else None,
            "predictedAmountHigh": _round(predicted_quote_amount * 1.1) if predicted_quote_amount is not None else None,
            "predictedActualAmount": predicted_actual_amount,
            "predictedVariancePct": predicted_variance_pct,
            "observedVarianceMedianPct": historical_variance_pct,
            "confidence": confidence_label(confidence_score),
            "confidenceScore": confidence_score,
            "dataSufficiencyScore": min(100.0, round((sample_size * 15) + (20 if quoted_amount is not None else 0), 2)),
            "fallbackTier": fallback_tier,
            "overrunRisk": overrun_risk,
            "isTargetDiscipline": discipline_id in target_discipline_ids,
            "comparableProjectIds": sorted(bucket["projectIds"]),
            "keyDrivers": [
                f"Usage rate {result_usage_rate:.1f}% in comparable work."
                if (result_usage_rate := (_round((sample_size / eligible_count) * 100) if eligible_count else 0.0))
                else "Limited comparable coverage.",
                f"Historical share median {share_pct:.1f}%."
                if share_pct
                else "Share defaults to quoted structure because history is sparse.",
                f"Stage actuals already posted at {actual_amount:.2f}."
                if actual_amount is not None
                else "No in-flight actuals for this discipline yet.",
            ],
            "reasoning": [
                f"Appears in {sample_size} eligible comparable project(s).",
                f"Weighted median discipline share is {share_pct:.1f}% of project value.",
            ],
        }
        if historical_variance_pct is not None:
            result["reasoning"].append(
                f"Complete-project benchmarks show a median variance of {historical_variance_pct:.1f}%."
            )
        results.append(result)

    results.sort(
        key=lambda item: (
            not bool(item["isTargetDiscipline"]),
            -float(item["predictedAmountMedian"] or 0),
            -float(item["usageRatePct"]),
            str(item["disciplineName"] or item["disciplineCode"] or item["disciplineId"]),
        )
    )

    explanations = [
        {
            "key": "discipline_count",
            "label": "Disciplines covered",
            "impact": str(len(results)),
            "detail": "Discipline predictions blend target quote structure, comparable benchmark shares, and stage actuals where available.",
        }
    ]
    return PredictionModuleResult(
        module_key="discipline_prediction",
        model_module="discipline_prediction.build_discipline_predictions",
        fallback_tier=fallback_tier,
        confidence_score=min(100.0, round(sum(float(item["confidenceScore"] or 0) for item in results) / max(len(results), 1), 2)),
        data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
        confidence_label=confidence_label(float(feature_snapshot["dataSufficiencyScore"])),
        output={"items": results},
        explanations=explanations,
        warning_codes=["discipline_sparse_history"] if len(results) <= 2 else [],
    )
