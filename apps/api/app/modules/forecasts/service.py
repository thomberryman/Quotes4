from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.datetimes import same_timestamp
from app.core.errors import ApiProblemException
from app.models import (
    Forecast,
    ForecastLine,
    ForecastVersion,
    MonthlyForecastAllocation,
    Project,
    ProjectOutcome,
    ProjectScheduleRange,
    Quote,
    QuoteLineItem,
    QuoteSection,
    QuoteVersion,
)
from app.models.enums import (
    ForecastAllocationMethod,
    ForecastVersionStatus,
    ProjectOutcomeType,
)
from app.modules.audit.service import audit_service
from app.modules.forecasts.schemas import (
    ForecastDetailRead,
    ForecastDisciplineMonthlyRollupRead,
    ForecastLineAllocationsReplaceRequest,
    ForecastLineMonthAllocationWrite,
    ForecastLineRead,
    ForecastMonthlyAllocationRead,
    ForecastProjectMonthlyRollupRead,
    ForecastVersionCreateRequest,
    ForecastVersionRead,
    ForecastVersionSummaryRead,
    ForecastVersionUpdateRequest,
)


def _to_cents(amount: float) -> int:
    return round(amount * 100)


def _from_cents(amount_in_cents: int) -> float:
    return amount_in_cents / 100


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _month_date(month: str) -> date:
    year_text, month_text = month.split("-", maxsplit=1)
    return date(int(year_text), int(month_text), 1)


def _first_day_next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _last_day_of_month(value: date) -> date:
    return _first_day_next_month(value) - timedelta(days=1)


def _diff_days_inclusive(start_date: date, end_date: date) -> int:
    return (end_date - start_date).days + 1


def _normalize_probability(bucket: str, requested_probability: float | None) -> float:
    if requested_probability is not None and (
        requested_probability < 0 or requested_probability > 100
    ):
        raise ApiProblemException(
            422,
            "Forecast probability percent must be between 0 and 100.",
            "Invalid Forecast Probability",
        )

    if bucket == "awarded":
        return 100.0

    if bucket == "lost":
        return 0.0

    return round(requested_probability if requested_probability is not None else 100.0, 2)


def _sort_with_remainder(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        items,
        key=lambda item: (-float(item["remainder"]), str(item["sort_key"])),
    )


def _build_schedule_monthly_allocations(
    start_date: date, end_date: date, amount_in_cents: int
) -> list[tuple[str, int]]:
    if end_date < start_date:
        raise ApiProblemException(
            422,
            "Schedule range end date cannot be earlier than start date.",
            "Invalid Schedule Range",
        )

    total_days = _diff_days_inclusive(start_date, end_date)
    current_start = start_date
    allocations: list[dict[str, object]] = []

    while current_start <= end_date:
        current_end = min(_last_day_of_month(current_start), end_date)
        days_in_slice = _diff_days_inclusive(current_start, current_end)
        raw_amount = (amount_in_cents * days_in_slice) / total_days
        floor_amount = int(raw_amount // 1)
        allocations.append(
            {
                "month": _month_key(current_start),
                "floor_amount": floor_amount,
                "remainder": raw_amount - floor_amount,
                "sort_key": _month_key(current_start),
            }
        )
        current_start = _first_day_next_month(current_start)

    remainder = amount_in_cents - sum(int(item["floor_amount"]) for item in allocations)
    for item in _sort_with_remainder(allocations):
        if remainder <= 0:
            break
        item["floor_amount"] = int(item["floor_amount"]) + 1
        remainder -= 1

    return [
        (str(item["month"]), int(item["floor_amount"]))
        for item in sorted(allocations, key=lambda item: str(item["month"]))
    ]


def _build_weighted_allocations(
    allocations: list[tuple[str, int]], probability_percent: float
) -> list[tuple[str, int, int]]:
    factor = probability_percent / 100
    total_weighted_cents = round(sum(amount for _, amount in allocations) * factor)
    weighted: list[dict[str, object]] = []

    for month, amount_in_cents in allocations:
        raw_weighted = amount_in_cents * factor
        floor_weighted = int(raw_weighted // 1)
        weighted.append(
            {
                "month": month,
                "amount_in_cents": amount_in_cents,
                "floor_weighted": floor_weighted,
                "remainder": raw_weighted - floor_weighted,
                "sort_key": month,
            }
        )

    remainder = total_weighted_cents - sum(int(item["floor_weighted"]) for item in weighted)
    for item in _sort_with_remainder(weighted):
        if remainder <= 0:
            break
        item["floor_weighted"] = int(item["floor_weighted"]) + 1
        remainder -= 1

    return [
        (str(item["month"]), int(item["amount_in_cents"]), int(item["floor_weighted"]))
        for item in sorted(weighted, key=lambda item: str(item["month"]))
    ]


def _allocate_month_weights(
    total_amount_in_cents: int,
    month_amounts: list[tuple[str, float]],
) -> list[tuple[str, int]]:
    total_weight = sum(amount for _, amount in month_amounts)
    if total_amount_in_cents <= 0 or total_weight <= 0:
        return []
    weighted: list[dict[str, object]] = []
    for month, amount in month_amounts:
        raw_amount = total_amount_in_cents * (amount / total_weight)
        floor_amount = int(raw_amount // 1)
        weighted.append(
            {
                "month": month,
                "floor_amount": floor_amount,
                "remainder": raw_amount - floor_amount,
                "sort_key": month,
            }
        )
    remainder = total_amount_in_cents - sum(int(item["floor_amount"]) for item in weighted)
    for item in _sort_with_remainder(weighted):
        if remainder <= 0:
            break
        item["floor_amount"] = int(item["floor_amount"]) + 1
        remainder -= 1
    return [
        (str(item["month"]), int(item["floor_amount"]))
        for item in sorted(weighted, key=lambda item: str(item["month"]))
    ]


def _validate_manual_allocations(
    expected_amount_in_cents: int, allocations: list[ForecastLineMonthAllocationWrite]
) -> tuple[list[tuple[str, int]], list[str]]:
    issues: list[str] = []
    seen_months: set[str] = set()
    normalized: list[tuple[str, int]] = []

    for allocation in sorted(allocations, key=lambda item: item.month):
        if len(allocation.month) != 7 or allocation.month[4] != "-":
            issues.append(f"Invalid month format: {allocation.month}")
        if allocation.amount < 0:
            issues.append(f"Negative manual allocation is not allowed: {allocation.month}")
        if allocation.month in seen_months:
            issues.append(f"Duplicate manual allocation month: {allocation.month}")
        seen_months.add(allocation.month)
        normalized.append((allocation.month, _to_cents(allocation.amount)))

    total_amount_in_cents = sum(amount for _, amount in normalized)
    if total_amount_in_cents != expected_amount_in_cents:
        issues.append(
            "Manual allocations total "
            f"{_from_cents(total_amount_in_cents):.2f} but expected "
            f"{_from_cents(expected_amount_in_cents):.2f}"
        )

    return normalized, issues


@dataclass
class OutcomeSeed:
    outcome_type: str
    effective_at: datetime


@dataclass
class ScheduleRangeSeed:
    id: str
    label: str
    start_date: date
    end_date: date
    discipline_id: str | None = None
    allocation_percent: float | None = None


@dataclass
class QuoteLineSeed:
    id: str
    label: str
    discipline_id: str | None
    amount_in_cents: int
    currency_code: str


@dataclass
class ForecastLineSeed:
    label: str
    total_amount_in_cents: int
    currency_code: str
    allocation_method: str
    discipline_id: str | None = None
    schedule_range_id: str | None = None
    source_quote_line_item_id: str | None = None
    notes: str | None = None
    manual_allocations: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class ProjectSeed:
    id: str
    status: str
    current_quote_version_id: str | None
    outcomes: list[OutcomeSeed]
    schedule_ranges: list[ScheduleRangeSeed]
    quote_lines: list[QuoteLineSeed]


class ForecastService:
    def get_project_forecast(self, session: Session, project_id: str) -> ForecastDetailRead:
        project = self._get_project_seed(session, project_id)
        forecast = self._get_or_create_forecast(session, project_id)
        return self._build_forecast_detail(session, project, forecast)

    def get_version(self, session: Session, version_id: str) -> ForecastVersionRead:
        _forecast, project, version = self._get_version_context(session, version_id)
        return self._build_version_read(session, project, version)

    def create_or_clone_version(
        self,
        session: Session,
        project_id: str,
        payload: ForecastVersionCreateRequest,
        *,
        actor_id: str,
    ) -> ForecastVersionRead:
        project = self._get_project_seed(session, project_id)
        forecast = self._get_or_create_forecast(session, project_id)
        existing_draft = self._find_draft(session, forecast.id)
        if existing_draft is not None:
            if payload.base_version_id is None or payload.base_version_id == existing_draft.id:
                before = self._build_version_read(
                    session,
                    project,
                    existing_draft,
                ).model_dump(mode="json")
                existing_draft.title = payload.title or existing_draft.title
                existing_draft.notes_text = payload.notes_text or existing_draft.notes_text
                existing_draft.revision_reason = (
                    payload.revision_reason or existing_draft.revision_reason
                )
                existing_draft.outcome_type_snapshot = self._resolve_bucket(project)
                existing_draft.probability_percent = _normalize_probability(
                    existing_draft.outcome_type_snapshot,
                    payload.probability_percent
                    if payload.probability_percent is not None
                    else float(existing_draft.probability_percent),
                )
                existing_draft.updated_at = datetime.now(UTC)
                forecast.current_version_id = existing_draft.id
                self._sync_version_total(session, existing_draft)
                after = self._build_version_read(
                    session,
                    project,
                    existing_draft,
                ).model_dump(mode="json")
                audit_service.record(
                    session,
                    action="forecast.draft.reused",
                    entity_type="forecast_version",
                    entity_id=existing_draft.id,
                    actor_id=actor_id,
                    project_id=project.id,
                    summary=(
                        f"Reused editable draft v{existing_draft.version_number} "
                        f"for {project.id}."
                    ),
                    before=before,
                    after=after,
                    metadata={
                        "reusedDraftId": existing_draft.id,
                        "sourceQuoteVersionId": existing_draft.source_quote_version_id,
                    },
                )
                return ForecastVersionRead.model_validate(after)
            raise ApiProblemException(
                409,
                "A draft forecast already exists for this project.",
                "Draft Already Exists",
            )

        parent_version: ForecastVersion | None = None
        if payload.base_version_id is not None:
            parent_version = self._get_version_entity(session, payload.base_version_id)
            if parent_version.forecast_id != forecast.id:
                raise ApiProblemException(
                    422,
                    "Base forecast version must belong to the project forecast.",
                    "Invalid Forecast Version",
                )

        latest_version_number = session.scalar(
            select(ForecastVersion.version_number)
            .where(ForecastVersion.forecast_id == forecast.id)
            .order_by(desc(ForecastVersion.version_number))
            .limit(1)
        )
        outcome_type_snapshot = self._resolve_bucket(project)
        version = ForecastVersion(
            forecast_id=forecast.id,
            parent_version_id=parent_version.id if parent_version is not None else None,
            version_number=(latest_version_number or 0) + 1,
            status=ForecastVersionStatus.draft,
            title=payload.title,
            notes_text=payload.notes_text,
            outcome_type_snapshot=ProjectOutcomeType(outcome_type_snapshot),
            probability_percent=_normalize_probability(
                outcome_type_snapshot,
                payload.probability_percent,
            ),
            source_quote_version_id=project.current_quote_version_id,
            revision_reason=payload.revision_reason,
            total_amount=0,
            created_by_id=actor_id,
        )
        session.add(version)
        session.flush()

        if parent_version is not None:
            self._clone_lines(session, parent_version, version)
        else:
            self._seed_lines_from_quote(session, version, project)

        self._sync_version_total(session, version)
        forecast.current_version_id = version.id
        session.flush()
        after = self._build_version_read(session, project, version).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.version.created",
            entity_type="forecast_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Created forecast draft v{version.version_number} for {project.id}.",
            after=after,
            metadata={
                "baseVersionId": payload.base_version_id,
                "sourceQuoteVersionId": version.source_quote_version_id,
                "isSourceQuoteCurrent": self._version_source_is_current(project, version),
            },
        )
        return ForecastVersionRead.model_validate(after)

    def promote_prediction_scenario(
        self,
        session: Session,
        project_id: str,
        scenario_output: dict[str, object],
        *,
        title: str | None,
        notes_text: str | None,
        revision_reason: str | None,
        probability_percent: float | None,
        actor_id: str,
    ) -> ForecastVersionRead:
        created_version = self.create_or_clone_version(
            session,
            project_id,
            ForecastVersionCreateRequest(
                base_version_id=None,
                title=title or f"{scenario_output.get('title', 'Scenario')} Forecast",
                notes_text=notes_text
                or f"Promoted from predictive scenario {scenario_output.get('scenarioKey', 'base')}.",
                probability_percent=probability_percent,
                revision_reason=revision_reason
                or f"Promoted from predictive scenario {scenario_output.get('scenarioKey', 'base')}.",
            ),
            actor_id=actor_id,
        )
        forecast, project, version = self._get_version_context(session, created_version.id)
        self._assert_mutable(version, created_version.updated_at)

        line_ids = list(
            session.scalars(
                select(ForecastLine.id).where(ForecastLine.forecast_version_id == version.id)
            )
        )
        if line_ids:
            session.execute(
                delete(MonthlyForecastAllocation).where(
                    MonthlyForecastAllocation.forecast_line_id.in_(line_ids)
                )
            )
        session.execute(delete(ForecastLine).where(ForecastLine.forecast_version_id == version.id))
        session.flush()

        discipline_usage = scenario_output.get("disciplineUsage")
        monthly_revenue_spread = scenario_output.get("monthlyRevenueSpread")
        if not isinstance(discipline_usage, list) or not isinstance(monthly_revenue_spread, list):
            raise ApiProblemException(
                422,
                "Scenario output does not contain a usable discipline or monthly revenue structure.",
                "Invalid Prediction Scenario",
            )

        project_month_amounts = [
            (
                str(item["month"]),
                float(item.get("predictedAmountMedian") or 0),
            )
            for item in monthly_revenue_spread
            if item.get("month")
        ]
        project_total = sum(amount for _, amount in project_month_amounts)
        currency_code = "GBP"
        likely_quote_range = scenario_output.get("likelyQuoteRange")
        if isinstance(likely_quote_range, dict) and isinstance(
            likely_quote_range.get("currencyCode"), str
        ):
            currency_code = str(likely_quote_range["currencyCode"])

        created_count = 0
        for sort_order, item in enumerate(discipline_usage, start=1):
            line_total = (
                float(item.get("predictedActualAmount"))
                if item.get("predictedActualAmount") is not None
                else float(item.get("predictedAmountMedian") or 0)
            )
            if line_total <= 0:
                continue
            label = (
                item.get("disciplineName")
                or item.get("disciplineCode")
                or item.get("disciplineId")
                or f"Scenario line {sort_order}"
            )
            line = ForecastLine(
                forecast_version_id=version.id,
                sort_order=sort_order,
                discipline_id=item.get("disciplineId"),
                source_quote_line_item_id=None,
                schedule_range_id=None,
                label=str(label),
                allocation_method=ForecastAllocationMethod.manual,
                total_amount=line_total,
                currency_code=currency_code,
                notes=f"Promoted from predictive scenario {scenario_output.get('scenarioKey', 'base')}.",
            )
            session.add(line)
            session.flush()
            line_allocations = _allocate_month_weights(
                _to_cents(line_total),
                project_month_amounts if project_total > 0 else [],
            )
            for month, amount_in_cents in line_allocations:
                session.add(
                    MonthlyForecastAllocation(
                        forecast_line_id=line.id,
                        month=_month_date(month),
                        amount=_from_cents(amount_in_cents),
                        manual_note="Promoted from predictive scenario",
                    )
                )
            created_count += 1

        if created_count == 0 and project_total > 0:
            line = ForecastLine(
                forecast_version_id=version.id,
                sort_order=1,
                discipline_id=None,
                source_quote_line_item_id=None,
                schedule_range_id=None,
                label=str(scenario_output.get("title") or "Scenario revenue"),
                allocation_method=ForecastAllocationMethod.manual,
                total_amount=project_total,
                currency_code=currency_code,
                notes="Promoted from predictive scenario without discipline breakdown.",
            )
            session.add(line)
            session.flush()
            for month, amount_in_cents in _allocate_month_weights(
                _to_cents(project_total),
                project_month_amounts,
            ):
                session.add(
                    MonthlyForecastAllocation(
                        forecast_line_id=line.id,
                        month=_month_date(month),
                        amount=_from_cents(amount_in_cents),
                        manual_note="Promoted from predictive scenario",
                    )
                )

        version.updated_at = datetime.now(UTC)
        forecast.current_version_id = version.id
        self._sync_version_total(session, version)
        session.flush()
        audit_service.record(
            session,
            action="forecast.prediction.promoted",
            entity_type="forecast_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Promoted predictive scenario into forecast draft v{version.version_number}.",
            metadata={
                "scenarioKey": scenario_output.get("scenarioKey"),
                "createdLineCount": created_count,
            },
        )
        return self._build_version_read(session, project, version)

    def update_version(
        self,
        session: Session,
        version_id: str,
        payload: ForecastVersionUpdateRequest,
        *,
        actor_id: str,
    ) -> ForecastVersionRead:
        forecast, project, version = self._get_version_context(session, version_id)
        self._assert_mutable(version, payload.expected_updated_at)
        before = self._build_version_read(session, project, version).model_dump(mode="json")
        if payload.title is not None:
            version.title = payload.title
        if payload.notes_text is not None:
            version.notes_text = payload.notes_text
        if payload.revision_reason is not None:
            version.revision_reason = payload.revision_reason
        version.outcome_type_snapshot = ProjectOutcomeType(self._resolve_bucket(project))
        version.probability_percent = _normalize_probability(
            version.outcome_type_snapshot.value,
            payload.probability_percent
            if payload.probability_percent is not None
            else float(version.probability_percent),
        )
        version.updated_at = datetime.now(UTC)
        forecast.current_version_id = version.id
        session.flush()
        after = self._build_version_read(session, project, version).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.version.updated",
            entity_type="forecast_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Updated draft v{version.version_number} for {project.id}.",
            before=before,
            after=after,
            metadata={
                "sourceQuoteVersionId": version.source_quote_version_id,
                "isSourceQuoteCurrent": self._version_source_is_current(project, version),
            },
        )
        return ForecastVersionRead.model_validate(after)

    def replace_line_allocations(
        self,
        session: Session,
        line_id: str,
        payload: ForecastLineAllocationsReplaceRequest,
        *,
        actor_id: str,
    ) -> ForecastVersionRead:
        line = session.get(ForecastLine, line_id)
        if line is None:
            raise ApiProblemException(
                404,
                "Forecast line was not found.",
                "Forecast Line Not Found",
            )
        forecast, project, version = self._get_version_context(session, line.forecast_version_id)
        self._assert_mutable(version, payload.expected_updated_at)
        before = self._build_line_read(
            session,
            project,
            line,
            float(version.probability_percent),
        ).model_dump(mode="json")

        if payload.allocation_method not in {"manual", "schedule"}:
            raise ApiProblemException(
                422,
                "Forecast allocation method must be schedule or manual.",
                "Invalid Forecast Allocation Method",
            )

        session.execute(
            delete(MonthlyForecastAllocation).where(
                MonthlyForecastAllocation.forecast_line_id == line.id
            )
        )

        if payload.allocation_method == "manual":
            normalized_allocations, issues = _validate_manual_allocations(
                _to_cents(float(line.total_amount)),
                payload.allocations,
            )
            if issues:
                raise ApiProblemException(
                    422,
                    "; ".join(issues),
                    "Invalid Manual Allocations",
                )
            line.allocation_method = ForecastAllocationMethod.manual
            if "schedule_range_id" in payload.model_fields_set:
                line.schedule_range_id = payload.schedule_range_id
            for month, amount_in_cents in normalized_allocations:
                session.add(
                    MonthlyForecastAllocation(
                        forecast_line_id=line.id,
                        month=_month_date(month),
                        amount=_from_cents(amount_in_cents),
                        manual_note=payload.reason,
                    )
                )
        else:
            line.allocation_method = ForecastAllocationMethod.schedule
            if "schedule_range_id" in payload.model_fields_set:
                if payload.schedule_range_id is not None:
                    self._ensure_schedule_range(session, payload.schedule_range_id)
                line.schedule_range_id = payload.schedule_range_id

        if payload.reason is not None:
            line.notes = self._append_reason(line.notes, payload.reason)

        version.outcome_type_snapshot = ProjectOutcomeType(self._resolve_bucket(project))
        version.probability_percent = _normalize_probability(
            version.outcome_type_snapshot.value,
            float(version.probability_percent),
        )
        version.updated_at = datetime.now(UTC)
        forecast.current_version_id = version.id
        self._sync_version_total(session, version)
        session.flush()
        after = self._build_line_read(
            session,
            project,
            line,
            float(version.probability_percent),
        ).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.line.allocations.replaced",
            entity_type="forecast_line",
            entity_id=line.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Replaced allocations for forecast line {line.label} in {project.id}.",
            before=before,
            after=after,
            metadata={
                "forecastVersionId": version.id,
                "allocationMethod": line.allocation_method.value,
                "reason": payload.reason,
                "scheduleRangeId": line.schedule_range_id,
            },
        )
        return self._build_version_read(session, project, version)

    def submit_version(
        self, session: Session, version_id: str, *, actor_id: str
    ) -> ForecastVersionRead:
        forecast, project, version = self._get_version_context(session, version_id)
        if version.status != ForecastVersionStatus.draft:
            raise ApiProblemException(
                409,
                "Only draft forecast versions can be submitted.",
                "Invalid Forecast Version Transition",
            )
        before = self._build_version_read(session, project, version).model_dump(mode="json")
        computed = self._build_version_read(session, project, version)
        if computed.issues:
            raise ApiProblemException(
                409,
                "Forecast version has validation issues and cannot be submitted.",
                "Forecast Version Invalid",
            )
        version.status = ForecastVersionStatus.submitted
        version.submitted_by_id = actor_id
        version.submitted_at = datetime.now(UTC)
        version.updated_at = datetime.now(UTC)
        forecast.current_version_id = version.id
        session.flush()
        after = self._build_version_read(session, project, version).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.version.submitted",
            entity_type="forecast_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Submitted forecast v{version.version_number} for {project.id}.",
            before=before,
            after=after,
        )
        return ForecastVersionRead.model_validate(after)

    def lock_version(
        self, session: Session, version_id: str, *, actor_id: str
    ) -> ForecastVersionRead:
        forecast, project, version = self._get_version_context(session, version_id)
        if version.status not in {ForecastVersionStatus.draft, ForecastVersionStatus.submitted}:
            raise ApiProblemException(
                409,
                "Only draft or submitted forecast versions can be locked.",
                "Invalid Forecast Version Transition",
            )
        before = self._build_version_read(session, project, version).model_dump(mode="json")
        computed = self._build_version_read(session, project, version)
        if computed.issues:
            raise ApiProblemException(
                409,
                "Forecast version has validation issues and cannot be locked.",
                "Forecast Version Invalid",
            )
        if forecast.current_version_id is not None and forecast.current_version_id != version.id:
            previous = session.get(ForecastVersion, forecast.current_version_id)
            if previous is not None:
                previous.status = ForecastVersionStatus.superseded
                previous.updated_at = datetime.now(UTC)
        version.status = ForecastVersionStatus.locked
        version.locked_by_id = actor_id
        version.locked_at = datetime.now(UTC)
        version.updated_at = datetime.now(UTC)
        forecast.current_version_id = version.id
        session.flush()
        after = self._build_version_read(session, project, version).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.version.locked",
            entity_type="forecast_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Locked forecast v{version.version_number} for {project.id}.",
            before=before,
            after=after,
        )
        return ForecastVersionRead.model_validate(after)

    def record_recalculation_request(
        self, session: Session, project_id: str, *, actor_id: str
    ) -> None:
        project = self._get_project_seed(session, project_id)
        forecast = self._get_or_create_forecast(session, project_id)
        if forecast.current_version_id is None:
            return
        current_version = session.get(ForecastVersion, forecast.current_version_id)
        if current_version is None:
            return
        current_version.outcome_type_snapshot = ProjectOutcomeType(self._resolve_bucket(project))
        current_version.probability_percent = _normalize_probability(
            current_version.outcome_type_snapshot.value,
            float(current_version.probability_percent),
        )
        current_version.updated_at = datetime.now(UTC)
        session.flush()
        audit_service.record(
            session,
            action="forecast.recalculate.requested",
            entity_type="project",
            entity_id=project_id,
            actor_id=actor_id,
            project_id=project_id,
            summary=f"Queued forecast recalculation for {project_id}.",
            metadata={
                "forecastVersionId": current_version.id,
                "sourceQuoteVersionId": current_version.source_quote_version_id,
                "currentQuoteVersionId": project.current_quote_version_id,
            },
        )

    def recalculate_project(
        self, session: Session, project_id: str, *, actor_id: str
    ) -> tuple[ForecastVersionRead | None, str]:
        project = self._get_project_seed(session, project_id)
        forecast = self._get_or_create_forecast(session, project_id)

        target_version = None
        created_new_version = False
        recalculation_message = "Recalculated the current draft forecast."
        current_version = (
            session.get(ForecastVersion, forecast.current_version_id)
            if forecast.current_version_id is not None
            else None
        )

        if current_version is None:
            target_version = self.create_or_clone_version(
                session,
                project_id,
                ForecastVersionCreateRequest(
                    title="Forecast Draft",
                    revision_reason="Created during forecast recalculation.",
                ),
                actor_id=actor_id,
            )
            return target_version, "Created the initial draft forecast during recalculation."

        if current_version.status != ForecastVersionStatus.draft:
            existing_draft = self._find_draft(session, forecast.id)
            if existing_draft is not None:
                current_version = existing_draft
                recalculation_message = (
                    "Reused the existing draft forecast and recalculated schedule-driven lines."
                )
            else:
                rebase_from_quote = not self._version_source_is_current(project, current_version)
                target_version = self.create_or_clone_version(
                    session,
                    project_id,
                    ForecastVersionCreateRequest(
                        base_version_id=None if rebase_from_quote else current_version.id,
                        title=current_version.title,
                        notes_text=current_version.notes_text,
                        probability_percent=float(current_version.probability_percent),
                        revision_reason=(
                            "Recalculated from the current quote version."
                            if rebase_from_quote
                            else "Recalculated from the current forecast version."
                        ),
                    ),
                    actor_id=actor_id,
                )
                created_new_version = True
                recalculation_message = (
                    (
                        "Created a new draft from the current quote because "
                        "the active forecast was not editable."
                    )
                    if rebase_from_quote
                    else (
                        "Created a new editable draft and recalculated "
                        "schedule-driven lines."
                    )
                )
                current_version = self._get_version_entity(session, target_version.id)
                project = self._get_project_seed(session, project_id)

        before = self._build_version_read(session, project, current_version).model_dump(mode="json")
        preserve_manual_lines = self._version_source_is_current(project, current_version)
        if not preserve_manual_lines:
            recalculation_message = (
                "Rebased the draft forecast onto the current quote version during recalculation."
            )
        manual_line_count = self._rebuild_draft_lines(
            session,
            project,
            current_version,
            preserve_manual_lines=preserve_manual_lines,
        )
        forecast.current_version_id = current_version.id
        session.flush()
        after = self._build_version_read(session, project, current_version).model_dump(mode="json")
        audit_service.record(
            session,
            action="forecast.version.recalculated",
            entity_type="forecast_version",
            entity_id=current_version.id,
            actor_id=actor_id,
            project_id=project_id,
            summary=(
                f"Recalculated forecast v{current_version.version_number} for {project_id}."
            ),
            before=before,
            after=after,
            metadata={
                "createdNewVersion": created_new_version,
                "preservedManualLines": preserve_manual_lines,
                "manualLineCount": manual_line_count,
                "sourceQuoteVersionId": current_version.source_quote_version_id,
                "currentQuoteVersionId": project.current_quote_version_id,
            },
        )
        return ForecastVersionRead.model_validate(after), recalculation_message

    def _get_project_seed(self, session: Session, project_id: str) -> ProjectSeed:
        project = session.get(Project, project_id)
        if project is None:
            raise ApiProblemException(404, "Project was not found.", "Project Not Found")

        outcomes = [
            OutcomeSeed(outcome_type=outcome.outcome_type.value, effective_at=outcome.effective_at)
            for outcome in session.scalars(
                select(ProjectOutcome)
                .where(ProjectOutcome.project_id == project.id)
                .order_by(ProjectOutcome.effective_at)
            )
        ]
        schedule_ranges = [
            ScheduleRangeSeed(
                id=item.id,
                label=item.label,
                start_date=item.start_date,
                end_date=item.end_date,
                discipline_id=item.discipline_id,
                allocation_percent=float(item.allocation_percent)
                if item.allocation_percent is not None
                else None,
            )
            for item in session.scalars(
                select(ProjectScheduleRange)
                .where(ProjectScheduleRange.project_id == project.id)
                .order_by(ProjectScheduleRange.start_date)
            )
        ]

        current_quote_version_id = None
        quote_lines: list[QuoteLineSeed] = []
        current_quote = session.scalar(
            select(Quote)
            .where(Quote.project_id == project.id)
            .order_by(desc(Quote.updated_at))
            .limit(1)
        )
        if current_quote is not None:
            current_quote_version_id = current_quote.current_version_id
        if current_quote_version_id is not None:
            sections = list(
                session.scalars(
                    select(QuoteSection)
                    .where(QuoteSection.quote_version_id == current_quote_version_id)
                    .order_by(QuoteSection.sort_order)
                )
            )
            for section in sections:
                line_items = list(
                    session.scalars(
                        select(QuoteLineItem)
                        .where(QuoteLineItem.quote_section_id == section.id)
                        .order_by(QuoteLineItem.sort_order)
                    )
                )
                for item in line_items:
                    quote_lines.append(
                        QuoteLineSeed(
                            id=item.id,
                            label=item.description,
                            discipline_id=item.discipline_id,
                            amount_in_cents=_to_cents(float(item.amount)),
                            currency_code=self._quote_currency_code(
                                session,
                                current_quote_version_id,
                            ),
                        )
                    )

        return ProjectSeed(
            id=project.id,
            status=project.status.value,
            current_quote_version_id=current_quote_version_id,
            outcomes=outcomes,
            schedule_ranges=schedule_ranges,
            quote_lines=quote_lines,
        )

    def _quote_currency_code(self, session: Session, quote_version_id: str) -> str:
        version = session.get(QuoteVersion, quote_version_id)
        if version is None:
            return "GBP"
        return version.currency_code

    def _get_or_create_forecast(self, session: Session, project_id: str) -> Forecast:
        existing = session.scalar(select(Forecast).where(Forecast.project_id == project_id))
        if existing is not None:
            return existing
        forecast = Forecast(project_id=project_id)
        session.add(forecast)
        session.flush()
        return forecast

    def _find_draft(self, session: Session, forecast_id: str) -> ForecastVersion | None:
        return session.scalar(
            select(ForecastVersion)
            .where(
                ForecastVersion.forecast_id == forecast_id,
                ForecastVersion.status == ForecastVersionStatus.draft,
            )
            .order_by(desc(ForecastVersion.version_number))
            .limit(1)
        )

    def _version_source_is_current(self, project: ProjectSeed, version: ForecastVersion) -> bool:
        return version.source_quote_version_id == project.current_quote_version_id

    def _resolve_bucket(self, project: ProjectSeed) -> str:
        if project.status == "lost":
            return "lost"
        terminal_outcomes = [
            outcome
            for outcome in project.outcomes
            if outcome.outcome_type != "bid"
        ]
        terminal_outcomes.sort(key=lambda outcome: outcome.effective_at, reverse=True)
        if terminal_outcomes:
            return terminal_outcomes[0].outcome_type
        if project.status in {"awarded", "active", "complete"}:
            return "awarded"
        return "bid"

    def _resolve_schedule_ranges(
        self, project: ProjectSeed, discipline_id: str | None, schedule_range_id: str | None
    ) -> tuple[list[ScheduleRangeSeed], list[str]]:
        if schedule_range_id is not None:
            matching_range = next(
                (item for item in project.schedule_ranges if item.id == schedule_range_id),
                None,
            )
            if matching_range is None:
                return [], [f"Schedule range {schedule_range_id} was not found."]
            return [matching_range], []

        if discipline_id is None:
            return [], ["Schedule line requires a discipline."]

        discipline_ranges = [
            item for item in project.schedule_ranges if item.discipline_id == discipline_id
        ]
        if not discipline_ranges:
            discipline_ranges = [
                item for item in project.schedule_ranges if item.discipline_id is None
            ]
        if not discipline_ranges:
            return [], ["No schedule ranges were found for this line."]
        if len(discipline_ranges) == 1:
            return discipline_ranges, []
        if any(item.allocation_percent is None for item in discipline_ranges):
            return [], ["Schedule ranges need allocation percentages to split a line."]
        total_percent = round(sum(item.allocation_percent or 0 for item in discipline_ranges), 2)
        if total_percent != 100:
            return [], ["Schedule range percentages must total 100."]
        ordered = sorted(discipline_ranges, key=lambda item: item.start_date)
        for index in range(1, len(ordered)):
            if ordered[index].start_date <= ordered[index - 1].end_date:
                return [], ["Schedule ranges overlap and cannot be auto-spread."]
        return ordered, []

    def _split_amounts_for_ranges(
        self, total_amount_in_cents: int, ranges: list[ScheduleRangeSeed]
    ) -> list[tuple[ScheduleRangeSeed, int]]:
        if len(ranges) == 1:
            return [(ranges[0], total_amount_in_cents)]

        total_percent = sum(range_item.allocation_percent or 0 for range_item in ranges)
        if total_percent <= 0:
            raise ApiProblemException(
                422,
                "Schedule ranges need positive allocation percentages to split a line.",
                "Invalid Schedule Range",
            )

        weighted: list[dict[str, object]] = []
        for range_item in ranges:
            percent = range_item.allocation_percent or 0
            raw_amount = (total_amount_in_cents * percent) / total_percent
            floor_amount = int(raw_amount // 1)
            weighted.append(
                {
                    "range": range_item,
                    "floor_amount": floor_amount,
                    "remainder": raw_amount - floor_amount,
                    "sort_key": range_item.id,
                }
            )

        remainder = total_amount_in_cents - sum(int(item["floor_amount"]) for item in weighted)
        for item in _sort_with_remainder(weighted):
            if remainder <= 0:
                break
            item["floor_amount"] = int(item["floor_amount"]) + 1
            remainder -= 1

        return [
            (item["range"], int(item["floor_amount"]))  # type: ignore[index]
            for item in weighted
        ]

    def _build_manual_seed_from_line(
        self, session: Session, line: ForecastLine
    ) -> ForecastLineSeed:
        allocations = [
            (_month_key(allocation.month), _to_cents(float(allocation.amount)))
            for allocation in session.scalars(
                select(MonthlyForecastAllocation)
                .where(MonthlyForecastAllocation.forecast_line_id == line.id)
                .order_by(MonthlyForecastAllocation.month)
            )
        ]
        total_amount_in_cents = sum(amount for _, amount in allocations)
        if total_amount_in_cents == 0:
            total_amount_in_cents = _to_cents(float(line.total_amount))

        return ForecastLineSeed(
            label=line.label,
            total_amount_in_cents=total_amount_in_cents,
            currency_code=line.currency_code,
            allocation_method=ForecastAllocationMethod.manual.value,
            discipline_id=line.discipline_id,
            schedule_range_id=line.schedule_range_id,
            source_quote_line_item_id=line.source_quote_line_item_id,
            notes=line.notes,
            manual_allocations=allocations,
        )

    def _build_seed_line_label(
        self,
        quote_label: str,
        range_item: ScheduleRangeSeed | None,
        *,
        show_range_label: bool,
    ) -> str:
        if range_item is None or not show_range_label:
            return quote_label

        return f"{quote_label} - {range_item.label}"

    def _build_unresolved_schedule_seed(
        self,
        quote_line: QuoteLineSeed,
        *,
        total_amount_in_cents: int | None = None,
    ) -> ForecastLineSeed:
        return ForecastLineSeed(
            label=quote_line.label,
            total_amount_in_cents=(
                quote_line.amount_in_cents
                if total_amount_in_cents is None
                else total_amount_in_cents
            ),
            currency_code=quote_line.currency_code,
            allocation_method=ForecastAllocationMethod.schedule.value,
            discipline_id=quote_line.discipline_id,
            source_quote_line_item_id=quote_line.id,
        )

    def _build_schedule_seed_lines(
        self,
        quote_line: QuoteLineSeed,
        ranges: list[ScheduleRangeSeed],
        *,
        total_amount_in_cents: int | None = None,
        show_range_labels: bool | None = None,
    ) -> list[ForecastLineSeed]:
        schedule_amount = (
            quote_line.amount_in_cents
            if total_amount_in_cents is None
            else total_amount_in_cents
        )
        include_range_labels = len(ranges) > 1 if show_range_labels is None else show_range_labels
        return [
            ForecastLineSeed(
                label=self._build_seed_line_label(
                    quote_line.label,
                    range_item,
                    show_range_label=include_range_labels,
                ),
                total_amount_in_cents=split_amount,
                currency_code=quote_line.currency_code,
                allocation_method=ForecastAllocationMethod.schedule.value,
                discipline_id=quote_line.discipline_id,
                schedule_range_id=range_item.id,
                source_quote_line_item_id=quote_line.id,
            )
            for range_item, split_amount in self._split_amounts_for_ranges(
                schedule_amount,
                ranges,
            )
        ]

    def _rebuild_draft_lines(
        self,
        session: Session,
        project: ProjectSeed,
        version: ForecastVersion,
        *,
        preserve_manual_lines: bool,
    ) -> int:
        existing_lines = list(
            session.scalars(
                select(ForecastLine)
                .where(ForecastLine.forecast_version_id == version.id)
                .order_by(ForecastLine.sort_order)
            )
        )
        manual_line_seeds: dict[str, list[ForecastLineSeed]] = {}
        orphan_manual_line_seeds: list[ForecastLineSeed] = []
        manual_line_count = 0

        if preserve_manual_lines:
            for line in existing_lines:
                if line.allocation_method != ForecastAllocationMethod.manual:
                    continue
                manual_line_count += 1
                seed = self._build_manual_seed_from_line(session, line)
                if line.source_quote_line_item_id is not None:
                    manual_line_seeds.setdefault(line.source_quote_line_item_id, []).append(seed)
                else:
                    orphan_manual_line_seeds.append(seed)

        existing_line_ids = [line.id for line in existing_lines]
        if existing_line_ids:
            session.execute(
                delete(MonthlyForecastAllocation).where(
                    MonthlyForecastAllocation.forecast_line_id.in_(existing_line_ids)
                )
            )
            session.execute(
                delete(ForecastLine).where(ForecastLine.forecast_version_id == version.id)
            )
            session.flush()

        refreshed_lines: list[ForecastLineSeed] = []
        for quote_line in project.quote_lines:
            ranges, issues = self._resolve_schedule_ranges(project, quote_line.discipline_id, None)
            preserved_manual_seeds = manual_line_seeds.pop(quote_line.id, [])

            if preserved_manual_seeds:
                range_lookup = {range_item.id: range_item for range_item in ranges}
                manual_total_amount_in_cents = 0
                manual_range_ids = {
                    seed.schedule_range_id
                    for seed in preserved_manual_seeds
                    if seed.schedule_range_id is not None
                }

                for seed in preserved_manual_seeds:
                    matching_range = (
                        range_lookup.get(seed.schedule_range_id)
                        if seed.schedule_range_id is not None
                        else None
                    )
                    seed.label = self._build_seed_line_label(
                        quote_line.label,
                        matching_range,
                        show_range_label=len(ranges) > 1,
                    )
                    seed.currency_code = quote_line.currency_code
                    seed.discipline_id = quote_line.discipline_id
                    refreshed_lines.append(seed)
                    manual_total_amount_in_cents += seed.total_amount_in_cents

                remaining_amount_in_cents = (
                    quote_line.amount_in_cents - manual_total_amount_in_cents
                )
                if remaining_amount_in_cents <= 0:
                    continue

                if issues:
                    refreshed_lines.append(
                        self._build_unresolved_schedule_seed(
                            quote_line,
                            total_amount_in_cents=remaining_amount_in_cents,
                        )
                    )
                    continue

                remaining_ranges = [
                    range_item
                    for range_item in ranges
                    if range_item.id not in manual_range_ids
                ]
                if not remaining_ranges:
                    refreshed_lines.append(
                        self._build_unresolved_schedule_seed(
                            quote_line,
                            total_amount_in_cents=remaining_amount_in_cents,
                        )
                    )
                    continue

                refreshed_lines.extend(
                    self._build_schedule_seed_lines(
                        quote_line,
                        remaining_ranges,
                        total_amount_in_cents=remaining_amount_in_cents,
                        show_range_labels=len(ranges) > 1,
                    )
                )
                continue

            if issues:
                refreshed_lines.append(self._build_unresolved_schedule_seed(quote_line))
                continue

            refreshed_lines.extend(self._build_schedule_seed_lines(quote_line, ranges))

        for seeds in manual_line_seeds.values():
            refreshed_lines.extend(seeds)
        refreshed_lines.extend(orphan_manual_line_seeds)
        self._persist_seed_lines(session, version, refreshed_lines)
        version.source_quote_version_id = project.current_quote_version_id
        version.outcome_type_snapshot = ProjectOutcomeType(self._resolve_bucket(project))
        version.probability_percent = _normalize_probability(
            version.outcome_type_snapshot.value,
            float(version.probability_percent),
        )
        version.updated_at = datetime.now(UTC)
        self._sync_version_total(session, version)
        session.flush()
        return manual_line_count

    def _seed_lines_from_quote(
        self, session: Session, version: ForecastVersion, project: ProjectSeed
    ) -> None:
        seeded_lines: list[ForecastLineSeed] = []
        for quote_line in project.quote_lines:
            ranges, issues = self._resolve_schedule_ranges(project, quote_line.discipline_id, None)
            if issues:
                seeded_lines.append(self._build_unresolved_schedule_seed(quote_line))
                continue
            seeded_lines.extend(self._build_schedule_seed_lines(quote_line, ranges))
        self._persist_seed_lines(session, version, seeded_lines)

    def _persist_seed_lines(
        self, session: Session, version: ForecastVersion, lines: list[ForecastLineSeed]
    ) -> None:
        for index, item in enumerate(lines, start=1):
            line = ForecastLine(
                forecast_version_id=version.id,
                sort_order=index,
                discipline_id=item.discipline_id,
                source_quote_line_item_id=item.source_quote_line_item_id,
                schedule_range_id=item.schedule_range_id,
                label=item.label,
                allocation_method=ForecastAllocationMethod(item.allocation_method),
                total_amount=_from_cents(item.total_amount_in_cents),
                currency_code=item.currency_code,
                notes=item.notes,
            )
            session.add(line)
            session.flush()
            for month, amount_in_cents in item.manual_allocations:
                session.add(
                    MonthlyForecastAllocation(
                        forecast_line_id=line.id,
                        month=_month_date(month),
                        amount=_from_cents(amount_in_cents),
                    )
                )
        session.flush()

    def _clone_lines(
        self,
        session: Session,
        source_version: ForecastVersion,
        target_version: ForecastVersion,
    ) -> None:
        source_lines = list(
            session.scalars(
                select(ForecastLine)
                .where(ForecastLine.forecast_version_id == source_version.id)
                .order_by(ForecastLine.sort_order)
            )
        )
        for source_line in source_lines:
            cloned = ForecastLine(
                forecast_version_id=target_version.id,
                sort_order=source_line.sort_order,
                discipline_id=source_line.discipline_id,
                source_quote_line_item_id=source_line.source_quote_line_item_id,
                schedule_range_id=source_line.schedule_range_id,
                label=source_line.label,
                allocation_method=source_line.allocation_method,
                total_amount=source_line.total_amount,
                currency_code=source_line.currency_code,
                notes=source_line.notes,
            )
            session.add(cloned)
            session.flush()
            source_allocations = list(
                session.scalars(
                    select(MonthlyForecastAllocation)
                    .where(MonthlyForecastAllocation.forecast_line_id == source_line.id)
                    .order_by(MonthlyForecastAllocation.month)
                )
            )
            for allocation in source_allocations:
                session.add(
                    MonthlyForecastAllocation(
                        forecast_line_id=cloned.id,
                        month=allocation.month,
                        amount=allocation.amount,
                        manual_note=allocation.manual_note,
                    )
                )
        session.flush()

    def _sync_version_total(self, session: Session, version: ForecastVersion) -> None:
        total = sum(
            float(line.total_amount)
            for line in session.scalars(
                select(ForecastLine).where(ForecastLine.forecast_version_id == version.id)
            )
        )
        version.total_amount = total
        session.flush()

    def _assert_mutable(self, version: ForecastVersion, expected_updated_at: datetime) -> None:
        if version.status != ForecastVersionStatus.draft:
            raise ApiProblemException(
                409,
                "Only draft forecast versions can be edited.",
                "Forecast Version Not Editable",
            )
        if not same_timestamp(version.updated_at, expected_updated_at):
            raise ApiProblemException(
                409,
                "Forecast version has been updated by another request.",
                "Forecast Version Conflict",
            )

    def _get_version_context(
        self, session: Session, version_id: str
    ) -> tuple[Forecast, ProjectSeed, ForecastVersion]:
        version = self._get_version_entity(session, version_id)
        forecast = session.get(Forecast, version.forecast_id)
        if forecast is None:
            raise ApiProblemException(404, "Forecast was not found.", "Forecast Not Found")
        project = self._get_project_seed(session, forecast.project_id)
        return forecast, project, version

    def _get_version_entity(self, session: Session, version_id: str) -> ForecastVersion:
        version = session.get(ForecastVersion, version_id)
        if version is None:
            raise ApiProblemException(
                404,
                "Forecast version was not found.",
                "Forecast Version Not Found",
            )
        return version

    def _build_line_read(
        self,
        session: Session,
        project: ProjectSeed,
        line: ForecastLine,
        probability_percent: float,
    ) -> ForecastLineRead:
        issues: list[str] = []
        base_allocations: list[tuple[str, int]] = []
        line_total_cents = _to_cents(float(line.total_amount))

        if line.allocation_method == ForecastAllocationMethod.manual:
            stored_allocations = [
                ForecastLineMonthAllocationWrite(
                    month=_month_key(allocation.month),
                    amount=float(allocation.amount),
                )
                for allocation in session.scalars(
                    select(MonthlyForecastAllocation)
                    .where(MonthlyForecastAllocation.forecast_line_id == line.id)
                    .order_by(MonthlyForecastAllocation.month)
                )
            ]
            base_allocations, issues = _validate_manual_allocations(
                line_total_cents,
                stored_allocations,
            )
        else:
            ranges, range_issues = self._resolve_schedule_ranges(
                project,
                line.discipline_id,
                line.schedule_range_id,
            )
            if range_issues:
                issues.extend(range_issues)
            elif len(ranges) != 1:
                issues.append("Schedule line must resolve to exactly one schedule range.")
            else:
                range_item = ranges[0]
                base_allocations = _build_schedule_monthly_allocations(
                    range_item.start_date,
                    range_item.end_date,
                    line_total_cents,
                )

        weighted_allocations = _build_weighted_allocations(base_allocations, probability_percent)
        allocations = [
            ForecastMonthlyAllocationRead(
                month=month,
                amount=_from_cents(amount_in_cents),
                weighted_amount=_from_cents(weighted_amount_in_cents),
            )
            for month, amount_in_cents, weighted_amount_in_cents in weighted_allocations
        ]

        return ForecastLineRead(
            id=line.id,
            source_line_id=line.source_quote_line_item_id or line.id,
            label=line.label,
            total_amount=_from_cents(sum(amount for _, amount in base_allocations)),
            weighted_total_amount=_from_cents(
                sum(weighted_amount for _, _, weighted_amount in weighted_allocations)
            ),
            currency_code=line.currency_code,
            allocation_method=line.allocation_method.value,
            discipline_id=line.discipline_id,
            schedule_range_id=line.schedule_range_id,
            notes=line.notes,
            issues=issues,
            allocations=allocations,
        )

    def _build_version_read(
        self, session: Session, project: ProjectSeed, version: ForecastVersion
    ) -> ForecastVersionRead:
        version.outcome_type_snapshot = ProjectOutcomeType(self._resolve_bucket(project))
        version.probability_percent = _normalize_probability(
            version.outcome_type_snapshot.value,
            float(version.probability_percent),
        )
        line_models = list(
            session.scalars(
                select(ForecastLine)
                .where(ForecastLine.forecast_version_id == version.id)
                .order_by(ForecastLine.sort_order)
            )
        )
        line_reads = [
            self._build_line_read(session, project, line, float(version.probability_percent))
            for line in line_models
        ]
        issues = [issue for line in line_reads for issue in line.issues]
        if version.source_quote_version_id is None:
            issues.append("Forecast version is not linked to a source quote version.")
        elif not self._version_source_is_current(project, version):
            issues.append(
                "Forecast source quote version is no longer current. "
                "Recalculate or create a new draft from the current quote."
            )

        discipline_rollups: dict[tuple[str | None, str], dict[str, float]] = {}
        project_rollups: dict[str, dict[str, float]] = {}
        for line in line_reads:
            for allocation in line.allocations:
                discipline_key = (line.discipline_id, allocation.month)
                if discipline_key not in discipline_rollups:
                    discipline_rollups[discipline_key] = {"amount": 0, "weighted_amount": 0}
                discipline_rollups[discipline_key]["amount"] += allocation.amount
                discipline_rollups[discipline_key]["weighted_amount"] += allocation.weighted_amount
                if allocation.month not in project_rollups:
                    project_rollups[allocation.month] = {"amount": 0, "weighted_amount": 0}
                project_rollups[allocation.month]["amount"] += allocation.amount
                project_rollups[allocation.month]["weighted_amount"] += allocation.weighted_amount

        discipline_monthly_rollups = [
            ForecastDisciplineMonthlyRollupRead(
                discipline_id=discipline_id,
                month=month,
                amount=round(values["amount"], 2),
                weighted_amount=round(values["weighted_amount"], 2),
            )
            for (discipline_id, month), values in sorted(
                discipline_rollups.items(),
                key=lambda item: ((item[0][0] or ""), item[0][1]),
            )
        ]
        project_monthly_rollups = [
            ForecastProjectMonthlyRollupRead(
                month=month,
                amount=round(values["amount"], 2),
                weighted_amount=round(values["weighted_amount"], 2),
            )
            for month, values in sorted(project_rollups.items(), key=lambda item: item[0])
        ]
        total_amount = round(sum(line.total_amount for line in line_reads), 2)
        weighted_total_amount = round(sum(line.weighted_total_amount for line in line_reads), 2)
        return ForecastVersionRead(
            id=version.id,
            forecast_id=version.forecast_id,
            version_number=version.version_number,
            status=version.status.value,
            title=version.title,
            notes_text=version.notes_text,
            outcome_type_snapshot=version.outcome_type_snapshot.value,
            probability_percent=float(version.probability_percent),
            total_amount=total_amount,
            weighted_total_amount=weighted_total_amount,
            source_quote_version_id=version.source_quote_version_id,
            is_source_quote_current=self._version_source_is_current(project, version),
            revision_reason=version.revision_reason,
            parent_version_id=version.parent_version_id,
            created_at=version.created_at,
            updated_at=version.updated_at,
            issues=issues,
            lines=line_reads,
            discipline_monthly_rollups=discipline_monthly_rollups,
            project_monthly_rollups=project_monthly_rollups,
        )

    def _build_forecast_detail(
        self, session: Session, project: ProjectSeed, forecast: Forecast
    ) -> ForecastDetailRead:
        versions = list(
            session.scalars(
                select(ForecastVersion)
                .where(ForecastVersion.forecast_id == forecast.id)
                .order_by(ForecastVersion.version_number)
            )
        )
        version_reads = [
            self._build_version_read(session, project, version)
            for version in versions
        ]
        version_summaries = [
            ForecastVersionSummaryRead(
                id=version.id,
                forecast_id=version.forecast_id,
                version_number=version.version_number,
                status=version.status,
                title=version.title,
                outcome_type_snapshot=version.outcome_type_snapshot,
                probability_percent=version.probability_percent,
                total_amount=version.total_amount,
                weighted_total_amount=version.weighted_total_amount,
                source_quote_version_id=version.source_quote_version_id,
                is_source_quote_current=version.is_source_quote_current,
                created_at=version.created_at,
                updated_at=version.updated_at,
            )
            for version in version_reads
        ]
        current_version_read = next(
            (version for version in version_reads if version.id == forecast.current_version_id),
            None,
        )
        return ForecastDetailRead(
            forecast_id=forecast.id,
            project_id=project.id,
            current_version_id=forecast.current_version_id,
            versions=version_summaries,
            current_version=current_version_read,
        )

    def _ensure_schedule_range(self, session: Session, schedule_range_id: str) -> None:
        if session.get(ProjectScheduleRange, schedule_range_id) is None:
            raise ApiProblemException(
                422,
                f"Schedule range '{schedule_range_id}' was not found.",
                "Invalid Schedule Range",
            )

    def _append_reason(
        self, existing: str | None, reason: str | None, *, prefix: str = "Manual override"
    ) -> str | None:
        if reason is None:
            return existing
        suffix = f"{prefix}: {reason}"
        if existing:
            return f"{existing}\n{suffix}"
        return suffix


forecast_service = ForecastService()
