from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.datetimes import same_timestamp
from app.core.errors import ApiProblemException
from app.models import (
    Forecast,
    ForecastLine,
    ForecastVersion,
    MappedActual,
    PredictionEvaluation,
    PredictionModuleOutput,
    PredictionOverride,
    PredictionRun,
    PredictionRunComparable,
    PredictionScenario,
    Project,
    ProjectBenchmarkDisciplineSummary,
    ProjectBenchmarkSummary,
    ProjectDiscipline,
    ProjectParty,
    ProjectScheduleRange,
    Quote,
    QuoteLineItem,
    QuoteSection,
    QuoteVersion,
)
from app.models.enums import CetaRowFinancialType
from app.modules.audit.service import audit_service
from app.modules.comparables.service import comparable_service
from app.modules.forecasts.service import forecast_service
from app.modules.predictions.discipline_prediction import build_discipline_predictions
from app.modules.predictions.evaluation import build_evaluations
from app.modules.predictions.explanations import build_explanations
from app.modules.predictions.fallbacks import select_fallback_tier
from app.modules.predictions.feature_snapshot import build_feature_snapshot
from app.modules.predictions.quote_guidance import build_quote_guidance
from app.modules.predictions.revenue_spread import build_revenue_spread
from app.modules.predictions.risk_anomaly import build_risk_and_anomalies
from app.modules.predictions.scenario_builder import build_scenarios
from app.modules.predictions.schemas import (
    PredictionRunCreateRequest,
    PredictionRunDetailRead,
    PredictionRunListResponse,
    PredictionRunSummaryRead,
    PredictionScenarioPromotionResponse,
    PredictionScenarioPromoteRequest,
    PredictionScenarioUpdateRequest,
    PredictionOverridesPatchRequest,
)
from app.modules.predictions.types import ActualsSummary, PredictionContext, PredictionModuleResult
from app.modules.predictions.utils import amount_or_none, confidence_label, month_key
from app.modules.predictions.win_probability import build_win_probability


def _dedupe_risk_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for signal in signals:
        deduped.setdefault(str(signal["key"]), signal)
    return list(deduped.values())


class PredictionService:
    def _prediction_query(self):
        return (
            select(Project)
            .options(
                selectinload(Project.metadata_record),
                selectinload(Project.disciplines).selectinload(ProjectDiscipline.discipline),
                selectinload(Project.schedule_ranges).selectinload(ProjectScheduleRange.discipline),
                selectinload(Project.parties).selectinload(ProjectParty.company),
                selectinload(Project.quotes).selectinload(Quote.versions),
                selectinload(Project.forecast)
                .selectinload(Forecast.versions)
                .selectinload(ForecastVersion.lines)
                .selectinload(ForecastLine.allocations),
                selectinload(Project.benchmark_summary)
                .selectinload(ProjectBenchmarkSummary.discipline_summaries)
                .selectinload(ProjectBenchmarkDisciplineSummary.discipline),
            )
        )

    def _load_projects(self, session: Session, project_ids: list[str]) -> dict[str, Project]:
        if not project_ids:
            return {}
        result = session.execute(self._prediction_query().where(Project.id.in_(project_ids)))
        return {project.id: project for project in result.scalars().unique().all()}

    def _current_forecast_version(self, project: Project) -> ForecastVersion | None:
        if project.forecast is None:
            return None
        if project.forecast.current_version_id is not None:
            current = next(
                (
                    version
                    for version in project.forecast.versions
                    if version.id == project.forecast.current_version_id
                ),
                None,
            )
            if current is not None:
                return current
        if project.forecast.versions:
            return max(project.forecast.versions, key=lambda item: (item.version_number, item.updated_at))
        return None

    def _load_quote_line_items(self, session: Session, quote_version_id: str | None) -> list[QuoteLineItem]:
        if quote_version_id is None:
            return []
        result = session.execute(
            select(QuoteLineItem)
            .join(QuoteSection, QuoteSection.id == QuoteLineItem.quote_section_id)
            .where(QuoteSection.quote_version_id == quote_version_id)
            .order_by(QuoteSection.sort_order, QuoteLineItem.sort_order)
            .options(selectinload(QuoteLineItem.discipline))
        )
        return list(result.scalars())

    def _load_actuals_summary(self, session: Session, project_id: str) -> ActualsSummary:
        rows = list(
            session.scalars(
                select(MappedActual).where(
                    MappedActual.project_id == project_id,
                    MappedActual.is_current.is_(True),
                )
            )
        )
        summary = ActualsSummary()
        third_party_costs = 0.0
        for row in rows:
            activity_date = row.work_date or row.posting_date
            month = month_key(activity_date) if activity_date is not None else None
            amount = float(row.amount)
            if row.financial_type == CetaRowFinancialType.revenue:
                summary.current_revenue_total += amount
                if month is not None:
                    summary.monthly_revenue[month] = summary.monthly_revenue.get(month, 0.0) + amount
                if row.discipline_id is not None:
                    summary.discipline_revenue[row.discipline_id] = (
                        summary.discipline_revenue.get(row.discipline_id, 0.0) + amount
                    )
            else:
                summary.current_cost_total += amount
                if month is not None:
                    summary.monthly_costs[month] = summary.monthly_costs.get(month, 0.0) + amount
                if row.discipline_id is not None:
                    summary.discipline_costs[row.discipline_id] = (
                        summary.discipline_costs.get(row.discipline_id, 0.0) + amount
                    )
                if row.vendor_name or row.cost_category_key == "third_party":
                    third_party_costs += amount
        if summary.current_cost_total > 0:
            summary.third_party_cost_share_pct = round((third_party_costs / summary.current_cost_total) * 100, 2)
        summary.current_month_count = len(summary.monthly_revenue)
        return summary

    def _request_context_matches(
        self, existing: dict[str, object] | None, expected: dict[str, object]
    ) -> bool:
        if existing is None:
            return False
        return (
            existing.get("quoteVersionId") == expected.get("quoteVersionId")
            and existing.get("disciplineId") == expected.get("disciplineId")
            and int(existing.get("limit") or 25) == int(expected.get("limit") or 25)
        )

    def _run_query(self):
        return select(PredictionRun).options(
            selectinload(PredictionRun.module_outputs),
            selectinload(PredictionRun.comparables),
            selectinload(PredictionRun.scenarios),
            selectinload(PredictionRun.overrides),
            selectinload(PredictionRun.evaluations),
        )

    def _latest_matching_run(
        self, session: Session, project_id: str, request_context: dict[str, object]
    ) -> PredictionRun | None:
        runs = list(
            session.scalars(
                self._run_query()
                .where(PredictionRun.project_id == project_id)
                .order_by(desc(PredictionRun.generated_at))
                .limit(10)
            )
        )
        for run in runs:
            if self._request_context_matches(run.request_context_json, request_context):
                return run
        return None

    def _build_context(
        self,
        session: Session,
        project_id: str,
        *,
        quote_version_id: str | None,
        limit: int,
        discipline_id: str | None,
    ) -> tuple[PredictionContext, dict[str, Any], dict[str, Any]]:
        target_project = comparable_service._get_project_entity(session, project_id)
        comparables = comparable_service.get_comparables(
            session,
            project_id,
            quote_version_id=quote_version_id,
            limit=limit,
            discipline_id=discipline_id,
            include_pinned=True,
        )
        recommendations = comparable_service.get_recommendations(
            session,
            project_id,
            quote_version_id=quote_version_id,
            limit=limit,
            discipline_id=discipline_id,
        )
        target_snapshot, target_quote_version = comparable_service._build_project_snapshot(
            target_project,
            quote_version_id=quote_version_id,
        )
        eligible_items = [
            item for item in comparables["items"] if bool(item["isEligibleForRecommendations"])
        ]
        project_ids = [project_id, *[item["projectId"] for item in comparables["items"]]]
        projects_by_id = self._load_projects(session, project_ids)
        target_project_detail = projects_by_id.get(project_id, target_project)
        quote_line_items = self._load_quote_line_items(
            session,
            target_quote_version.id if target_quote_version is not None else None,
        )
        actuals = self._load_actuals_summary(session, project_id)
        request_context = {
            "quoteVersionId": quote_version_id,
            "disciplineId": discipline_id,
            "limit": limit,
        }
        context = PredictionContext(
            project=target_project_detail,
            target_snapshot=target_snapshot,
            target_quote_version=target_quote_version,
            current_forecast_version=self._current_forecast_version(target_project_detail),
            comparable_items=comparables["items"],
            eligible_items=eligible_items,
            projects_by_id=projects_by_id,
            quote_line_items=quote_line_items,
            schedule_ranges=list(target_project_detail.schedule_ranges),
            actuals=actuals,
            request_context=request_context,
        )
        return context, comparables, recommendations

    def _persist_run(
        self,
        session: Session,
        context: PredictionContext,
        *,
        comparables: dict[str, Any],
        module_results: list[PredictionModuleResult],
        feature_snapshot: dict[str, Any],
        fallback_tier: str,
        methodology_summary: str,
        actor_id: str | None,
    ) -> PredictionRun:
        revenue_module = next(item for item in module_results if item.module_key == "revenue_spread")
        run = PredictionRun(
            project_id=context.project.id,
            quote_version_id=context.target_quote_version.id if context.target_quote_version else None,
            forecast_version_id=context.current_forecast_version.id if context.current_forecast_version else None,
            created_by_id=actor_id,
            model_version="predictive_layer_v2",
            strategy_key="deterministic_modular_prediction_run",
            maturity_stage=str(feature_snapshot["maturityStage"]),
            primary_evidence_source=str(feature_snapshot["primaryEvidenceSource"]),
            fallback_tier=fallback_tier,
            feature_readiness_score=float(feature_snapshot["featureReadinessScore"]),
            data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
            confidence_score=float(feature_snapshot["confidenceScore"]),
            confidence_label=confidence_label(float(feature_snapshot["confidenceScore"])),
            missing_critical_inputs_json=list(feature_snapshot["missingCriticalInputs"]),
            request_context_json=jsonable_encoder(context.request_context),
            source_references_json=jsonable_encoder([
                {
                    "type": "prediction_context",
                    "comparableProjectsConsidered": len(comparables["items"]),
                    "comparableProjectsUsed": len(context.eligible_items),
                    "completeActualHistoryCount": int(feature_snapshot["actualHistoryCount"]),
                    "monthlyProfileCount": int(revenue_module.output.get("profileCount", 0)),
                }
            ]),
            feature_snapshot_json=jsonable_encoder(feature_snapshot),
            methodology_summary=methodology_summary,
            expected_scenario_key="base",
            generated_at=datetime.now(UTC),
        )
        session.add(run)
        session.flush()

        for module in module_results:
            session.add(
                PredictionModuleOutput(
                    prediction_run_id=run.id,
                    module_key=module.module_key,
                    model_module=module.model_module,
                    fallback_tier=module.fallback_tier,
                    confidence_score=module.confidence_score,
                    data_sufficiency_score=module.data_sufficiency_score,
                    confidence_label=module.confidence_label,
                    output_json=jsonable_encoder(module.output),
                    explanation_json=jsonable_encoder(module.explanations),
                    warning_codes_json=jsonable_encoder(module.warning_codes),
                )
            )

        for index, item in enumerate(comparables["items"], start=1):
            session.add(
                PredictionRunComparable(
                    prediction_run_id=run.id,
                    comparable_project_id=item.get("projectId"),
                    comparable_project_name=item["projectName"],
                    selection_state=item["selectionState"],
                    similarity_score=float(item["similarityScore"]),
                    strength=item["strength"],
                    is_primary=index <= 3,
                    sort_order=index,
                    evidence_json=jsonable_encoder(item.get("matchedFactors", [])),
                )
            )

        scenarios_module = next(item for item in module_results if item.module_key == "scenario_builder")
        for scenario in scenarios_module.output["items"]:
            session.add(
                PredictionScenario(
                    prediction_run_id=run.id,
                    scenario_key=scenario["scenarioKey"],
                    title=scenario["title"],
                    is_expected=bool(scenario["isExpected"]),
                    assumption_overrides_json=jsonable_encoder(scenario["assumptionOverrides"]),
                    output_json=jsonable_encoder(scenario),
                )
            )

        evaluation_module = next(item for item in module_results if item.module_key == "evaluation")
        for evaluation in evaluation_module.output["items"]:
            session.add(
                PredictionEvaluation(
                    prediction_run_id=run.id,
                    module_key=evaluation["moduleKey"],
                    scenario_key=evaluation.get("scenarioKey"),
                    metric_key=evaluation["metricKey"],
                    predicted_value_json=jsonable_encoder(evaluation.get("predictedValue")),
                    actual_value_json=jsonable_encoder(evaluation.get("actualValue")),
                    error_value=evaluation.get("errorValue"),
                    calibration_bucket=evaluation.get("calibrationBucket"),
                    note=evaluation.get("note"),
                    outcome_recorded_at=evaluation.get("outcomeRecordedAt"),
                )
            )

        session.flush()
        return run

    def _build_prediction_run(
        self,
        session: Session,
        project_id: str,
        *,
        quote_version_id: str | None,
        limit: int,
        discipline_id: str | None,
        scenario_assumptions: dict[str, dict[str, object]] | None,
        actor_id: str | None,
    ) -> PredictionRun:
        context, comparables, recommendations = self._build_context(
            session,
            project_id,
            quote_version_id=quote_version_id,
            limit=limit,
            discipline_id=discipline_id,
        )

        feature_module, feature_snapshot = build_feature_snapshot(context)
        fallback_module = select_fallback_tier(context, feature_snapshot)
        quote_module = build_quote_guidance(
            context,
            comparable_quote_range=recommendations.get("overallQuoteRange"),
            actual_informed_quote_range=recommendations.get("overallActualInformedRange"),
            fallback_tier=fallback_module.fallback_tier,
            feature_snapshot=feature_snapshot,
        )
        discipline_module = build_discipline_predictions(
            context,
            quote_guidance=quote_module.output,
            fallback_tier=fallback_module.fallback_tier,
            feature_snapshot=feature_snapshot,
            discipline_code_filter=discipline_id,
        )
        omitted_discipline_ids = [
            item["disciplineId"]
            for item in discipline_module.output["items"]
            if not item["isTargetDiscipline"] and float(item["usageRatePct"]) >= 45
        ]
        quote_module.output["omittedDisciplineIds"] = omitted_discipline_ids

        revenue_module = build_revenue_spread(
            context,
            quote_guidance=quote_module.output,
            fallback_tier=fallback_module.fallback_tier,
            feature_snapshot=feature_snapshot,
        )
        win_module = build_win_probability(
            context,
            quote_guidance=quote_module.output,
            fallback_tier=fallback_module.fallback_tier,
            feature_snapshot=feature_snapshot,
        )
        risk_module = build_risk_and_anomalies(
            context,
            quote_guidance=quote_module.output,
            discipline_predictions=discipline_module.output["items"],
            monthly_revenue_spread=revenue_module.output["items"],
            fallback_tier=fallback_module.fallback_tier,
            feature_snapshot=feature_snapshot,
            comparable_risk_signals=_dedupe_risk_signals(
                list(comparables["riskSignals"]) + list(recommendations["riskSignals"]) + list(revenue_module.output.get("warningSignals", []))
            ),
        )
        scenario_module = build_scenarios(
            quote_guidance=quote_module.output,
            discipline_predictions=discipline_module.output["items"],
            monthly_revenue_spread=revenue_module.output["items"],
            overrun_risk=risk_module.output["overrunRisk"],
            win_probability=win_module.output,
            scenario_assumptions=scenario_assumptions,
            fallback_tier=fallback_module.fallback_tier,
            data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
        )
        evaluation_module = build_evaluations(
            context,
            quote_guidance=quote_module.output,
            win_probability=win_module.output,
            scenarios=scenario_module.output["items"],
            data_sufficiency_score=float(feature_snapshot["dataSufficiencyScore"]),
        )
        explanations_module = build_explanations(
            context,
            feature_snapshot=feature_snapshot,
            fallback_tier=fallback_module.fallback_tier,
            module_results=[
                feature_module,
                fallback_module,
                quote_module,
                discipline_module,
                revenue_module,
                win_module,
                risk_module,
                scenario_module,
                evaluation_module,
            ],
        )

        module_results = [
            feature_module,
            fallback_module,
            quote_module,
            discipline_module,
            revenue_module,
            win_module,
            risk_module,
            scenario_module,
            evaluation_module,
            explanations_module,
        ]
        methodology_summary = (
            "Prediction runs reuse explainable comparable scoring, benchmark variance history, "
            "quote structure, schedule timing, and in-flight actuals. Modules persist their own "
            "outputs, fallbacks, and explanations so guidance remains auditable and editable."
        )
        run = self._persist_run(
            session,
            context,
            comparables=comparables,
            module_results=module_results,
            feature_snapshot=feature_snapshot,
            fallback_tier=fallback_module.fallback_tier,
            methodology_summary=methodology_summary,
            actor_id=actor_id,
        )
        audit_service.record(
            session,
            action="prediction.run.created",
            entity_type="prediction_run",
            entity_id=run.id,
            actor_id=actor_id,
            project_id=project_id,
            summary=f"Created prediction run {run.id} for {context.project.name}.",
            metadata=context.request_context,
        )
        session.flush()
        return run

    def _serialize_run_summary(self, run: PredictionRun) -> PredictionRunSummaryRead:
        return PredictionRunSummaryRead(
            id=run.id,
            project_id=run.project_id,
            quote_version_id=run.quote_version_id,
            forecast_version_id=run.forecast_version_id,
            model_version=run.model_version,
            strategy_key=run.strategy_key,
            maturity_stage=run.maturity_stage,
            primary_evidence_source=run.primary_evidence_source,
            fallback_tier=run.fallback_tier,
            feature_readiness_score=float(run.feature_readiness_score),
            data_sufficiency_score=float(run.data_sufficiency_score),
            confidence_score=float(run.confidence_score),
            confidence_label=run.confidence_label,
            expected_scenario_key=run.expected_scenario_key,
            methodology_summary=run.methodology_summary,
            generated_at=run.generated_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    def _overlay_overrides(self, detail: PredictionRunDetailRead) -> PredictionRunDetailRead:
        latest_by_key: dict[tuple[str, str, str | None], Any] = {}
        for override in sorted(detail.overrides, key=lambda item: item.decided_at):
            latest_by_key[(override.module_key, override.target_key, override.scenario_key)] = override

        overall_quote_override = latest_by_key.get(("quote_guidance", "overall_quote", None))
        if overall_quote_override is not None and detail.likely_quote_range is not None:
            detail.likely_quote_range.acceptance_status = overall_quote_override.status
            if overall_quote_override.override_value:
                for source_key, target_key in (
                    ("recommendedLow", "recommended_low"),
                    ("recommendedMedian", "recommended_median"),
                    ("recommendedHigh", "recommended_high"),
                ):
                    if source_key in overall_quote_override.override_value:
                        setattr(
                            detail.likely_quote_range,
                            target_key,
                            float(overall_quote_override.override_value[source_key]),
                        )

        win_override = latest_by_key.get(("win_probability", "win_probability", None))
        if win_override is not None and detail.win_probability is not None:
            detail.win_probability.override_status = win_override.status
            if win_override.override_value and "probabilityPct" in win_override.override_value:
                probability_pct = float(win_override.override_value["probabilityPct"])
                detail.win_probability.probability_pct = probability_pct
                if probability_pct >= 70:
                    detail.win_probability.probability_band = "high"
                elif probability_pct >= 45:
                    detail.win_probability.probability_band = "medium"
                else:
                    detail.win_probability.probability_band = "low"

        return detail

    def _serialize_run(self, run: PredictionRun) -> PredictionRunDetailRead:
        module_map = {module.module_key: module for module in run.module_outputs}
        feature_snapshot = run.feature_snapshot_json or {}
        quote_output = (module_map.get("quote_guidance").output_json if module_map.get("quote_guidance") else {}) or {}
        discipline_output = (module_map.get("discipline_prediction").output_json if module_map.get("discipline_prediction") else {}) or {}
        revenue_output = (module_map.get("revenue_spread").output_json if module_map.get("revenue_spread") else {}) or {}
        risk_output = (module_map.get("risk_anomaly").output_json if module_map.get("risk_anomaly") else {}) or {}
        win_output = (module_map.get("win_probability").output_json if module_map.get("win_probability") else None)
        explanations_output = (module_map.get("explanations").output_json if module_map.get("explanations") else {}) or {}
        source_reference = next(
            (
                reference
                for reference in run.source_references_json
                if reference.get("type") == "prediction_context"
            ),
            {},
        )
        def normalize_explanations(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
            normalized: list[dict[str, Any]] = []
            for value in values:
                normalized.append(
                    {
                        "key": value.get("key", "explanation"),
                        "label": value.get("label", "Explanation"),
                        "impact": str(value.get("impact", value.get("effect", ""))),
                        "detail": value.get("detail", ""),
                    }
                )
            return normalized

        detail = PredictionRunDetailRead(
            **self._serialize_run_summary(run).model_dump(),
            target={
                "projectId": run.project_id,
                "projectName": feature_snapshot.get("projectName", "Unknown project"),
                "quoteCurrencyCode": feature_snapshot.get("quoteCurrencyCode", "GBP"),
                "quoteVersionId": run.quote_version_id,
                "projectFormatKey": feature_snapshot.get("projectFormatKey"),
            },
            model_info={
                "strategy": run.strategy_key,
                "refreshedAt": run.generated_at,
                "updateApproach": "Recomputed from persisted project, quote, benchmark, comparable, forecast, and actuals data with persisted run storage.",
                "comparableProjectsConsidered": int(source_reference.get("comparableProjectsConsidered", len(run.comparables))),
                "comparableProjectsUsed": int(source_reference.get("comparableProjectsUsed", len(run.comparables))),
                "completeActualHistoryCount": int(source_reference.get("completeActualHistoryCount", feature_snapshot.get("actualHistoryCount", 0))),
                "monthlyProfileCount": int(source_reference.get("monthlyProfileCount", revenue_output.get("profileCount", 0))),
            },
            comparable_quote_range=quote_output.get("comparableQuoteRange"),
            actual_informed_quote_range=quote_output.get("actualInformedQuoteRange"),
            likely_quote_range=(
                {
                    key: value
                    for key, value in quote_output.items()
                    if key not in {"comparableQuoteRange", "actualInformedQuoteRange"}
                }
                if quote_output.get("basis")
                else None
            ),
            discipline_usage=discipline_output.get("items", []),
            monthly_revenue_spread=revenue_output.get("items", []),
            overrun_risk=risk_output.get("overrunRisk", {"level": "low", "flags": []}),
            risk_signals=_dedupe_risk_signals(risk_output.get("riskSignals", [])),
            win_probability=win_output if win_output and win_output.get("probabilityPct") is not None else None,
            scenarios=[
                {
                    **scenario.output_json,
                    "id": scenario.id,
                    "updatedAt": scenario.updated_at,
                    "promotedForecastVersionId": scenario.promoted_forecast_version_id,
                    "promotedAt": scenario.promoted_at,
                }
                for scenario in sorted(run.scenarios, key=lambda item: item.scenario_key)
            ],
            top_comparables=explanations_output.get("topComparables", []),
            module_outputs=[
                {
                    "moduleKey": module.module_key,
                    "modelModule": module.model_module,
                    "fallbackTier": module.fallback_tier,
                    "confidenceScore": float(module.confidence_score),
                    "dataSufficiencyScore": float(module.data_sufficiency_score),
                    "confidenceLabel": module.confidence_label,
                    "output": module.output_json,
                    "explanations": normalize_explanations(module.explanation_json),
                    "warningCodes": module.warning_codes_json,
                }
                for module in sorted(run.module_outputs, key=lambda item: item.module_key)
            ],
            overrides=[
                {
                    "id": override.id,
                    "moduleKey": override.module_key,
                    "scenarioKey": override.scenario_key,
                    "targetKey": override.target_key,
                    "status": override.status,
                    "overrideValue": override.override_value_json,
                    "note": override.note,
                    "actorId": override.actor_id,
                    "decidedAt": override.decided_at,
                }
                for override in sorted(run.overrides, key=lambda item: item.decided_at)
            ],
            evaluations=[
                {
                    "id": evaluation.id,
                    "moduleKey": evaluation.module_key,
                    "scenarioKey": evaluation.scenario_key,
                    "metricKey": evaluation.metric_key,
                    "predictedValue": evaluation.predicted_value_json,
                    "actualValue": evaluation.actual_value_json,
                    "errorValue": float(evaluation.error_value) if evaluation.error_value is not None else None,
                    "calibrationBucket": evaluation.calibration_bucket,
                    "note": evaluation.note,
                    "outcomeRecordedAt": evaluation.outcome_recorded_at,
                }
                for evaluation in sorted(run.evaluations, key=lambda item: item.metric_key)
            ],
            missing_critical_inputs=list(run.missing_critical_inputs_json),
            feature_snapshot=feature_snapshot,
            request_context=run.request_context_json or {},
            source_references=run.source_references_json or [],
        )
        return self._overlay_overrides(detail)

    def get_project_predictive_guidance(
        self,
        session: Session,
        project_id: str,
        *,
        quote_version_id: str | None,
        limit: int,
        discipline_id: str | None,
    ) -> dict[str, Any]:
        request_context = {
            "quoteVersionId": quote_version_id,
            "disciplineId": discipline_id,
            "limit": limit,
        }
        run = self._latest_matching_run(session, project_id, request_context)
        if run is None:
            run = self._build_prediction_run(
                session,
                project_id,
                quote_version_id=quote_version_id,
                limit=limit,
                discipline_id=discipline_id,
                scenario_assumptions=None,
                actor_id=None,
            )
            session.flush()
        return self._serialize_run(run).model_dump(mode="json", by_alias=True)

    def create_prediction_run(
        self,
        session: Session,
        project_id: str,
        payload: PredictionRunCreateRequest,
        *,
        actor_id: str,
    ) -> PredictionRunDetailRead:
        run = self._build_prediction_run(
            session,
            project_id,
            quote_version_id=payload.quote_version_id,
            limit=payload.limit,
            discipline_id=payload.discipline_id,
            scenario_assumptions=payload.scenario_assumptions,
            actor_id=actor_id,
        )
        return self._serialize_run(run)

    def list_prediction_runs(self, session: Session, project_id: str) -> PredictionRunListResponse:
        runs = list(
            session.scalars(
                self._run_query()
                .where(PredictionRun.project_id == project_id)
                .order_by(desc(PredictionRun.generated_at))
            )
        )
        return PredictionRunListResponse(
            items=[self._serialize_run_summary(run) for run in runs]
        )

    def get_prediction_run(
        self, session: Session, project_id: str, run_id: str
    ) -> PredictionRunDetailRead:
        run = session.scalar(
            self._run_query().where(
                PredictionRun.id == run_id,
                PredictionRun.project_id == project_id,
            )
        )
        if run is None:
            raise ApiProblemException(
                404,
                f"Prediction run '{run_id}' was not found.",
                "Prediction Run Not Found",
            )
        return self._serialize_run(run)

    def patch_overrides(
        self,
        session: Session,
        project_id: str,
        run_id: str,
        payload: PredictionOverridesPatchRequest,
        *,
        actor_id: str,
    ) -> PredictionRunDetailRead:
        run = session.scalar(
            self._run_query().where(
                PredictionRun.id == run_id,
                PredictionRun.project_id == project_id,
            )
        )
        if run is None:
            raise ApiProblemException(404, "Prediction run was not found.", "Prediction Run Not Found")
        now = datetime.now(UTC)
        for item in payload.items:
            session.add(
                PredictionOverride(
                    prediction_run_id=run.id,
                    module_key=item.module_key,
                    scenario_key=item.scenario_key,
                    target_key=item.target_key,
                    status=item.status,
                    override_value_json=item.override_value,
                    note=item.note,
                    actor_id=actor_id,
                    decided_at=now,
                )
            )
        run.updated_at = now
        session.flush()
        audit_service.record(
            session,
            action="prediction.override.recorded",
            entity_type="prediction_run",
            entity_id=run.id,
            actor_id=actor_id,
            project_id=project_id,
            summary=f"Recorded {len(payload.items)} prediction override(s).",
        )
        session.refresh(run)
        return self.get_prediction_run(session, project_id, run_id)

    def update_scenario(
        self,
        session: Session,
        project_id: str,
        run_id: str,
        scenario_key: str,
        payload: PredictionScenarioUpdateRequest,
        *,
        actor_id: str,
    ) -> PredictionRunDetailRead:
        run = session.scalar(
            self._run_query().where(
                PredictionRun.id == run_id,
                PredictionRun.project_id == project_id,
            )
        )
        if run is None:
            raise ApiProblemException(404, "Prediction run was not found.", "Prediction Run Not Found")
        scenario = next((item for item in run.scenarios if item.scenario_key == scenario_key), None)
        if scenario is None:
            raise ApiProblemException(404, "Prediction scenario was not found.", "Prediction Scenario Not Found")
        if not same_timestamp(scenario.updated_at, payload.expected_updated_at):
            raise ApiProblemException(
                409,
                "The prediction scenario was modified by another request. Reload and retry.",
                "Stale Update",
            )

        detail = self._serialize_run(run)
        assumptions = {
            item.scenario_key: dict(item.assumption_overrides_json or {})
            for item in run.scenarios
        }
        assumptions[scenario_key] = payload.assumption_overrides
        scenario_module = build_scenarios(
            quote_guidance=detail.likely_quote_range.model_dump(mode="json", by_alias=True)
            if detail.likely_quote_range is not None
            else None,
            discipline_predictions=[item.model_dump(mode="json", by_alias=True) for item in detail.discipline_usage],
            monthly_revenue_spread=[item.model_dump(mode="json", by_alias=True) for item in detail.monthly_revenue_spread],
            overrun_risk=detail.overrun_risk.model_dump(mode="json", by_alias=True),
            win_probability=detail.win_probability.model_dump(mode="json", by_alias=True)
            if detail.win_probability is not None
            else None,
            scenario_assumptions=assumptions,
            fallback_tier=run.fallback_tier,
            data_sufficiency_score=float(run.data_sufficiency_score),
        )
        scenario_rows = {item.scenario_key: item for item in run.scenarios}
        for scenario_output in scenario_module.output["items"]:
            row = scenario_rows.get(scenario_output["scenarioKey"])
            if row is None:
                continue
            row.title = scenario_output["title"]
            row.is_expected = bool(scenario_output["isExpected"])
            row.assumption_overrides_json = jsonable_encoder(scenario_output["assumptionOverrides"])
            row.output_json = jsonable_encoder(scenario_output)
        scenario_module_row = next(
            (item for item in run.module_outputs if item.module_key == "scenario_builder"),
            None,
        )
        if scenario_module_row is not None:
            scenario_module_row.output_json = jsonable_encoder(scenario_module.output)
            scenario_module_row.explanation_json = jsonable_encoder(scenario_module.explanations)
            scenario_module_row.warning_codes_json = jsonable_encoder(scenario_module.warning_codes)
            scenario_module_row.updated_at = datetime.now(UTC)
        run.updated_at = datetime.now(UTC)
        session.flush()
        audit_service.record(
            session,
            action="prediction.scenario.updated",
            entity_type="prediction_scenario",
            entity_id=scenario.id,
            actor_id=actor_id,
            project_id=project_id,
            summary=f"Updated scenario {scenario_key} for prediction run {run.id}.",
        )
        session.refresh(run)
        return self.get_prediction_run(session, project_id, run_id)

    def promote_scenario(
        self,
        session: Session,
        project_id: str,
        run_id: str,
        payload: PredictionScenarioPromoteRequest,
        *,
        actor_id: str,
    ) -> PredictionScenarioPromotionResponse:
        run = session.scalar(
            self._run_query().where(
                PredictionRun.id == run_id,
                PredictionRun.project_id == project_id,
            )
        )
        if run is None:
            raise ApiProblemException(404, "Prediction run was not found.", "Prediction Run Not Found")
        scenario = next((item for item in run.scenarios if item.scenario_key == payload.scenario_key), None)
        if scenario is None:
            raise ApiProblemException(404, "Prediction scenario was not found.", "Prediction Scenario Not Found")
        forecast_version = forecast_service.promote_prediction_scenario(
            session,
            project_id,
            scenario.output_json,
            title=payload.title,
            notes_text=payload.notes_text,
            revision_reason=payload.revision_reason,
            probability_percent=payload.probability_percent,
            actor_id=actor_id,
        )
        promoted_at = datetime.now(UTC)
        scenario.promoted_forecast_version_id = forecast_version.id
        scenario.promoted_at = promoted_at
        scenario_output = dict(scenario.output_json)
        scenario_output["promotedForecastVersionId"] = forecast_version.id
        scenario_output["promotedAt"] = promoted_at
        scenario.output_json = jsonable_encoder(scenario_output)
        run.updated_at = promoted_at
        session.flush()
        audit_service.record(
            session,
            action="prediction.scenario.promoted",
            entity_type="prediction_scenario",
            entity_id=scenario.id,
            actor_id=actor_id,
            project_id=project_id,
            summary=f"Promoted scenario {payload.scenario_key} into forecast draft {forecast_version.id}.",
        )
        return PredictionScenarioPromotionResponse(
            prediction_run_id=run.id,
            scenario_key=payload.scenario_key,
            promoted_forecast_version_id=forecast_version.id,
            promoted_at=promoted_at,
        )


prediction_service = PredictionService()
