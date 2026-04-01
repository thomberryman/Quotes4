from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ApiProblemException
from app.models import (
    ComparableProjectLink,
    Project,
    ProjectBenchmarkDisciplineSummary,
    ProjectBenchmarkSummary,
    ProjectDiscipline,
    ProjectMetadata,
    ProjectParty,
    Quote,
    QuoteVersion,
)
from app.models.enums import ComparableProjectLinkDisposition, QuoteVersionStatus
from app.modules.audit.service import audit_service
from app.modules.comparables.benchmark_summary import build_benchmark_summary

SCORING_MODEL_VERSION = "comparable-project-v1"

FACTOR_WEIGHTS: dict[str, int] = {
    "project_format_key": 18,
    "client": 15,
    "discipline_overlap": 14,
    "budget_band": 14,
    "schedule_length": 10,
    "deliverables_overlap": 8,
    "complexity_profile": 8,
    "language_localization_profile": 5,
    "episode_count": 4,
    "counterparty_overlap": 4,
}

COMPLEXITY_LEVELS = {
    "simple": 1,
    "low": 1,
    "standard": 2,
    "medium": 2,
    "complex": 3,
    "high": 3,
}


def _round(value: float) -> float:
    return round(value, 2)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    return _round(float(value))


def _unique_strings(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


def _overlap_score(left: list[str], right: list[str]) -> float:
    left_set = set(_unique_strings(left))
    right_set = set(_unique_strings(right))
    union = left_set | right_set

    if not union:
        return 0.0

    return len(left_set & right_set) / len(union)


def _flatten_counterparties(snapshot: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for role, company_ids in (snapshot.get("counterpartyCompanyIdsByRole") or {}).items():
        for company_id in company_ids:
            values.append(f"{role}:{company_id}")
    return _unique_strings(values)


def _strength_for_score(similarity_score: float) -> str:
    if similarity_score >= 70:
        return "strong"
    if similarity_score >= 55:
        return "usable"
    return "weak"


def _factor(
    factor_key: str,
    label: str,
    *,
    awarded_points: float,
    detail: str,
    is_available: bool,
) -> dict[str, Any]:
    return {
        "factorKey": factor_key,
        "label": label,
        "weight": FACTOR_WEIGHTS[factor_key],
        "awardedPoints": _round(awarded_points),
        "detail": detail,
        "isAvailable": is_available,
    }


def _compare_exact(
    factor_key: str, label: str, target_value: str | None, candidate_value: str | None
) -> dict[str, Any]:
    if not target_value or not candidate_value:
        return _factor(
            factor_key,
            label,
            awarded_points=0,
            detail=f"{label} metadata is missing on the target or candidate project.",
            is_available=False,
        )

    if target_value == candidate_value:
        return _factor(
            factor_key,
            label,
            awarded_points=FACTOR_WEIGHTS[factor_key],
            detail=f"{label} matches exactly.",
            is_available=True,
        )

    return _factor(
        factor_key,
        label,
        awarded_points=0,
        detail=f"{label} does not match.",
        is_available=True,
    )


def _compare_overlap(
    factor_key: str, label: str, target_values: list[str], candidate_values: list[str]
) -> dict[str, Any]:
    if not target_values or not candidate_values:
        return _factor(
            factor_key,
            label,
            awarded_points=0,
            detail=f"{label} metadata is missing on the target or candidate project.",
            is_available=False,
        )

    overlap = _overlap_score(target_values, candidate_values)
    return _factor(
        factor_key,
        label,
        awarded_points=FACTOR_WEIGHTS[factor_key] * overlap,
        detail=f"{label} overlap is {round(overlap * 100)}%.",
        is_available=True,
    )


def _compare_budget(target_value: float | None, candidate_value: float | None) -> dict[str, Any]:
    if not target_value or not candidate_value or target_value <= 0 or candidate_value <= 0:
        return _factor(
            "budget_band",
            "Budget Band",
            awarded_points=0,
            detail="Budget or quote-size metadata is missing on the target or candidate project.",
            is_available=False,
        )

    ratio = abs(candidate_value - target_value) / target_value
    if ratio <= 0.1:
        return _factor(
            "budget_band",
            "Budget Band",
            awarded_points=FACTOR_WEIGHTS["budget_band"],
            detail="Budget is within 10% of the target project.",
            is_available=True,
        )
    if ratio <= 0.25:
        return _factor(
            "budget_band",
            "Budget Band",
            awarded_points=FACTOR_WEIGHTS["budget_band"] * 0.7,
            detail="Budget is within 25% of the target project.",
            is_available=True,
        )
    if ratio <= 0.5:
        return _factor(
            "budget_band",
            "Budget Band",
            awarded_points=FACTOR_WEIGHTS["budget_band"] * 0.4,
            detail="Budget is within 50% of the target project.",
            is_available=True,
        )

    return _factor(
        "budget_band",
        "Budget Band",
        awarded_points=0,
        detail="Budget is outside the comparable range for the target project.",
        is_available=True,
    )


def _compare_duration(target_value: int | None, candidate_value: int | None) -> dict[str, Any]:
    if not target_value or not candidate_value or target_value <= 0 or candidate_value <= 0:
        return _factor(
            "schedule_length",
            "Schedule Length",
            awarded_points=0,
            detail="Schedule-length metadata is missing on the target or candidate project.",
            is_available=False,
        )

    difference = abs(candidate_value - target_value)
    ratio = difference / target_value
    if difference <= 1 or ratio <= 0.1:
        return _factor(
            "schedule_length",
            "Schedule Length",
            awarded_points=FACTOR_WEIGHTS["schedule_length"],
            detail="Duration is within one week or 10% of the target project.",
            is_available=True,
        )
    if ratio <= 0.25:
        return _factor(
            "schedule_length",
            "Schedule Length",
            awarded_points=FACTOR_WEIGHTS["schedule_length"] * 0.5,
            detail="Duration is within 25% of the target project.",
            is_available=True,
        )

    return _factor(
        "schedule_length",
        "Schedule Length",
        awarded_points=0,
        detail="Schedule length is materially different from the target project.",
        is_available=True,
    )


def _compare_episode_count(target_value: int | None, candidate_value: int | None) -> dict[str, Any]:
    if not target_value or not candidate_value:
        return _factor(
            "episode_count",
            "Episode Count",
            awarded_points=0,
            detail="Episode-count metadata is missing on the target or candidate project.",
            is_available=False,
        )

    if target_value == candidate_value:
        return _factor(
            "episode_count",
            "Episode Count",
            awarded_points=FACTOR_WEIGHTS["episode_count"],
            detail="Episode count matches exactly.",
            is_available=True,
        )
    if abs(target_value - candidate_value) <= 1:
        return _factor(
            "episode_count",
            "Episode Count",
            awarded_points=FACTOR_WEIGHTS["episode_count"] * 0.5,
            detail="Episode count is within one episode of the target project.",
            is_available=True,
        )

    return _factor(
        "episode_count",
        "Episode Count",
        awarded_points=0,
        detail="Episode count is outside the comparable range for the target project.",
        is_available=True,
    )


def _compare_complexity(target: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    scores: list[float] = []
    for axis in ("finishing", "audio", "vfx"):
        target_value = (target.get("complexityProfile") or {}).get(axis)
        candidate_value = (candidate.get("complexityProfile") or {}).get(axis)
        if not target_value or not candidate_value:
            continue

        target_level = COMPLEXITY_LEVELS.get(str(target_value).lower())
        candidate_level = COMPLEXITY_LEVELS.get(str(candidate_value).lower())
        if target_level is None or candidate_level is None:
            continue

        difference = abs(target_level - candidate_level)
        if difference == 0:
            scores.append(1)
        elif difference == 1:
            scores.append(0.5)
        else:
            scores.append(0)

    if not scores:
        return _factor(
            "complexity_profile",
            "Complexity Profile",
            awarded_points=0,
            detail="Complexity metadata is missing on the target or candidate project.",
            is_available=False,
        )

    score = sum(scores) / len(scores)
    return _factor(
        "complexity_profile",
        "Complexity Profile",
        awarded_points=FACTOR_WEIGHTS["complexity_profile"] * score,
        detail=(
            f"Complexity profile alignment is {round(score * 100)}% "
            "across finishing, audio, and VFX."
        ),
        is_available=True,
    )


def _compare_language_and_localization(
    target: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    target_language = target.get("primaryLanguageCode")
    candidate_language = candidate.get("primaryLanguageCode")
    target_localization_keys = target.get("localizationKeys", [])
    candidate_localization_keys = candidate.get("localizationKeys", [])

    language_available = bool(target_language and candidate_language)
    localization_available = bool(target_localization_keys and candidate_localization_keys)
    if not language_available and not localization_available:
        return _factor(
            "language_localization_profile",
            "Language / Localization",
            awarded_points=0,
            detail=(
                "Language or localization metadata is missing on the "
                "target or candidate project."
            ),
            is_available=False,
        )

    language_score = 1 if language_available and target_language == candidate_language else 0
    localization_score = (
        _overlap_score(target_localization_keys, candidate_localization_keys)
        if localization_available
        else 0
    )
    normalized_score = (language_score * 0.6 if language_available else 0) + (
        localization_score * 0.4 if localization_available else 0
    )
    return _factor(
        "language_localization_profile",
        "Language / Localization",
        awarded_points=FACTOR_WEIGHTS["language_localization_profile"] * normalized_score,
        detail=(
            f"Primary language {'matches' if language_score == 1 else 'does not match'} "
            f"and localization overlap is {round(localization_score * 100)}%."
        ),
        is_available=True,
    )


def _score_project(target: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    matched_factors = [
        _compare_exact(
            "project_format_key",
            "Project Format",
            target.get("projectFormatKey"),
            candidate.get("projectFormatKey"),
        ),
        _compare_exact("client", "Client", target.get("clientId"), candidate.get("clientId")),
        _compare_overlap(
            "discipline_overlap",
            "Discipline Overlap",
            target.get("disciplineIds", []),
            candidate.get("disciplineIds", []),
        ),
        _compare_budget(target.get("targetAmount"), candidate.get("targetAmount")),
        _compare_duration(target.get("durationWeeks"), candidate.get("durationWeeks")),
        _compare_overlap(
            "deliverables_overlap",
            "Deliverables Overlap",
            target.get("deliverableKeys", []),
            candidate.get("deliverableKeys", []),
        ),
        _compare_complexity(target, candidate),
        _compare_language_and_localization(target, candidate),
        _compare_episode_count(target.get("episodeCount"), candidate.get("episodeCount")),
        _compare_overlap(
            "counterparty_overlap",
            "Counterparty Overlap",
            _flatten_counterparties(target),
            _flatten_counterparties(candidate),
        ),
    ]
    matched_factors.sort(key=lambda factor: factor["awardedPoints"], reverse=True)
    achieved_points = sum(float(factor["awardedPoints"]) for factor in matched_factors)
    available_weight = sum(
        factor["weight"] for factor in matched_factors if bool(factor["isAvailable"])
    )
    return {
        "similarityScore": _round(min(100, achieved_points)),
        "coveragePct": _round(float(available_weight)),
        "strength": _strength_for_score(achieved_points),
        "matchedFactors": [
            {key: value for key, value in factor.items() if key != "isAvailable"}
            for factor in matched_factors
        ],
    }


def _weighted_percentile(values: list[dict[str, float | str]], percentile: float) -> float:
    total_weight = sum(float(value["weight"]) for value in values)
    target_weight = total_weight * percentile
    cumulative_weight = 0.0
    for value in sorted(values, key=lambda item: float(item["value"])):
        cumulative_weight += float(value["weight"])
        if cumulative_weight >= target_weight:
            return _round(float(value["value"]))
    return _round(float(values[-1]["value"]))


def _weighted_range(
    values: list[dict[str, float | str]], currency_code: str
) -> dict[str, Any] | None:
    if len(values) < 3:
        return None

    if len(values) < 5:
        sorted_values = sorted(values, key=lambda item: float(item["value"]))
        return {
            "low": _round(float(sorted_values[0]["value"])),
            "median": _weighted_percentile(values, 0.5),
            "high": _round(float(sorted_values[-1]["value"])),
            "currencyCode": currency_code,
            "sampleSize": len(values),
            "comparableProjectIds": [str(value["projectId"]) for value in values],
            "methodology": "min_median_max",
        }

    return {
        "low": _weighted_percentile(values, 0.25),
        "median": _weighted_percentile(values, 0.5),
        "high": _weighted_percentile(values, 0.75),
        "currencyCode": currency_code,
        "sampleSize": len(values),
        "comparableProjectIds": [str(value["projectId"]) for value in values],
        "methodology": "weighted_percentiles",
    }


class ComparableService:
    def _project_query(self):
        return select(Project).options(
            selectinload(Project.metadata_record),
            selectinload(Project.parties).selectinload(ProjectParty.company),
            selectinload(Project.disciplines).selectinload(ProjectDiscipline.discipline),
            selectinload(Project.quotes).selectinload(Quote.versions),
            selectinload(Project.benchmark_summary)
            .selectinload(ProjectBenchmarkSummary.discipline_summaries)
            .selectinload(ProjectBenchmarkDisciplineSummary.discipline),
            selectinload(Project.comparable_source_links),
        )

    def _get_project_entity(self, session: Session, project_id: str) -> Project:
        result = session.execute(self._project_query().where(Project.id == project_id))
        project = result.scalars().unique().one_or_none()
        if project is None:
            raise ApiProblemException(
                status_code=404,
                detail=f"Project {project_id} was not found.",
            )
        return project

    def _list_candidate_projects(self, session: Session, project_id: str) -> list[Project]:
        result = session.execute(
            self._project_query()
            .where(Project.id != project_id)
            .order_by(Project.updated_at.desc(), Project.name.asc())
        )
        return list(result.scalars().unique().all())

    def _resolve_quote_version(
        self, project: Project, requested_quote_version_id: str | None = None
    ) -> QuoteVersion | None:
        versions = [version for quote in project.quotes for version in quote.versions]
        if not versions:
            return None

        if requested_quote_version_id:
            for version in versions:
                if version.id == requested_quote_version_id:
                    return version
            raise ApiProblemException(
                status_code=422,
                title="Invalid Quote Version",
                detail=(
                    f"Quote version {requested_quote_version_id} does not belong to project "
                    f"{project.id}."
                ),
            )

        current_versions = []
        for quote in project.quotes:
            if quote.current_version_id is None:
                continue
            current = next(
                (
                    version
                    for version in quote.versions
                    if version.id == quote.current_version_id
                ),
                None,
            )
            if current is not None:
                current_versions.append(current)
        if current_versions:
            return max(current_versions, key=self._quote_version_sort_key)

        issued_versions = [
            version
            for version in versions
            if version.status in {QuoteVersionStatus.issued, QuoteVersionStatus.accepted}
        ]
        if issued_versions:
            return max(issued_versions, key=self._quote_version_sort_key)

        return max(versions, key=self._quote_version_sort_key)

    def _quote_version_sort_key(self, version: QuoteVersion) -> tuple[datetime, int]:
        reference_date = (
            version.issued_at
            or version.accepted_at
            or version.rejected_at
            or version.updated_at
            or version.created_at
        )
        return (reference_date, int(version.version_number))

    def _resolve_client_party(self, project: Project) -> ProjectParty | None:
        client_parties = [party for party in project.parties if party.role.value == "client"]
        if not client_parties:
            return None
        return next((party for party in client_parties if party.is_primary), client_parties[0])

    def _resolve_counterparties(self, project: Project) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for party in project.parties:
            grouped.setdefault(party.role.value, []).append(party.company_id)
        return {key: _unique_strings(values) for key, values in grouped.items()}

    def _metadata_array(self, metadata_record: ProjectMetadata | None, key: str) -> list[str]:
        metadata_json = metadata_record.metadata_json if metadata_record is not None else {}
        raw_value = metadata_json.get(key) if metadata_json else None
        if not isinstance(raw_value, list):
            return []
        return _unique_strings([str(value) for value in raw_value if isinstance(value, str)])

    def _metadata_object(
        self, metadata_record: ProjectMetadata | None, key: str
    ) -> dict[str, str] | None:
        metadata_json = metadata_record.metadata_json if metadata_record is not None else {}
        raw_value = metadata_json.get(key) if metadata_json else None
        if not isinstance(raw_value, dict):
            return None
        normalized = {
            str(axis): str(value)
            for axis, value in raw_value.items()
            if isinstance(axis, str) and isinstance(value, str)
        }
        return normalized or None

    def _serialize_benchmark_summary(
        self, benchmark_summary: ProjectBenchmarkSummary | None
    ) -> dict[str, Any] | None:
        summary = build_benchmark_summary(benchmark_summary)
        if summary is None:
            return None
        return summary.model_dump(mode="json", by_alias=True)

    def _build_project_snapshot(
        self,
        project: Project,
        *,
        quote_version_id: str | None = None,
    ) -> tuple[dict[str, Any], QuoteVersion | None]:
        quote_version = self._resolve_quote_version(project, quote_version_id)
        benchmark_summary = self._serialize_benchmark_summary(project.benchmark_summary)
        metadata_record = project.metadata_record
        client_party = self._resolve_client_party(project)
        target_amount = (
            _float(quote_version.total_amount) if quote_version is not None else None
        ) or _float(metadata_record.budget_target if metadata_record is not None else None)
        if target_amount is None and benchmark_summary is not None:
            target_amount = _float(benchmark_summary.get("quotedAmount"))

        project_format_key = None
        if metadata_record is not None:
            project_format_key = metadata_record.project_format_key or metadata_record.format_type or None
            if not project_format_key and metadata_record.metadata_json:
                raw_project_format = metadata_record.metadata_json.get("projectFormatKey")
                if isinstance(raw_project_format, str):
                    project_format_key = raw_project_format

        primary_language_code = None
        if metadata_record is not None:
            primary_language_code = metadata_record.language or None
            if not primary_language_code and metadata_record.metadata_json:
                raw_primary_language = metadata_record.metadata_json.get("primaryLanguageCode")
                if isinstance(raw_primary_language, str):
                    primary_language_code = raw_primary_language

        quote_currency_code = (
            (quote_version.currency_code if quote_version is not None else None)
            or project.quote_currency_code
            or (benchmark_summary.get("currencyCode") if benchmark_summary is not None else None)
            or "GBP"
        )

        return (
            {
                "id": project.id,
                "projectName": project.name,
                "status": project.status.value,
                "clientId": client_party.company_id if client_party is not None else None,
                "clientName": (
                    client_party.company.name
                    if client_party is not None and client_party.company is not None
                    else None
                ),
                "projectFormatKey": project_format_key,
                "disciplineIds": [
                    link.discipline.code
                    for link in project.disciplines
                    if link.discipline is not None
                ],
                "targetAmount": target_amount,
                "durationWeeks": (
                    int(metadata_record.duration_weeks)
                    if metadata_record is not None and metadata_record.duration_weeks is not None
                    else None
                ),
                "episodeCount": (
                    int(metadata_record.episode_count)
                    if metadata_record is not None and metadata_record.episode_count is not None
                    else None
                ),
                "quoteCurrencyCode": quote_currency_code,
                "primaryLanguageCode": primary_language_code,
                "deliverableKeys": self._metadata_array(metadata_record, "deliverableKeys"),
                "localizationKeys": self._metadata_array(metadata_record, "localizationKeys"),
                "complexityProfile": self._metadata_object(metadata_record, "complexityProfile"),
                "counterpartyCompanyIdsByRole": self._resolve_counterparties(project),
                "benchmarkSummary": benchmark_summary,
            },
            quote_version,
        )

    def _selection_state(
        self,
        selection_links_by_candidate_id: dict[str, ComparableProjectLink],
        candidate_id: str,
    ) -> str:
        link = selection_links_by_candidate_id.get(candidate_id)
        if link is None:
            return "auto"
        return link.disposition.value

    def _is_recommendation_eligible(
        self,
        target: dict[str, Any],
        candidate: dict[str, Any],
        selection_state: str,
        score: dict[str, Any],
    ) -> bool:
        if selection_state == "excluded":
            return False
        if score["strength"] == "weak":
            return False
        if candidate["quoteCurrencyCode"] != target["quoteCurrencyCode"]:
            return False
        if candidate["status"] not in {"awarded", "complete"}:
            return False
        benchmark_summary = candidate.get("benchmarkSummary") or {}
        return bool(benchmark_summary.get("quotedAmount"))

    def _collect_target_risk_signals(self, target: dict[str, Any]) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        if not target.get("projectFormatKey"):
            signals.append(
                {
                    "key": "missing_project_format",
                    "severity": "warning",
                    "detail": "Target project is missing a controlled project format key.",
                }
            )
        if not target.get("primaryLanguageCode"):
            signals.append(
                {
                    "key": "missing_primary_language",
                    "severity": "info",
                    "detail": "Target project is missing a primary language code.",
                }
            )
        if not target.get("deliverableKeys"):
            signals.append(
                {
                    "key": "missing_deliverables",
                    "severity": "info",
                    "detail": "Target project has no structured deliverable metadata.",
                }
            )
        complexity_profile = target.get("complexityProfile") or {}
        if not (
            complexity_profile.get("finishing")
            or complexity_profile.get("audio")
            or complexity_profile.get("vfx")
        ):
            signals.append(
                {
                    "key": "missing_complexity_profile",
                    "severity": "info",
                    "detail": "Target project is missing structured complexity metadata.",
                }
            )
        return signals

    def _rank_candidates(
        self,
        target_project: Project,
        target_snapshot: dict[str, Any],
        candidate_projects: list[Project],
        *,
        limit: int,
        discipline_id: str | None,
        include_pinned: bool,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        risk_signals = self._collect_target_risk_signals(target_snapshot)
        currency_filtered_count = 0
        selection_links_by_candidate_id = {
            link.comparable_project_id: link for link in target_project.comparable_source_links
        }

        for candidate_project in candidate_projects:
            candidate_snapshot, _ = self._build_project_snapshot(candidate_project)
            if discipline_id and discipline_id not in candidate_snapshot.get("disciplineIds", []):
                continue

            score = _score_project(target_snapshot, candidate_snapshot)
            selection_state = self._selection_state(
                selection_links_by_candidate_id,
                candidate_project.id,
            )
            if selection_state == "pinned" and not include_pinned:
                continue
            if selection_state == "auto" and score["strength"] == "weak":
                continue
            if candidate_snapshot["quoteCurrencyCode"] != target_snapshot["quoteCurrencyCode"]:
                currency_filtered_count += 1

            items.append(
                {
                    "projectId": candidate_snapshot["id"],
                    "projectName": candidate_snapshot["projectName"],
                    "status": candidate_snapshot["status"],
                    "clientName": candidate_snapshot.get("clientName"),
                    "similarityScore": score["similarityScore"],
                    "coveragePct": score["coveragePct"],
                    "strength": score["strength"],
                    "selectionState": selection_state,
                    "matchedFactors": score["matchedFactors"],
                    "benchmarkSummary": candidate_snapshot.get("benchmarkSummary"),
                    "disciplineBenchmarkSummaries": (
                        candidate_snapshot.get("benchmarkSummary") or {}
                    ).get("disciplineSummaries", []),
                    "isEligibleForRecommendations": self._is_recommendation_eligible(
                        target_snapshot,
                        candidate_snapshot,
                        selection_state,
                        score,
                    ),
                }
            )

        selection_priority = {"pinned": 0, "auto": 1, "excluded": 2}
        items.sort(
            key=lambda item: (
                selection_priority[item["selectionState"]],
                -float(item["similarityScore"]),
                -float(item["coveragePct"]),
                str(item["projectName"]),
            )
        )

        if currency_filtered_count > 0:
            risk_signals.append(
                {
                    "key": "currency_filtered_candidates",
                    "severity": "info",
                    "detail": (
                        f"{currency_filtered_count} candidate project(s) were ignored for numeric "
                        "recommendations because their quote currency did not "
                        "match the target project."
                    ),
                }
            )

        return {
            "items": items[:limit],
            "riskSignals": risk_signals,
        }

    def get_comparables(
        self,
        session: Session,
        project_id: str,
        *,
        quote_version_id: str | None,
        limit: int,
        discipline_id: str | None,
        include_pinned: bool,
    ) -> dict[str, Any]:
        target_project = self._get_project_entity(session, project_id)
        candidate_projects = self._list_candidate_projects(session, project_id)
        target_snapshot, target_quote_version = self._build_project_snapshot(
            target_project,
            quote_version_id=quote_version_id,
        )
        ranked = self._rank_candidates(
            target_project,
            target_snapshot,
            candidate_projects,
            limit=limit,
            discipline_id=discipline_id,
            include_pinned=include_pinned,
        )
        return {
            "target": {
                "projectId": target_snapshot["id"],
                "projectName": target_snapshot["projectName"],
                "quoteCurrencyCode": target_snapshot["quoteCurrencyCode"],
                "quoteVersionId": target_quote_version.id if target_quote_version else None,
                "projectFormatKey": target_snapshot.get("projectFormatKey"),
            },
            "scoringModelVersion": SCORING_MODEL_VERSION,
            "riskSignals": ranked["riskSignals"],
            "items": ranked["items"],
        }

    def get_recommendations(
        self,
        session: Session,
        project_id: str,
        *,
        quote_version_id: str | None,
        limit: int,
        discipline_id: str | None,
    ) -> dict[str, Any]:
        target_project = self._get_project_entity(session, project_id)
        candidate_projects = self._list_candidate_projects(session, project_id)
        target_snapshot, target_quote_version = self._build_project_snapshot(
            target_project,
            quote_version_id=quote_version_id,
        )
        ranked = self._rank_candidates(
            target_project,
            target_snapshot,
            candidate_projects,
            limit=limit,
            discipline_id=discipline_id,
            include_pinned=True,
        )
        eligible_items = [
            item for item in ranked["items"] if bool(item["isEligibleForRecommendations"])
        ]

        overall_values = [
            {
                "projectId": item["projectId"],
                "value": item["benchmarkSummary"]["quotedAmount"],
                "weight": item["similarityScore"],
            }
            for item in eligible_items
        ]
        overall_quote_range = _weighted_range(overall_values, target_snapshot["quoteCurrencyCode"])

        actual_variance_values = [
            {
                "projectId": item["projectId"],
                "value": item["benchmarkSummary"]["quoteToActualVariancePct"],
                "weight": item["similarityScore"],
            }
            for item in eligible_items
            if item["status"] == "complete"
            and item["benchmarkSummary"].get("actualsStatus") == "complete"
            and item["benchmarkSummary"].get("quoteToActualVariancePct") is not None
        ]
        overall_actual_informed_range = None
        if overall_quote_range is not None:
            variance_range = _weighted_range(
                actual_variance_values,
                target_snapshot["quoteCurrencyCode"],
            )
            if variance_range is not None:
                overall_actual_informed_range = {
                    "low": _round(overall_quote_range["low"] * (1 + variance_range["low"] / 100)),
                    "median": _round(
                        overall_quote_range["median"] * (1 + variance_range["median"] / 100)
                    ),
                    "high": _round(
                        overall_quote_range["high"] * (1 + variance_range["high"] / 100)
                    ),
                    "currencyCode": target_snapshot["quoteCurrencyCode"],
                    "sampleSize": variance_range["sampleSize"],
                    "comparableProjectIds": variance_range["comparableProjectIds"],
                    "methodology": variance_range["methodology"],
                    "varianceLowPct": variance_range["low"],
                    "varianceMedianPct": variance_range["median"],
                    "varianceHighPct": variance_range["high"],
                }

        discipline_values: dict[str, dict[str, Any]] = {}
        for item in eligible_items:
            for summary in item["disciplineBenchmarkSummaries"]:
                if discipline_id is not None and summary["disciplineId"] != discipline_id:
                    continue
                bucket = discipline_values.setdefault(
                    summary["disciplineId"],
                    {
                        "disciplineName": summary.get("disciplineName"),
                        "quoted": [],
                        "variance": [],
                    },
                )
                bucket["quoted"].append(
                    {
                        "projectId": item["projectId"],
                        "value": summary["quotedAmount"],
                        "weight": item["similarityScore"],
                    }
                )
                if (
                    summary.get("actualsStatus") == "complete"
                    and summary.get("quoteToActualVariancePct") is not None
                ):
                    bucket["variance"].append(
                        {
                            "projectId": item["projectId"],
                            "value": summary["quoteToActualVariancePct"],
                            "weight": item["similarityScore"],
                        }
                    )

        discipline_ranges: list[dict[str, Any]] = []
        for discipline_id, values in discipline_values.items():
            range_summary = _weighted_range(values["quoted"], target_snapshot["quoteCurrencyCode"])
            if range_summary is None:
                continue
            discipline_range = {
                "disciplineId": discipline_id,
                "disciplineName": values["disciplineName"],
                **range_summary,
            }
            if len(values["variance"]) >= 3:
                discipline_range["observedVarianceMedianPct"] = _weighted_percentile(
                    values["variance"], 0.5
                )
            discipline_ranges.append(discipline_range)

        risk_signals = list(ranked["riskSignals"])
        if len(eligible_items) < 3:
            risk_signals.append(
                {
                    "key": "insufficient_comparables",
                    "severity": "warning",
                    "detail": (
                        "Fewer than three eligible awarded or complete projects were available, "
                        "so numeric recommendations were suppressed."
                    ),
                }
            )
        if len(actual_variance_values) < 3:
            risk_signals.append(
                {
                    "key": "insufficient_actuals_history",
                    "severity": "info",
                    "detail": (
                        "Fewer than three complete projects had trustworthy actuals, so "
                        "actual-informed guidance is limited."
                    ),
                }
            )

        return {
            "target": {
                "projectId": target_snapshot["id"],
                "projectName": target_snapshot["projectName"],
                "quoteCurrencyCode": target_snapshot["quoteCurrencyCode"],
                "quoteVersionId": target_quote_version.id if target_quote_version else None,
            },
            "scoringModelVersion": SCORING_MODEL_VERSION,
            "overallQuoteRange": overall_quote_range,
            "overallActualInformedRange": overall_actual_informed_range,
            "disciplineRanges": sorted(
                discipline_ranges, key=lambda item: int(item["sampleSize"]), reverse=True
            ),
            "comparablesUsed": [item["projectId"] for item in eligible_items],
            "riskSignals": risk_signals,
            "methodologySummary": (
                "Quotes use weighted comparable ranges from issued won work. "
                "Actual-informed guidance only uses complete projects with approved actuals."
            ),
        }

    def update_selection(
        self,
        session: Session,
        project_id: str,
        *,
        pinned_project_ids: list[str],
        excluded_project_ids: list[str],
        note: str | None,
        actor_id: str,
    ) -> dict[str, Any]:
        target_project = self._get_project_entity(session, project_id)
        candidate_projects = self._list_candidate_projects(session, project_id)
        candidate_projects_by_id = {candidate.id: candidate for candidate in candidate_projects}
        target_snapshot, _ = self._build_project_snapshot(target_project)

        unknown_project_ids = sorted(
            {
                project_id_value
                for project_id_value in [*pinned_project_ids, *excluded_project_ids]
                if project_id_value not in candidate_projects_by_id
            }
        )
        if unknown_project_ids:
            raise ApiProblemException(
                status_code=422,
                title="Invalid Comparable Selection",
                detail=(
                    "Comparable selection contains project ids that are not in the candidate set: "
                    + ", ".join(unknown_project_ids)
                ),
            )

        overlapping_project_ids = sorted(set(pinned_project_ids) & set(excluded_project_ids))
        if overlapping_project_ids:
            raise ApiProblemException(
                status_code=422,
                title="Invalid Comparable Selection",
                detail=(
                    "A project cannot be pinned and excluded at the same time: "
                    + ", ".join(overlapping_project_ids)
                ),
            )

        before = {
            "pinnedProjectIds": sorted(
                [
                    link.comparable_project_id
                    for link in target_project.comparable_source_links
                    if link.disposition == ComparableProjectLinkDisposition.pinned
                ]
            ),
            "excludedProjectIds": sorted(
                [
                    link.comparable_project_id
                    for link in target_project.comparable_source_links
                    if link.disposition == ComparableProjectLinkDisposition.excluded
                ]
            ),
            "note": next(
                (
                    link.note
                    for link in target_project.comparable_source_links
                    if link.note is not None
                ),
                None,
            ),
        }

        pinned = [
            project_id_value
            for project_id_value in _unique_strings(pinned_project_ids)
            if project_id_value not in excluded_project_ids
        ]
        excluded = _unique_strings(excluded_project_ids)

        session.execute(
            delete(ComparableProjectLink).where(ComparableProjectLink.project_id == project_id)
        )

        for comparable_project_id, disposition in (
            [(candidate_id, ComparableProjectLinkDisposition.pinned) for candidate_id in pinned]
            + [
                (candidate_id, ComparableProjectLinkDisposition.excluded)
                for candidate_id in excluded
            ]
        ):
            candidate_snapshot, _ = self._build_project_snapshot(
                candidate_projects_by_id[comparable_project_id]
            )
            score = _score_project(target_snapshot, candidate_snapshot)
            session.add(
                ComparableProjectLink(
                    project_id=project_id,
                    comparable_project_id=comparable_project_id,
                    disposition=disposition,
                    score=score["similarityScore"],
                    note=note,
                    created_by_id=actor_id,
                    scoring_model_version=SCORING_MODEL_VERSION,
                    reasons_json={
                        "matchedFactors": score["matchedFactors"],
                        "coveragePct": score["coveragePct"],
                        "strength": score["strength"],
                    },
                )
            )

        session.flush()
        updated_at = datetime.now(UTC).isoformat()
        after = {
            "pinnedProjectIds": pinned,
            "excludedProjectIds": excluded,
            "note": note,
        }
        audit_service.record(
            session,
            action="project.comparables.selection.updated",
            entity_type="project",
            entity_id=project_id,
            actor_id=actor_id,
            project_id=project_id,
            summary=f"Updated comparable-project selection for {target_project.name}.",
            before=before,
            after=after,
        )
        return {
            **after,
            "updatedAt": updated_at,
        }


comparable_service = ComparableService()
