# ruff: noqa: E501

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import StringIO
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ApiProblemException
from app.models import (
    Discipline,
    Forecast,
    ForecastVersion,
    Project,
    ProjectBenchmarkDisciplineSummary,
    ProjectBenchmarkSummary,
    ProjectDiscipline,
    ProjectParty,
    Quote,
)
from app.models.enums import ProjectPartyRole
from app.modules.dashboards.schemas import (
    AwardedLostMonthPoint,
    AwardedLostTrendSection,
    BenchmarkDisciplineSummary,
    BenchmarkOverviewSection,
    ClientHistorySummary,
    ClientProjectHistorySection,
    ConfidenceBandSummary,
    DashboardAppliedFilters,
    DashboardDrilldownColumn,
    DashboardDrilldownResponse,
    DashboardFilterOptions,
    DashboardOption,
    DashboardSummaryCard,
    DisciplineRevenueSeries,
    DisciplineRevenueTrendsSection,
    DisciplineTrendPoint,
    ForecastConfidenceSection,
    ForecastRevenueDashboardSection,
    ForecastRevenueDisciplineRow,
    ForecastRevenueMonthStatusPoint,
    ForecastRevenueProjectMonthValue,
    ForecastRevenueProjectRow,
    ForecastRevenueStatusTotal,
    MonthlyRevenueForecastSection,
    OperationalDashboardResponse,
    PipelineStageSummary,
    QuoteActualVarianceSection,
    RevenueMonthPoint,
    SalesPipelineSection,
    VarianceBucketSummary,
)
from app.modules.forecasts.service import forecast_service

STATUS_LABELS = {
    "bid": "Bid",
    "awarded": "Awarded",
    "active": "Active",
    "complete": "Complete",
    "lost": "Lost",
}

DISCIPLINE_LABELS = {
    "offline": "Offline",
    "online": "Online",
    "grade": "Grade",
    "sound": "Sound",
    "localization": "Localization",
    "production": "Production",
}

VIEW_TITLES = {
    "sales_pipeline": "Sales pipeline detail",
    "monthly_forecast": "Monthly revenue forecast detail",
    "awarded_lost": "Awarded vs lost trend detail",
    "variance": "Quote vs actual variance detail",
    "client_history": "Client and project history detail",
    "discipline_trends": "Discipline revenue trend detail",
    "forecast_confidence": "Forecast confidence detail",
    "benchmark_overview": "Comparable benchmark detail",
}

DEFAULT_REFERENCE_DATE = date(2026, 3, 31)
BOOKED_STATUSES = {"awarded", "active", "complete"}


@dataclass(frozen=True)
class BenchmarkDisciplineRecord:
    discipline_id: str
    discipline_name: str
    quoted_amount: float
    actual_amount: float

    @property
    def variance_amount(self) -> float:
        return round(self.actual_amount - self.quoted_amount, 2)

    @property
    def variance_pct(self) -> float | None:
        if self.quoted_amount <= 0:
            return None
        return round((self.actual_amount - self.quoted_amount) / self.quoted_amount * 100, 2)


@dataclass(frozen=True)
class BenchmarkRecord:
    quoted_amount: float
    actual_amount: float | None
    actuals_status: str
    actuals_as_of_date: str | None
    disciplines: tuple[BenchmarkDisciplineRecord, ...] = ()

    @property
    def variance_amount(self) -> float | None:
        if self.actual_amount is None:
            return None
        return round(self.actual_amount - self.quoted_amount, 2)

    @property
    def variance_pct(self) -> float | None:
        if self.actual_amount is None or self.quoted_amount <= 0:
            return None
        return round((self.actual_amount - self.quoted_amount) / self.quoted_amount * 100, 2)


@dataclass(frozen=True)
class DisciplineMonthRecord:
    month: str
    discipline_id: str
    discipline_name: str
    gross_amount: float
    weighted_amount: float
    low_amount: float
    high_amount: float
    actual_amount: float
    booked_amount: float


@dataclass(frozen=True)
class ProjectMonthRecord:
    month: str
    gross_amount: float
    weighted_amount: float
    actual_amount: float
    booked_amount: float


@dataclass(frozen=True)
class DisciplineDetailRecord:
    discipline_id: str
    discipline_name: str
    base_phasing_profile: str
    forecast_method: str
    line_count: int
    manual_override_line_count: int
    total_amount: float
    weighted_total_amount: float
    month_values: tuple[ProjectMonthRecord, ...]


@dataclass(frozen=True)
class OutcomeRecord:
    outcome_type: str
    effective_at: str


@dataclass(frozen=True)
class DashboardProjectRecord:
    id: str
    name: str
    client_id: str
    client_name: str
    status: str
    quote_amount: float
    probability_percent: float
    issues: tuple[str, ...]
    outcomes: tuple[OutcomeRecord, ...]
    disciplines: tuple[str, ...]
    monthly_values: tuple[DisciplineMonthRecord, ...]
    forecast_total_amount: float = 0.0
    forecast_weighted_total_amount: float = 0.0
    benchmark: BenchmarkRecord | None = None
    currency_code: str = "GBP"
    forecast_version_id: str | None = None
    forecast_status: str | None = None
    forecast_scenario_key: str | None = None
    forecast_confidence_score: float | None = None
    data_sufficiency_score: float | None = None
    fallback_tier: str | None = None
    project_monthly_values: tuple[ProjectMonthRecord, ...] = ()
    discipline_details: tuple[DisciplineDetailRecord, ...] = ()
    base_phasing_profile: str = "flat_equal"
    forecast_method: str = "none"
    manual_override_line_count: int = 0
    quote_entry_date: str | None = None
    execution_start_date: str | None = None
    execution_end_date: str | None = None
    quote_to_execution_lead_months: int | None = None
    change_summary: dict[str, object] | None = None
    explanation_summary: dict[str, object] | None = None

    @property
    def weighted_value(self) -> float:
        return round(sum(item.weighted_amount for item in self.monthly_values), 2)

    @property
    def booked_value(self) -> float:
        return round(sum(item.booked_amount for item in self.monthly_values), 2)

    @property
    def commercial_weighted_value(self) -> float:
        return round(self.quote_amount * (self.probability_percent / 100), 2)

    @property
    def commercial_booked_value(self) -> float:
        if self.status not in BOOKED_STATUSES:
            return 0.0
        return round(self.quote_amount, 2)

    @property
    def actuals_status(self) -> str:
        if self.benchmark is None:
            return "none"
        return self.benchmark.actuals_status

    @property
    def spanning_month_count(self) -> int:
        return len([item for item in self.project_monthly_values if item.gross_amount > 0])


@dataclass(frozen=True)
class DashboardFilters:
    from_month: str
    to_month: str
    client_id: str | None
    project_id: str | None
    discipline_id: str | None
    status: str | None
    scenario_key: str | None


def _benchmark(
    *,
    quoted_amount: float,
    actual_amount: float | None,
    actuals_status: str,
    actuals_as_of_date: str | None,
    disciplines: list[tuple[str, str, float, float]],
) -> BenchmarkRecord:
    return BenchmarkRecord(
        quoted_amount=quoted_amount,
        actual_amount=actual_amount,
        actuals_status=actuals_status,
        actuals_as_of_date=actuals_as_of_date,
        disciplines=tuple(
            BenchmarkDisciplineRecord(
                discipline_id=discipline_id,
                discipline_name=discipline_name,
                quoted_amount=quoted,
                actual_amount=actual,
            )
            for discipline_id, discipline_name, quoted, actual in disciplines
        ),
    )


def _monthly(
    month: str,
    discipline_id: str,
    gross_amount: float,
    weighted_amount: float,
) -> DisciplineMonthRecord:
    return DisciplineMonthRecord(
        month=month,
        discipline_id=discipline_id,
        discipline_name=DISCIPLINE_LABELS.get(discipline_id, discipline_id.title()),
        gross_amount=gross_amount,
        weighted_amount=weighted_amount,
        low_amount=gross_amount,
        high_amount=gross_amount,
        actual_amount=0.0,
        booked_amount=gross_amount,
    )


FIXTURE_PROJECTS: tuple[DashboardProjectRecord, ...] = (
    DashboardProjectRecord(
        id="project_red_room",
        name="Red Room Trailer Campaign",
        client_id="client_north_star",
        client_name="North Star Pictures",
        status="bid",
        quote_amount=115000,
        probability_percent=65,
        issues=("Awaiting client schedule confirmation.",),
        outcomes=(OutcomeRecord("bid", "2026-03-28"),),
        disciplines=("offline", "online", "sound"),
        monthly_values=(
            _monthly("2026-04", "offline", 22000, 14300),
            _monthly("2026-04", "online", 8000, 5200),
            _monthly("2026-05", "offline", 18000, 11700),
            _monthly("2026-05", "online", 22000, 14300),
            _monthly("2026-05", "sound", 15000, 9750),
            _monthly("2026-06", "online", 15000, 9750),
            _monthly("2026-06", "sound", 15000, 9750),
        ),
    ),
    DashboardProjectRecord(
        id="project_black_glass",
        name="Black Glass Series Launch",
        client_id="client_bbc",
        client_name="BBC Studios",
        status="complete",
        quote_amount=110000,
        probability_percent=100,
        issues=(),
        outcomes=(OutcomeRecord("awarded", "2025-10-10"),),
        disciplines=("offline", "online", "grade"),
        monthly_values=(
            _monthly("2025-10", "offline", 32000, 32000),
            _monthly("2025-11", "online", 38000, 38000),
            _monthly("2025-12", "grade", 40000, 40000),
        ),
        benchmark=_benchmark(
            quoted_amount=110000,
            actual_amount=118000,
            actuals_status="complete",
            actuals_as_of_date="2026-03-31",
            disciplines=[
                ("offline", "Offline", 42000, 45000),
                ("online", "Online", 38000, 41000),
                ("grade", "Grade", 30000, 32000),
            ],
        ),
    ),
    DashboardProjectRecord(
        id="project_north_passage",
        name="North Passage Promo Package",
        client_id="client_silverline",
        client_name="Silverline Media",
        status="complete",
        quote_amount=98000,
        probability_percent=100,
        issues=(),
        outcomes=(OutcomeRecord("awarded", "2025-11-14"),),
        disciplines=("offline", "online", "grade"),
        monthly_values=(
            _monthly("2025-12", "offline", 28000, 28000),
            _monthly("2026-01", "online", 35000, 35000),
            _monthly("2026-02", "grade", 35000, 35000),
        ),
        benchmark=_benchmark(
            quoted_amount=98000,
            actual_amount=104500,
            actuals_status="complete",
            actuals_as_of_date="2026-03-31",
            disciplines=[
                ("offline", "Offline", 39000, 41500),
                ("online", "Online", 33000, 35500),
                ("grade", "Grade", 26000, 27500),
            ],
        ),
    ),
    DashboardProjectRecord(
        id="project_silver_tide",
        name="Silver Tide Teaser Rollout",
        client_id="client_north_star",
        client_name="North Star Pictures",
        status="complete",
        quote_amount=122000,
        probability_percent=100,
        issues=(),
        outcomes=(OutcomeRecord("awarded", "2026-01-16"),),
        disciplines=("offline", "online", "grade"),
        monthly_values=(
            _monthly("2026-01", "offline", 42000, 42000),
            _monthly("2026-02", "online", 40000, 40000),
            _monthly("2026-03", "grade", 40000, 40000),
        ),
        benchmark=_benchmark(
            quoted_amount=122000,
            actual_amount=132000,
            actuals_status="complete",
            actuals_as_of_date="2026-03-31",
            disciplines=[
                ("offline", "Offline", 45000, 48500),
                ("online", "Online", 42000, 45500),
                ("grade", "Grade", 35000, 38000),
            ],
        ),
    ),
    DashboardProjectRecord(
        id="project_blue_echo",
        name="Blue Echo Spot Burst",
        client_id="client_aurora",
        client_name="Aurora Creative",
        status="complete",
        quote_amount=116000,
        probability_percent=100,
        issues=(),
        outcomes=(OutcomeRecord("awarded", "2026-02-08"),),
        disciplines=("offline", "online", "grade"),
        monthly_values=(
            _monthly("2026-02", "offline", 36000, 36000),
            _monthly("2026-03", "online", 40000, 40000),
            _monthly("2026-04", "grade", 40000, 40000),
        ),
        benchmark=_benchmark(
            quoted_amount=116000,
            actual_amount=128500,
            actuals_status="complete",
            actuals_as_of_date="2026-03-31",
            disciplines=[
                ("offline", "Offline", 43000, 48000),
                ("online", "Online", 40000, 44500),
                ("grade", "Grade", 33000, 36000),
            ],
        ),
    ),
    DashboardProjectRecord(
        id="project_global_cut",
        name="Global Cut International Promo",
        client_id="client_global_media",
        client_name="Global Media",
        status="active",
        quote_amount=130000,
        probability_percent=100,
        issues=("Localization handoff still needs final territory sign-off.", "Audio mix lock pending."),
        outcomes=(OutcomeRecord("awarded", "2026-03-05"),),
        disciplines=("online", "sound", "localization"),
        monthly_values=(
            _monthly("2026-03", "online", 30000, 30000),
            _monthly("2026-04", "sound", 30000, 30000),
            _monthly("2026-05", "localization", 40000, 40000),
            _monthly("2026-06", "localization", 30000, 30000),
        ),
        benchmark=_benchmark(
            quoted_amount=130000,
            actual_amount=54000,
            actuals_status="partial",
            actuals_as_of_date="2026-03-31",
            disciplines=[
                ("online", "Online", 50000, 23000),
                ("sound", "Sound", 35000, 17000),
                ("localization", "Localization", 45000, 14000),
            ],
        ),
    ),
    DashboardProjectRecord(
        id="project_amber_lane",
        name="Amber Lane Launch Spots",
        client_id="client_studio_east",
        client_name="Studio East",
        status="awarded",
        quote_amount=92000,
        probability_percent=100,
        issues=(),
        outcomes=(OutcomeRecord("awarded", "2026-03-18"),),
        disciplines=("offline", "online"),
        monthly_values=(
            _monthly("2026-04", "offline", 28000, 28000),
            _monthly("2026-05", "online", 32000, 32000),
            _monthly("2026-06", "online", 32000, 32000),
        ),
    ),
    DashboardProjectRecord(
        id="project_ember_fade",
        name="Ember Fade Pitch Package",
        client_id="client_north_star",
        client_name="North Star Pictures",
        status="lost",
        quote_amount=76000,
        probability_percent=0,
        issues=(
            "Budget ceiling was not aligned.",
            "Territory scope remained open.",
            "Audio review turnaround slipped.",
        ),
        outcomes=(OutcomeRecord("lost", "2026-03-22"),),
        disciplines=("offline", "production"),
        monthly_values=(
            _monthly("2026-03", "offline", 28000, 0),
            _monthly("2026-04", "production", 24000, 0),
            _monthly("2026-05", "production", 24000, 0),
        ),
    ),
)


class DashboardService:
    def get_operational_dashboard(
        self,
        session: Session,
        *,
        from_month: str | None,
        to_month: str | None,
        client_id: str | None,
        project_id: str | None,
        discipline_id: str | None,
        status: str | None,
        scenario_key: str | None,
    ) -> OperationalDashboardResponse:
        filters = self._normalize_filters(
            from_month=from_month,
            to_month=to_month,
            client_id=client_id,
            project_id=project_id,
            discipline_id=discipline_id,
            status=status,
            scenario_key=scenario_key,
        )
        forecast_dataset = forecast_service.get_dashboard_forecast_dataset(
            session,
            from_month=filters.from_month,
            to_month=filters.to_month,
            client_id=filters.client_id,
            project_id=filters.project_id,
            discipline_id=filters.discipline_id,
            status=filters.status,
            scenario_key=filters.scenario_key,
        )
        forecast_dataset_contract = forecast_service.to_dashboard_forecast_contract_dataset(
            forecast_dataset
        )
        projects = self._filtered_projects(
            session,
            filters,
            forecast_dataset=forecast_dataset,
        )
        return OperationalDashboardResponse(
            generated_at=datetime.now(UTC),
            applied_filters=DashboardAppliedFilters(**filters.__dict__),
            filter_options=self._build_filter_options(session),
            summary_cards=self._build_summary_cards(projects, filters),
            sales_pipeline=self._build_sales_pipeline(projects),
            forecast_dataset=forecast_dataset_contract,
            monthly_revenue_forecast=self._build_monthly_revenue_forecast(projects, filters),
            forecast_revenue=self._build_forecast_revenue(projects, filters),
            awarded_lost_trend=self._build_awarded_lost_trend(projects, filters),
            quote_actual_variance=self._build_quote_actual_variance(projects),
            client_project_history=self._build_client_project_history(projects),
            discipline_revenue_trends=self._build_discipline_revenue_trends(projects, filters),
            forecast_confidence=self._build_forecast_confidence(projects),
            benchmark_overview=self._build_benchmark_overview(projects),
        )

    def get_drilldown(
        self,
        session: Session,
        view: str,
        *,
        from_month: str | None,
        to_month: str | None,
        client_id: str | None,
        project_id: str | None,
        discipline_id: str | None,
        status: str | None,
        scenario_key: str | None,
    ) -> DashboardDrilldownResponse:
        filters = self._normalize_filters(
            from_month=from_month,
            to_month=to_month,
            client_id=client_id,
            project_id=project_id,
            discipline_id=discipline_id,
            status=status,
            scenario_key=scenario_key,
        )
        forecast_dataset = forecast_service.get_dashboard_forecast_dataset(
            session,
            from_month=filters.from_month,
            to_month=filters.to_month,
            client_id=filters.client_id,
            project_id=filters.project_id,
            discipline_id=filters.discipline_id,
            status=filters.status,
            scenario_key=filters.scenario_key,
        )
        projects = self._filtered_projects(
            session,
            filters,
            forecast_dataset=forecast_dataset,
        )

        if view == "sales_pipeline":
            return self._build_sales_pipeline_drilldown(projects)
        if view == "monthly_forecast":
            return self._build_monthly_forecast_drilldown(projects, filters)
        if view == "awarded_lost":
            return self._build_awarded_lost_drilldown(projects, filters)
        if view == "variance":
            return self._build_variance_drilldown(projects)
        if view == "client_history":
            return self._build_client_history_drilldown(projects)
        if view == "discipline_trends":
            return self._build_discipline_trends_drilldown(projects, filters)
        if view == "forecast_confidence":
            return self._build_forecast_confidence_drilldown(projects)
        if view == "benchmark_overview":
            return self._build_benchmark_overview_drilldown(projects)

        raise ApiProblemException(404, f"Dashboard view '{view}' was not found.", "Dashboard View Not Found")

    def render_csv(self, drilldown: DashboardDrilldownResponse) -> str:
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=[column.key for column in drilldown.columns])
        writer.writeheader()
        for row in drilldown.rows:
            writer.writerow({column.key: row.get(column.key) for column in drilldown.columns})
        return buffer.getvalue()

    def _build_filter_options(self, session: Session) -> DashboardFilterOptions:
        project_entities = list(
            session.scalars(
                select(Project).options(
                    selectinload(Project.parties).selectinload(ProjectParty.company),
                    selectinload(Project.disciplines).selectinload(ProjectDiscipline.discipline),
                )
            )
        )
        clients = sorted(
            {
                self._resolve_client(project)
                for project in project_entities
            },
            key=lambda item: item[1],
        )
        project_options = sorted(
            ((project.id, project.name) for project in project_entities),
            key=lambda item: item[1],
        )
        disciplines = sorted(
            {
                (
                    item.discipline_id,
                    item.discipline.name,
                )
                for project in project_entities
                for item in project.disciplines
                if item.discipline_id is not None and item.discipline is not None
            },
            key=lambda item: item[1],
        )
        scenario_keys = sorted(
            {
                value
                for value in session.scalars(select(ForecastVersion.scenario_key).distinct())
                if isinstance(value, str) and value
            }
            | {"base"}
        )
        statuses = [(status, label) for status, label in STATUS_LABELS.items()]
        return DashboardFilterOptions(
            clients=[DashboardOption(id=client_id, label=label) for client_id, label in clients],
            projects=[DashboardOption(id=project_id, label=label) for project_id, label in project_options],
            disciplines=[DashboardOption(id=discipline_id, label=label) for discipline_id, label in disciplines],
            statuses=[DashboardOption(id=status, label=label) for status, label in statuses],
            scenarios=[
                DashboardOption(id=key, label=STATUS_LABELS.get(key, key.replace("_", " ").title()))
                for key in scenario_keys
            ],
        )

    def _normalize_filters(
        self,
        *,
        from_month: str | None,
        to_month: str | None,
        client_id: str | None,
        project_id: str | None,
        discipline_id: str | None,
        status: str | None,
        scenario_key: str | None,
    ) -> DashboardFilters:
        default_from = self._offset_month(DEFAULT_REFERENCE_DATE, -5)
        default_to = self._offset_month(DEFAULT_REFERENCE_DATE, 6)
        normalized_from = from_month or default_from
        normalized_to = to_month or default_to
        start = self._parse_month(normalized_from)
        end = self._parse_month(normalized_to)
        if end < start:
            raise ApiProblemException(
                422,
                "Dashboard toMonth cannot be earlier than fromMonth.",
                "Invalid Dashboard Month Range",
            )
        if status is not None and status not in STATUS_LABELS:
            raise ApiProblemException(422, f"Unknown dashboard status '{status}'.", "Invalid Dashboard Status")
        return DashboardFilters(
            from_month=normalized_from,
            to_month=normalized_to,
            client_id=client_id,
            project_id=project_id,
            discipline_id=discipline_id,
            status=status,
            scenario_key=scenario_key or "base",
        )

    def _load_dashboard_projects(
        self,
        session: Session,
        *,
        forecast_dataset,
    ) -> list[DashboardProjectRecord]:
        project_entities = list(
            session.scalars(
                select(Project).options(
                    selectinload(Project.parties).selectinload(ProjectParty.company),
                    selectinload(Project.outcomes),
                    selectinload(Project.disciplines).selectinload(ProjectDiscipline.discipline),
                    selectinload(Project.quotes).selectinload(Quote.versions),
                    selectinload(Project.benchmark_summary)
                    .selectinload(ProjectBenchmarkSummary.discipline_summaries)
                    .selectinload(ProjectBenchmarkDisciplineSummary.discipline),
                )
            )
        )
        forecast_projects = {
            project.project_id: project
            for project in forecast_dataset.projects
        }
        records: list[DashboardProjectRecord] = []
        for project in project_entities:
            forecast_project = forecast_projects.get(project.id)
            if forecast_project is None:
                continue
            records.append(
                self._to_dashboard_project_record(
                    project,
                    forecast_project=forecast_project,
                )
            )
        return records

    def _filtered_projects(
        self,
        session: Session,
        filters: DashboardFilters,
        *,
        forecast_dataset,
    ) -> list[DashboardProjectRecord]:
        items = self._load_dashboard_projects(
            session,
            forecast_dataset=forecast_dataset,
        )
        if filters.client_id is not None:
            items = [project for project in items if project.client_id == filters.client_id]
        if filters.project_id is not None:
            items = [project for project in items if project.id == filters.project_id]
        if filters.discipline_id is not None:
            items = [
                project
                for project in items
                if filters.discipline_id in project.disciplines
            ]
        if filters.status is not None:
            items = [project for project in items if project.status == filters.status]
        return items

    def _currency_code(self, projects: list[DashboardProjectRecord]) -> str:
        return next(
            (project.currency_code for project in projects if project.currency_code),
            "GBP",
        )

    def _select_forecast_version(
        self,
        project: Project,
        *,
        scenario_key: str | None,
    ) -> ForecastVersion | None:
        forecast = project.forecast
        if forecast is None:
            return None
        versions = sorted(forecast.versions, key=lambda item: item.version_number, reverse=True)
        if not versions:
            return None
        normalized_scenario = scenario_key or "base"
        matching_version = next(
            (item for item in versions if item.scenario_key == normalized_scenario),
            None,
        )
        if matching_version is not None:
            return matching_version
        if normalized_scenario == "base":
            current_version = next(
                (item for item in versions if item.id == forecast.current_version_id),
                None,
            )
            if current_version is not None:
                return current_version
        return None

    def _resolve_client(self, project: Project) -> tuple[str, str]:
        primary_client = next(
            (
                party
                for party in project.parties
                if party.role == ProjectPartyRole.client and party.is_primary and party.company is not None
            ),
            None,
        )
        if primary_client is not None and primary_client.company is not None:
            return primary_client.company.id, primary_client.company.name
        fallback_client = next(
            (
                party
                for party in project.parties
                if party.role == ProjectPartyRole.client and party.company is not None
            ),
            None,
        )
        if fallback_client is not None and fallback_client.company is not None:
            return fallback_client.company.id, fallback_client.company.name
        return f"unknown-client-{project.id}", "Unknown client"

    def _resolve_quote_total(self, project: Project) -> tuple[float, str]:
        for quote in project.quotes:
            current_version = next(
                (item for item in quote.versions if item.id == quote.current_version_id),
                None,
            )
            if current_version is not None:
                return float(current_version.total_amount), current_version.currency_code
        if project.benchmark_summary is not None:
            return (
                float(project.benchmark_summary.quoted_amount),
                project.benchmark_summary.currency_code,
            )
        return 0.0, project.quote_currency_code or "GBP"

    def _month_window(self, filters: DashboardFilters) -> list[str]:
        months: list[str] = []
        current = self._parse_month(filters.from_month)
        end = self._parse_month(filters.to_month)
        while current <= end:
            months.append(f"{current.year:04d}-{current.month:02d}")
            current = self._parse_month(self._offset_month(current, 1))
        return months

    def _month_end(self, value: str) -> date:
        start = self._parse_month(value)
        next_month = self._parse_month(self._offset_month(start, 1))
        return date.fromordinal(next_month.toordinal() - 1)

    def _summarize_method_values(self, values: set[str]) -> str:
        normalized = {value for value in values if value}
        if not normalized:
            return "none"
        if len(normalized) == 1:
            return next(iter(normalized))
        return "mixed"

    def _resolve_quote_entry_date(self, project: Project) -> str | None:
        issued_dates: list[date] = []
        for quote in project.quotes:
            current_version = next(
                (item for item in quote.versions if item.id == quote.current_version_id),
                None,
            )
            if current_version is None:
                continue
            if current_version.issued_at is not None:
                issued_dates.append(current_version.issued_at.date())
            elif current_version.source_document_date is not None:
                issued_dates.append(current_version.source_document_date)
            else:
                issued_dates.append(current_version.created_at.date())
        if issued_dates:
            return max(issued_dates).isoformat()
        if project.bid_submitted_at is not None:
            return project.bid_submitted_at.date().isoformat()
        return None

    def _resolve_execution_window(
        self,
        project: Project,
        project_monthly_values: tuple[ProjectMonthRecord, ...],
    ) -> tuple[str | None, str | None]:
        return forecast_service.resolve_execution_window(
            project,
            month_values=[item.month for item in project_monthly_values if item.gross_amount > 0],
        )

    def _months_between(
        self,
        start_value: str | None,
        end_value: str | None,
    ) -> int | None:
        if start_value is None or end_value is None:
            return None
        start = date.fromisoformat(start_value)
        end = date.fromisoformat(end_value)
        return (end.year - start.year) * 12 + (end.month - start.month)

    def _build_project_monthly_values(
        self,
        version_read,
        *,
        project_status: str,
    ) -> tuple[ProjectMonthRecord, ...]:
        if version_read is None:
            return ()
        return tuple(
            ProjectMonthRecord(
                month=item.month,
                gross_amount=item.amount,
                weighted_amount=item.weighted_amount,
                actual_amount=item.actual_amount or 0.0,
                booked_amount=item.amount if project_status in BOOKED_STATUSES else 0.0,
            )
            for item in version_read.project_monthly_rollups
        )

    def _build_discipline_details(
        self,
        version_read,
        *,
        project_status: str,
        discipline_lookup: dict[str, tuple[str, str]],
        base_phasing_profile: str,
    ) -> tuple[DisciplineDetailRecord, ...]:
        if version_read is None:
            return ()

        grouped: dict[str, dict[str, object]] = {}
        for line in version_read.lines:
            discipline_id, discipline_name = discipline_lookup.get(
                line.discipline_id,
                ("unassigned", "Unassigned"),
            )
            bucket = grouped.setdefault(
                discipline_id,
                {
                    "discipline_name": discipline_name,
                    "forecast_methods": set(),
                    "line_count": 0,
                    "manual_override_line_count": 0,
                    "total_amount": 0.0,
                    "weighted_total_amount": 0.0,
                    "month_values": [],
                },
            )
            forecast_methods = bucket["forecast_methods"]
            if isinstance(forecast_methods, set):
                forecast_methods.add(line.forecast_method_key or "unknown")
            bucket["line_count"] = int(bucket["line_count"]) + 1
            has_manual_override = line.allocation_method == "manual" or any(
                allocation.allocation_source == "manual_override"
                for allocation in line.allocations
            )
            if has_manual_override:
                bucket["manual_override_line_count"] = (
                    int(bucket["manual_override_line_count"]) + 1
                )
            bucket["total_amount"] = float(bucket["total_amount"]) + line.total_amount
            bucket["weighted_total_amount"] = (
                float(bucket["weighted_total_amount"]) + line.weighted_total_amount
            )

        for rollup in version_read.discipline_monthly_rollups:
            discipline_id, discipline_name = discipline_lookup.get(
                rollup.discipline_id,
                ("unassigned", "Unassigned"),
            )
            bucket = grouped.setdefault(
                discipline_id,
                {
                    "discipline_name": discipline_name,
                    "forecast_methods": set(),
                    "line_count": 0,
                    "manual_override_line_count": 0,
                    "total_amount": 0.0,
                    "weighted_total_amount": 0.0,
                    "month_values": [],
                },
            )
            month_values = bucket["month_values"]
            if isinstance(month_values, list):
                month_values.append(
                    ProjectMonthRecord(
                        month=rollup.month,
                        gross_amount=rollup.amount,
                        weighted_amount=rollup.weighted_amount,
                        actual_amount=rollup.actual_amount or 0.0,
                        booked_amount=(
                            rollup.amount if project_status in BOOKED_STATUSES else 0.0
                        ),
                    )
                )

        return tuple(
            DisciplineDetailRecord(
                discipline_id=discipline_id,
                discipline_name=str(values["discipline_name"]),
                base_phasing_profile=base_phasing_profile,
                forecast_method=self._summarize_method_values(
                    set(values["forecast_methods"])
                ),
                line_count=int(values["line_count"]),
                manual_override_line_count=int(values["manual_override_line_count"]),
                total_amount=round(float(values["total_amount"]), 2),
                weighted_total_amount=round(float(values["weighted_total_amount"]), 2),
                month_values=tuple(
                    sorted(
                        list(values["month_values"]),
                        key=lambda item: item.month,
                    )
                ),
            )
            for discipline_id, values in sorted(
                grouped.items(),
                key=lambda item: (
                    -float(item[1]["total_amount"]),
                    str(item[1]["discipline_name"]),
                ),
            )
        )

    def _to_dashboard_project_record(
        self,
        project: Project,
        *,
        forecast_project,
    ) -> DashboardProjectRecord:
        client_id, client_name = self._resolve_client(project)
        currency_code = project.quote_currency_code or "GBP"
        quote_entry_date = self._resolve_quote_entry_date(project)
        project_monthly_values = tuple(
            ProjectMonthRecord(
                month=item.month,
                gross_amount=round(item.amount, 2),
                weighted_amount=round(item.weighted_amount, 2),
                actual_amount=round(item.actual_amount or 0.0, 2),
                booked_amount=round(item.booked_amount or 0.0, 2),
            )
            for item in sorted(forecast_project.project_months, key=lambda value: value.month)
        )
        base_phasing_profile = forecast_project.base_phasing_profile or "system_default"
        discipline_details = tuple(
            DisciplineDetailRecord(
                discipline_id=detail.discipline_id,
                discipline_name=detail.discipline_name,
                base_phasing_profile=base_phasing_profile,
                forecast_method=detail.allocation_method_used,
                line_count=detail.line_count,
                manual_override_line_count=detail.manual_override_line_count,
                total_amount=round(detail.total_amount, 2),
                weighted_total_amount=round(detail.weighted_total_amount, 2),
                month_values=tuple(
                    ProjectMonthRecord(
                        month=value.month,
                        gross_amount=round(value.amount, 2),
                        weighted_amount=round(value.weighted_amount, 2),
                        actual_amount=round(value.actual_amount or 0.0, 2),
                        booked_amount=round(value.booked_amount or 0.0, 2),
                    )
                    for value in sorted(detail.month_values, key=lambda item: item.month)
                ),
            )
            for detail in forecast_project.discipline_rows
        )
        monthly_values = tuple(
            DisciplineMonthRecord(
                month=value.month,
                discipline_id=detail.discipline_id,
                discipline_name=detail.discipline_name,
                gross_amount=round(value.gross_amount, 2),
                weighted_amount=round(value.weighted_amount, 2),
                low_amount=round(value.gross_amount, 2),
                high_amount=round(value.gross_amount, 2),
                actual_amount=round(value.actual_amount, 2),
                booked_amount=round(value.booked_amount, 2),
            )
            for detail in discipline_details
            for value in detail.month_values
        )
        benchmark = None
        if project.benchmark_summary is not None:
            benchmark = _benchmark(
                quoted_amount=float(project.benchmark_summary.quoted_amount),
                actual_amount=(
                    float(project.benchmark_summary.actual_amount)
                    if project.benchmark_summary.actual_amount is not None
                    else None
                ),
                actuals_status=project.benchmark_summary.actuals_status.value,
                actuals_as_of_date=(
                    project.benchmark_summary.actuals_as_of_date.isoformat()
                    if project.benchmark_summary.actuals_as_of_date is not None
                    else None
                ),
                disciplines=[
                    (
                        (
                            item.discipline.code
                            if item.discipline is not None
                            else item.discipline_id
                        ),
                        (
                            item.discipline.name
                            if item.discipline is not None
                            else item.discipline_id
                        ),
                        float(item.quoted_amount),
                        float(item.actual_amount or 0.0),
                    )
                    for item in project.benchmark_summary.discipline_summaries
                ],
            )
        return DashboardProjectRecord(
            id=project.id,
            name=project.name,
            client_id=forecast_project.client_id or client_id,
            client_name=forecast_project.client_name or client_name,
            currency_code=currency_code,
            status=forecast_project.operational_status,
            quote_amount=round(float(forecast_project.total_project_value), 2),
            forecast_total_amount=round(float(forecast_project.total_forecast_value), 2),
            forecast_weighted_total_amount=round(
                float(forecast_project.weighted_total_forecast_value),
                2,
            ),
            probability_percent=round(float(forecast_project.probability_percent), 2),
            forecast_version_id=forecast_project.forecast_version_id,
            forecast_status=forecast_project.forecast_status,
            forecast_scenario_key=forecast_project.scenario_key,
            forecast_confidence_score=forecast_project.confidence_score,
            data_sufficiency_score=forecast_project.data_sufficiency_score,
            fallback_tier=forecast_project.fallback_tier,
            project_monthly_values=project_monthly_values,
            discipline_details=discipline_details,
            base_phasing_profile=base_phasing_profile,
            forecast_method=forecast_project.allocation_method_used,
            manual_override_line_count=forecast_project.manual_override_line_count,
            quote_entry_date=quote_entry_date,
            execution_start_date=forecast_project.execution_start_date,
            execution_end_date=forecast_project.execution_end_date,
            quote_to_execution_lead_months=self._months_between(
                quote_entry_date,
                forecast_project.execution_start_date,
            ),
            change_summary=forecast_project.change_summary,
            explanation_summary=forecast_project.explanation_summary,
            issues=tuple(forecast_project.issues),
            outcomes=tuple(
                OutcomeRecord(
                    outcome_type=item.outcome_type.value,
                    effective_at=item.effective_at.isoformat(),
                )
                for item in sorted(project.outcomes, key=lambda outcome: outcome.effective_at)
            ),
            disciplines=tuple(sorted({item.discipline_id for item in monthly_values})),
            monthly_values=monthly_values,
            benchmark=benchmark,
        )

    def _build_summary_cards(
        self, projects: list[DashboardProjectRecord], filters: DashboardFilters
    ) -> list[DashboardSummaryCard]:
        pipeline_projects = [project for project in projects if project.status in {"bid", "awarded"}]
        pipeline_value = round(sum(project.quote_amount for project in pipeline_projects), 2)
        booked_forecast = round(
            sum(
                item.booked_amount
                for project in projects
                for item in project.monthly_values
                if self._month_in_window(item.month, filters)
            ),
            2,
        )
        weighted_forecast = round(
            sum(
                item.weighted_amount
                for project in projects
                for item in project.monthly_values
                if self._month_in_window(item.month, filters)
            ),
            2,
        )
        awarded_count = sum(1 for project in projects if project.status == "awarded")
        lost_count = sum(1 for project in projects if project.status == "lost")
        variance_values = [
            project.benchmark.variance_pct
            for project in projects
            if project.benchmark is not None
            and project.benchmark.actuals_status == "complete"
            and project.benchmark.variance_pct is not None
        ]
        median_variance = round(float(median(variance_values)), 2) if variance_values else None
        high_confidence_count = sum(
            1 for project in projects if self._confidence_band(self._confidence_score(project)) == "high"
        )
        return [
            DashboardSummaryCard(
                key="open_pipeline",
                label="Open Pipeline",
                value=self._format_currency(pipeline_value),
                detail=f"{len(pipeline_projects)} bid or awarded projects",
            ),
            DashboardSummaryCard(
                key="weighted_forecast",
                label="Weighted Forecast",
                value=self._format_currency(weighted_forecast),
                detail=f"{filters.from_month} to {filters.to_month}",
            ),
            DashboardSummaryCard(
                key="booked_forecast",
                label="Booked Forecast",
                value=self._format_currency(booked_forecast),
                detail="Operational forecast from awarded and in-flight work",
            ),
            DashboardSummaryCard(
                key="awarded_projects",
                label="Awarded Projects",
                value=str(awarded_count),
                detail="Current awarded projects in scope",
            ),
            DashboardSummaryCard(
                key="lost_projects",
                label="Lost Projects",
                value=str(lost_count),
                detail="Current lost projects in scope",
            ),
            DashboardSummaryCard(
                key="benchmark_median_variance",
                label="Benchmark Median Variance",
                value=self._format_percent(median_variance) if median_variance is not None else "N/A",
                detail="Complete benchmark actuals only",
            ),
            DashboardSummaryCard(
                key="high_confidence",
                label="High Confidence",
                value=str(high_confidence_count),
                detail="Projects scoring 75 or above",
            ),
        ]

    def _build_sales_pipeline(
        self, projects: list[DashboardProjectRecord]
    ) -> SalesPipelineSection:
        currency_code = self._currency_code(projects)
        stages: list[PipelineStageSummary] = []
        for status, label in STATUS_LABELS.items():
            stage_projects = [project for project in projects if project.status == status]
            stages.append(
                PipelineStageSummary(
                    status=status,
                    label=label,
                    project_count=len(stage_projects),
                    quote_amount=round(sum(project.quote_amount for project in stage_projects), 2),
                    weighted_amount=round(
                        sum(project.commercial_weighted_value for project in stage_projects),
                        2,
                    ),
                    booked_amount=round(
                        sum(project.commercial_booked_value for project in stage_projects),
                        2,
                    ),
                    currency_code=currency_code,
                )
            )
        return SalesPipelineSection(
            currency_code=currency_code,
            total_quote_amount=round(sum(project.quote_amount for project in projects), 2),
            total_weighted_amount=round(
                sum(project.commercial_weighted_value for project in projects),
                2,
            ),
            total_booked_amount=round(
                sum(project.commercial_booked_value for project in projects),
                2,
            ),
            stages=stages,
        )

    def _build_monthly_revenue_forecast(
        self,
        projects: list[DashboardProjectRecord],
        filters: DashboardFilters,
    ) -> MonthlyRevenueForecastSection:
        values_by_month: dict[str, dict[str, float]] = defaultdict(
            lambda: {
                "gross": 0.0,
                "weighted": 0.0,
                "low": 0.0,
                "high": 0.0,
                "actual": 0.0,
                "booked": 0.0,
            }
        )
        for project in projects:
            for item in project.monthly_values:
                if not self._month_in_window(item.month, filters):
                    continue
                values_by_month[item.month]["gross"] += item.gross_amount
                values_by_month[item.month]["weighted"] += item.weighted_amount
                values_by_month[item.month]["low"] += item.low_amount
                values_by_month[item.month]["high"] += item.high_amount
                values_by_month[item.month]["actual"] += item.actual_amount
                values_by_month[item.month]["booked"] += item.booked_amount
        months = [
            RevenueMonthPoint(
                month=month,
                gross_amount=round(values["gross"], 2),
                weighted_amount=round(values["weighted"], 2),
                low_amount=round(values["low"], 2),
                high_amount=round(values["high"], 2),
                actual_amount=round(values["actual"], 2),
                booked_amount=round(values["booked"], 2),
            )
            for month, values in sorted(values_by_month.items())
        ]
        return MonthlyRevenueForecastSection(
            currency_code=self._currency_code(projects),
            months=months,
        )

    def _build_forecast_revenue(
        self,
        projects: list[DashboardProjectRecord],
        filters: DashboardFilters,
    ) -> ForecastRevenueDashboardSection:
        months = self._month_window(filters)
        monthly_status_totals: dict[str, dict[str, float]] = {
            month: {
                "bid": 0.0,
                "weighted_bid": 0.0,
                "awarded": 0.0,
                "active": 0.0,
                "complete": 0.0,
                "booked": 0.0,
                "lost": 0.0,
            }
            for month in months
        }
        overall_status_totals: dict[str, dict[str, object]] = {
            status: {"project_ids": set(), "total_amount": 0.0, "weighted_total_amount": 0.0}
            for status in STATUS_LABELS
        }
        project_rows: list[ForecastRevenueProjectRow] = []

        for project in projects:
            month_lookup = {item.month: item for item in project.project_monthly_values}
            window_revenue = 0.0
            window_weighted_revenue = 0.0

            for month in months:
                item = month_lookup.get(month)
                if item is None:
                    continue
                window_revenue += item.gross_amount
                window_weighted_revenue += item.weighted_amount
                if project.status == "bid":
                    monthly_status_totals[month]["bid"] += item.gross_amount
                    monthly_status_totals[month]["weighted_bid"] += item.weighted_amount
                elif project.status == "awarded":
                    monthly_status_totals[month]["awarded"] += item.gross_amount
                    monthly_status_totals[month]["booked"] += item.booked_amount
                elif project.status == "active":
                    monthly_status_totals[month]["active"] += item.gross_amount
                    monthly_status_totals[month]["booked"] += item.booked_amount
                elif project.status == "complete":
                    monthly_status_totals[month]["complete"] += item.gross_amount
                    monthly_status_totals[month]["booked"] += item.booked_amount
                elif project.status == "lost":
                    monthly_status_totals[month]["lost"] += item.gross_amount

            status_bucket = overall_status_totals[project.status]
            project_ids = status_bucket["project_ids"]
            if isinstance(project_ids, set):
                project_ids.add(project.id)
            status_bucket["total_amount"] = (
                float(status_bucket["total_amount"]) + window_revenue
            )
            status_bucket["weighted_total_amount"] = (
                float(status_bucket["weighted_total_amount"]) + window_weighted_revenue
            )

            project_rows.append(
                ForecastRevenueProjectRow(
                    project_id=project.id,
                    project_name=project.name,
                    client_id=project.client_id,
                    client_name=project.client_name,
                    status=project.status,
                    quote_entry_date=project.quote_entry_date,
                    execution_start_date=project.execution_start_date,
                    execution_end_date=project.execution_end_date,
                    quote_to_execution_lead_months=project.quote_to_execution_lead_months,
                    spanning_month_count=project.spanning_month_count,
                    base_phasing_profile=project.base_phasing_profile,
                    forecast_method=project.forecast_method,
                    manual_override_line_count=project.manual_override_line_count,
                    total_revenue=round(project.forecast_total_amount, 2),
                    window_revenue=round(window_revenue, 2),
                    weighted_total_revenue=round(project.forecast_weighted_total_amount, 2),
                    window_weighted_revenue=round(window_weighted_revenue, 2),
                    forecast_version_id=project.forecast_version_id,
                    forecast_status=project.forecast_status,
                    scenario_key=project.forecast_scenario_key or "base",
                    change_summary=project.change_summary,
                    explanation_summary=project.explanation_summary,
                    month_values=[
                        ForecastRevenueProjectMonthValue(
                            month=month,
                            amount=round(month_lookup.get(month).gross_amount, 2)
                            if month_lookup.get(month) is not None
                            else 0.0,
                            weighted_amount=round(month_lookup.get(month).weighted_amount, 2)
                            if month_lookup.get(month) is not None
                            else 0.0,
                            actual_amount=round(month_lookup.get(month).actual_amount, 2)
                            if month_lookup.get(month) is not None
                            else 0.0,
                            booked_amount=round(month_lookup.get(month).booked_amount, 2)
                            if month_lookup.get(month) is not None
                            else 0.0,
                        )
                        for month in months
                    ],
                    discipline_rows=[
                        ForecastRevenueDisciplineRow(
                            discipline_id=detail.discipline_id,
                            discipline_name=detail.discipline_name,
                            base_phasing_profile=detail.base_phasing_profile,
                            forecast_method=detail.forecast_method,
                            line_count=detail.line_count,
                            manual_override_line_count=detail.manual_override_line_count,
                            total_amount=detail.total_amount,
                            weighted_total_amount=detail.weighted_total_amount,
                            month_values=[
                                ForecastRevenueProjectMonthValue(
                                    month=month,
                                    amount=round(discipline_month_lookup.get(month).gross_amount, 2)
                                    if discipline_month_lookup.get(month) is not None
                                    else 0.0,
                                    weighted_amount=round(
                                        discipline_month_lookup.get(month).weighted_amount,
                                        2,
                                    )
                                    if discipline_month_lookup.get(month) is not None
                                    else 0.0,
                                    actual_amount=round(
                                        discipline_month_lookup.get(month).actual_amount,
                                        2,
                                    )
                                    if discipline_month_lookup.get(month) is not None
                                    else 0.0,
                                    booked_amount=round(
                                        discipline_month_lookup.get(month).booked_amount,
                                        2,
                                    )
                                    if discipline_month_lookup.get(month) is not None
                                    else 0.0,
                                )
                                for discipline_month_lookup in [
                                    {value.month: value for value in detail.month_values}
                                ]
                                for month in months
                            ],
                        )
                        for detail in project.discipline_details
                    ],
                )
            )

        project_rows.sort(
            key=lambda item: (
                item.execution_start_date or "9999-12-31",
                item.client_name,
                item.project_name,
            )
        )

        return ForecastRevenueDashboardSection(
            currency_code=self._currency_code(projects),
            months=months,
            monthly_status_totals=[
                ForecastRevenueMonthStatusPoint(
                    month=month,
                    bid_amount=round(values["bid"], 2),
                    weighted_bid_amount=round(values["weighted_bid"], 2),
                    awarded_amount=round(values["awarded"], 2),
                    active_amount=round(values["active"], 2),
                    complete_amount=round(values["complete"], 2),
                    booked_amount=round(values["booked"], 2),
                    lost_amount=round(values["lost"], 2),
                )
                for month, values in monthly_status_totals.items()
            ],
            overall_status_totals=[
                ForecastRevenueStatusTotal(
                    status=status,
                    label=STATUS_LABELS[status],
                    project_count=len(values["project_ids"]) if isinstance(values["project_ids"], set) else 0,
                    total_amount=round(float(values["total_amount"]), 2),
                    weighted_total_amount=round(float(values["weighted_total_amount"]), 2),
                )
                for status, values in overall_status_totals.items()
            ],
            project_rows=project_rows,
        )

    def _build_awarded_lost_trend(
        self,
        projects: list[DashboardProjectRecord],
        filters: DashboardFilters,
    ) -> AwardedLostTrendSection:
        values_by_month: dict[str, dict[str, float]] = defaultdict(
            lambda: {"awarded_count": 0, "lost_count": 0, "awarded_amount": 0.0, "lost_amount": 0.0}
        )
        for project in projects:
            for outcome in project.outcomes:
                month = outcome.effective_at[:7]
                if not self._month_in_window(month, filters):
                    continue
                if outcome.outcome_type == "awarded":
                    values_by_month[month]["awarded_count"] += 1
                    values_by_month[month]["awarded_amount"] += project.quote_amount
                elif outcome.outcome_type == "lost":
                    values_by_month[month]["lost_count"] += 1
                    values_by_month[month]["lost_amount"] += project.quote_amount
        points = [
            AwardedLostMonthPoint(
                month=month,
                awarded_count=int(values["awarded_count"]),
                lost_count=int(values["lost_count"]),
                awarded_amount=round(values["awarded_amount"], 2),
                lost_amount=round(values["lost_amount"], 2),
            )
            for month, values in sorted(values_by_month.items())
        ]
        return AwardedLostTrendSection(currency_code="GBP", months=points)

    def _build_quote_actual_variance(
        self, projects: list[DashboardProjectRecord]
    ) -> QuoteActualVarianceSection:
        benchmarked = [
            project
            for project in projects
            if project.benchmark is not None
            and project.benchmark.actuals_status == "complete"
            and project.benchmark.variance_pct is not None
            and project.benchmark.variance_amount is not None
            and project.benchmark.actual_amount is not None
        ]
        values = [project.benchmark.variance_pct for project in benchmarked if project.benchmark is not None]
        buckets: dict[str, VarianceBucketSummary] = {}
        for key, label in (
            ("material_under", "Under 10%+"),
            ("under", "Under 5-10%"),
            ("on_target", "Within +/-5%"),
            ("over", "Over 5-10%"),
            ("material_over", "Over 10%+"),
        ):
            buckets[key] = VarianceBucketSummary(
                key=key,
                label=label,
                project_count=0,
                quoted_amount=0,
                actual_amount=0,
                variance_amount=0,
            )
        for project in benchmarked:
            benchmark = project.benchmark
            assert benchmark is not None
            assert benchmark.variance_pct is not None
            assert benchmark.variance_amount is not None
            assert benchmark.actual_amount is not None
            bucket_key = self._variance_bucket_key(benchmark.variance_pct)
            bucket = buckets[bucket_key]
            buckets[bucket_key] = VarianceBucketSummary(
                key=bucket.key,
                label=bucket.label,
                project_count=bucket.project_count + 1,
                quoted_amount=round(bucket.quoted_amount + benchmark.quoted_amount, 2),
                actual_amount=round(bucket.actual_amount + benchmark.actual_amount, 2),
                variance_amount=round(bucket.variance_amount + benchmark.variance_amount, 2),
            )
        return QuoteActualVarianceSection(
            currency_code="GBP",
            project_count=len(benchmarked),
            median_variance_pct=round(float(median(values)), 2) if values else None,
            complete_actuals_count=len(benchmarked),
            buckets=list(buckets.values()),
        )

    def _build_client_project_history(
        self, projects: list[DashboardProjectRecord]
    ) -> ClientProjectHistorySection:
        by_client: dict[str, dict[str, object]] = {}
        for project in projects:
            client = by_client.setdefault(
                project.client_id,
                {
                    "client_name": project.client_name,
                    "project_count": 0,
                    "bid_count": 0,
                    "awarded_count": 0,
                    "lost_count": 0,
                    "active_count": 0,
                    "complete_count": 0,
                    "quoted_amount": 0.0,
                    "actual_amount": 0.0,
                    "variance_pcts": [],
                },
            )
            client["project_count"] = int(client["project_count"]) + 1
            client[f"{project.status}_count"] = int(client.get(f"{project.status}_count", 0)) + 1
            client["quoted_amount"] = float(client["quoted_amount"]) + project.quote_amount
            if project.benchmark is not None and project.benchmark.actual_amount is not None:
                client["actual_amount"] = float(client["actual_amount"]) + project.benchmark.actual_amount
                if project.benchmark.actuals_status == "complete" and project.benchmark.variance_pct is not None:
                    variance_pcts = client["variance_pcts"]
                    assert isinstance(variance_pcts, list)
                    variance_pcts.append(project.benchmark.variance_pct)
        summaries: list[ClientHistorySummary] = []
        for client_id, values in sorted(by_client.items(), key=lambda item: str(item[1]["client_name"])):
            variance_pcts = values["variance_pcts"]
            assert isinstance(variance_pcts, list)
            summaries.append(
                ClientHistorySummary(
                    client_id=client_id,
                    client_name=str(values["client_name"]),
                    project_count=int(values["project_count"]),
                    bid_count=int(values["bid_count"]),
                    awarded_count=int(values["awarded_count"]),
                    lost_count=int(values["lost_count"]),
                    active_count=int(values["active_count"]),
                    complete_count=int(values["complete_count"]),
                    quoted_amount=round(float(values["quoted_amount"]), 2),
                    actual_amount=round(float(values["actual_amount"]), 2),
                    median_variance_pct=round(float(median(variance_pcts)), 2) if variance_pcts else None,
                )
            )
        return ClientProjectHistorySection(currency_code="GBP", clients=summaries)

    def _build_discipline_revenue_trends(
        self,
        projects: list[DashboardProjectRecord],
        filters: DashboardFilters,
    ) -> DisciplineRevenueTrendsSection:
        by_discipline: dict[str, dict[str, dict[str, float]]] = defaultdict(
            lambda: defaultdict(lambda: {"gross": 0.0, "weighted": 0.0})
        )
        month_keys: set[str] = set()
        for project in projects:
            for item in project.monthly_values:
                if not self._month_in_window(item.month, filters):
                    continue
                by_discipline[item.discipline_id][item.month]["gross"] += item.gross_amount
                by_discipline[item.discipline_id][item.month]["weighted"] += item.weighted_amount
                month_keys.add(item.month)
        ordered_months = sorted(month_keys)
        series = [
            DisciplineRevenueSeries(
                discipline_id=discipline_id,
                discipline_name=next(
                    (
                        next_item.discipline_name
                        for project in projects
                        for next_item in project.monthly_values
                        if next_item.discipline_id == discipline_id
                    ),
                    DISCIPLINE_LABELS.get(discipline_id, discipline_id.title()),
                ),
                points=[
                    DisciplineTrendPoint(
                        month=month,
                        gross_amount=round(by_discipline[discipline_id].get(month, {}).get("gross", 0.0), 2),
                        weighted_amount=round(by_discipline[discipline_id].get(month, {}).get("weighted", 0.0), 2),
                    )
                    for month in ordered_months
                ],
            )
            for discipline_id in sorted(by_discipline, key=lambda item: DISCIPLINE_LABELS.get(item, item))
        ]
        return DisciplineRevenueTrendsSection(
            currency_code=self._currency_code(projects),
            months=ordered_months,
            series=series,
        )

    def _build_forecast_confidence(
        self, projects: list[DashboardProjectRecord]
    ) -> ForecastConfidenceSection:
        scores = [self._confidence_score(project) for project in projects]
        band_counts = {"high": 0, "medium": 0, "low": 0}
        for project in projects:
            band_counts[self._confidence_band(self._confidence_score(project))] += 1
        return ForecastConfidenceSection(
            project_count=len(projects),
            average_score=round(sum(scores) / len(scores), 2) if scores else 0.0,
            high_confidence_project_count=band_counts["high"],
            bands=[
                ConfidenceBandSummary(band="high", label="High", project_count=band_counts["high"]),
                ConfidenceBandSummary(band="medium", label="Medium", project_count=band_counts["medium"]),
                ConfidenceBandSummary(band="low", label="Low", project_count=band_counts["low"]),
            ],
        )

    def _build_benchmark_overview(
        self, projects: list[DashboardProjectRecord]
    ) -> BenchmarkOverviewSection:
        benchmarked = [project for project in projects if project.benchmark is not None]
        complete = [
            project
            for project in benchmarked
            if project.benchmark is not None
            and project.benchmark.actuals_status == "complete"
            and project.benchmark.variance_pct is not None
        ]
        variance_values = [
            project.benchmark.variance_pct
            for project in complete
            if project.benchmark is not None and project.benchmark.variance_pct is not None
        ]
        band_buckets = self._build_variance_band_buckets(complete)
        discipline_buckets: dict[str, list[float]] = defaultdict(list)
        for project in complete:
            benchmark = project.benchmark
            assert benchmark is not None
            for summary in benchmark.disciplines:
                if summary.variance_pct is not None:
                    discipline_buckets[summary.discipline_id].append(summary.variance_pct)
        discipline_summaries = [
            BenchmarkDisciplineSummary(
                discipline_id=discipline_id,
                discipline_name=DISCIPLINE_LABELS.get(discipline_id, discipline_id.title()),
                project_count=len(values),
                median_variance_pct=round(float(median(values)), 2) if values else None,
            )
            for discipline_id, values in sorted(discipline_buckets.items(), key=lambda item: item[0])
        ]
        return BenchmarkOverviewSection(
            currency_code="GBP",
            benchmark_project_count=len(benchmarked),
            complete_actuals_count=len(complete),
            median_variance_pct=round(float(median(variance_values)), 2) if variance_values else None,
            variance_bands=band_buckets,
            disciplines=discipline_summaries,
        )

    def _build_sales_pipeline_drilldown(
        self, projects: list[DashboardProjectRecord]
    ) -> DashboardDrilldownResponse:
        rows = [
            {
                "projectName": project.name,
                "clientName": project.client_name,
                "status": STATUS_LABELS.get(project.status, project.status.title()),
                "quoteTotal": round(project.quote_amount, 2),
                "weightedValue": round(project.commercial_weighted_value, 2),
                "probabilityPercent": round(project.probability_percent, 2),
                "lastStatusDate": project.outcomes[-1].effective_at if project.outcomes else None,
            }
            for project in sorted(projects, key=lambda item: (-item.quote_amount, item.name))
        ]
        return DashboardDrilldownResponse(
            view="sales_pipeline",
            title=VIEW_TITLES["sales_pipeline"],
            columns=[
                DashboardDrilldownColumn(key="projectName", label="Project", kind="text"),
                DashboardDrilldownColumn(key="clientName", label="Client", kind="text"),
                DashboardDrilldownColumn(key="status", label="Status", kind="status"),
                DashboardDrilldownColumn(key="quoteTotal", label="Quote Total", kind="currency"),
                DashboardDrilldownColumn(key="weightedValue", label="Weighted Value", kind="currency"),
                DashboardDrilldownColumn(key="probabilityPercent", label="Probability %", kind="percent"),
                DashboardDrilldownColumn(key="lastStatusDate", label="Last Status Date", kind="date"),
            ],
            rows=rows,
            totals={
                "projectCount": len(rows),
                "quoteTotal": round(sum(project.quote_amount for project in projects), 2),
                "weightedValue": round(
                    sum(project.commercial_weighted_value for project in projects),
                    2,
                ),
            },
        )

    def _build_monthly_forecast_drilldown(
        self, projects: list[DashboardProjectRecord], filters: DashboardFilters
    ) -> DashboardDrilldownResponse:
        rows = [
            {
                "month": item.month,
                "projectName": project.name,
                "disciplineName": item.discipline_name,
                "grossAmount": round(item.gross_amount, 2),
                "weightedAmount": round(item.weighted_amount, 2),
                "lowAmount": round(item.low_amount, 2),
                "highAmount": round(item.high_amount, 2),
                "actualAmount": round(item.actual_amount, 2),
                "bookedAmount": round(item.booked_amount, 2),
                "scenarioKey": project.forecast_scenario_key or "base",
                "forecastStatus": project.forecast_status,
            }
            for project in projects
            for item in sorted(project.monthly_values, key=lambda value: (value.month, value.discipline_id))
            if self._month_in_window(item.month, filters)
        ]
        return DashboardDrilldownResponse(
            view="monthly_forecast",
            title=VIEW_TITLES["monthly_forecast"],
            columns=[
                DashboardDrilldownColumn(key="month", label="Month", kind="month"),
                DashboardDrilldownColumn(key="projectName", label="Project", kind="text"),
                DashboardDrilldownColumn(key="disciplineName", label="Discipline", kind="text"),
                DashboardDrilldownColumn(key="grossAmount", label="Gross Amount", kind="currency"),
                DashboardDrilldownColumn(key="weightedAmount", label="Weighted Amount", kind="currency"),
                DashboardDrilldownColumn(key="bookedAmount", label="Booked Amount", kind="currency"),
                DashboardDrilldownColumn(key="actualAmount", label="Actual Amount", kind="currency"),
                DashboardDrilldownColumn(key="lowAmount", label="Low", kind="currency"),
                DashboardDrilldownColumn(key="highAmount", label="High", kind="currency"),
                DashboardDrilldownColumn(key="scenarioKey", label="Scenario", kind="text"),
            ],
            rows=rows,
            totals={
                "grossAmount": round(sum(float(row["grossAmount"]) for row in rows), 2),
                "weightedAmount": round(sum(float(row["weightedAmount"]) for row in rows), 2),
                "bookedAmount": round(sum(float(row["bookedAmount"]) for row in rows), 2),
                "actualAmount": round(sum(float(row["actualAmount"]) for row in rows), 2),
            },
        )

    def _build_awarded_lost_drilldown(
        self, projects: list[DashboardProjectRecord], filters: DashboardFilters
    ) -> DashboardDrilldownResponse:
        rows = [
            {
                "month": outcome.effective_at[:7],
                "projectName": project.name,
                "clientName": project.client_name,
                "outcomeType": outcome.outcome_type.title(),
                "quotedAmount": round(project.quote_amount, 2),
                "effectiveAt": outcome.effective_at,
            }
            for project in projects
            for outcome in project.outcomes
            if outcome.outcome_type in {"awarded", "lost"} and self._month_in_window(outcome.effective_at[:7], filters)
        ]
        rows.sort(key=lambda item: (str(item["month"]), str(item["projectName"])))
        return DashboardDrilldownResponse(
            view="awarded_lost",
            title=VIEW_TITLES["awarded_lost"],
            columns=[
                DashboardDrilldownColumn(key="month", label="Month", kind="month"),
                DashboardDrilldownColumn(key="projectName", label="Project", kind="text"),
                DashboardDrilldownColumn(key="clientName", label="Client", kind="text"),
                DashboardDrilldownColumn(key="outcomeType", label="Outcome", kind="text"),
                DashboardDrilldownColumn(key="quotedAmount", label="Quoted Amount", kind="currency"),
                DashboardDrilldownColumn(key="effectiveAt", label="Effective At", kind="date"),
            ],
            rows=rows,
            totals={
                "eventCount": len(rows),
                "quotedAmount": round(sum(float(row["quotedAmount"]) for row in rows), 2),
            },
        )

    def _build_variance_drilldown(
        self, projects: list[DashboardProjectRecord]
    ) -> DashboardDrilldownResponse:
        rows = [
            {
                "projectName": project.name,
                "disciplineName": "Project Total",
                "quotedAmount": round(project.benchmark.quoted_amount, 2),
                "actualAmount": round(project.benchmark.actual_amount or 0, 2),
                "varianceAmount": round(project.benchmark.variance_amount or 0, 2),
                "variancePct": project.benchmark.variance_pct,
                "actualsStatus": project.benchmark.actuals_status.title(),
                "actualsAsOfDate": project.benchmark.actuals_as_of_date,
            }
            for project in projects
            if project.benchmark is not None
            and project.benchmark.actual_amount is not None
            and project.benchmark.variance_amount is not None
        ]
        rows.sort(key=lambda item: (-(float(item["variancePct"] or 0)), str(item["projectName"])))
        return DashboardDrilldownResponse(
            view="variance",
            title=VIEW_TITLES["variance"],
            columns=[
                DashboardDrilldownColumn(key="projectName", label="Project", kind="text"),
                DashboardDrilldownColumn(key="disciplineName", label="Discipline", kind="text"),
                DashboardDrilldownColumn(key="quotedAmount", label="Quoted Amount", kind="currency"),
                DashboardDrilldownColumn(key="actualAmount", label="Actual Amount", kind="currency"),
                DashboardDrilldownColumn(key="varianceAmount", label="Variance", kind="currency"),
                DashboardDrilldownColumn(key="variancePct", label="Variance %", kind="percent"),
                DashboardDrilldownColumn(key="actualsStatus", label="Actuals Status", kind="text"),
                DashboardDrilldownColumn(key="actualsAsOfDate", label="Actuals As Of", kind="date"),
            ],
            rows=rows,
            totals={
                "projectCount": len(rows),
                "quotedAmount": round(sum(float(row["quotedAmount"]) for row in rows), 2),
                "actualAmount": round(sum(float(row["actualAmount"]) for row in rows), 2),
                "varianceAmount": round(sum(float(row["varianceAmount"]) for row in rows), 2),
            },
        )

    def _build_client_history_drilldown(
        self, projects: list[DashboardProjectRecord]
    ) -> DashboardDrilldownResponse:
        section = self._build_client_project_history(projects)
        rows = [
            {
                "clientName": client.client_name,
                "projectCount": client.project_count,
                "awardedCount": client.awarded_count,
                "lostCount": client.lost_count,
                "winRate": round(
                    client.awarded_count / (client.awarded_count + client.lost_count) * 100,
                    2,
                )
                if (client.awarded_count + client.lost_count) > 0
                else None,
                "quotedAmount": client.quoted_amount,
                "actualAmount": client.actual_amount,
                "medianVariancePct": client.median_variance_pct,
            }
            for client in section.clients
        ]
        return DashboardDrilldownResponse(
            view="client_history",
            title=VIEW_TITLES["client_history"],
            columns=[
                DashboardDrilldownColumn(key="clientName", label="Client", kind="text"),
                DashboardDrilldownColumn(key="projectCount", label="Projects", kind="number"),
                DashboardDrilldownColumn(key="awardedCount", label="Awarded", kind="number"),
                DashboardDrilldownColumn(key="lostCount", label="Lost", kind="number"),
                DashboardDrilldownColumn(key="winRate", label="Win Rate %", kind="percent"),
                DashboardDrilldownColumn(key="quotedAmount", label="Quoted Amount", kind="currency"),
                DashboardDrilldownColumn(key="actualAmount", label="Actual Amount", kind="currency"),
                DashboardDrilldownColumn(key="medianVariancePct", label="Median Variance %", kind="percent"),
            ],
            rows=rows,
            totals={
                "clientCount": len(rows),
                "quotedAmount": round(sum(float(row["quotedAmount"]) for row in rows), 2),
                "actualAmount": round(sum(float(row["actualAmount"]) for row in rows), 2),
            },
        )

    def _build_discipline_trends_drilldown(
        self, projects: list[DashboardProjectRecord], filters: DashboardFilters
    ) -> DashboardDrilldownResponse:
        rows = [
            {
                "month": item.month,
                "disciplineName": item.discipline_name,
                "projectName": project.name,
                "grossAmount": round(item.gross_amount, 2),
                "weightedAmount": round(item.weighted_amount, 2),
            }
            for project in projects
            for item in project.monthly_values
            if self._month_in_window(item.month, filters)
        ]
        rows.sort(key=lambda item: (str(item["month"]), str(item["disciplineName"]), str(item["projectName"])))
        return DashboardDrilldownResponse(
            view="discipline_trends",
            title=VIEW_TITLES["discipline_trends"],
            columns=[
                DashboardDrilldownColumn(key="month", label="Month", kind="month"),
                DashboardDrilldownColumn(key="disciplineName", label="Discipline", kind="text"),
                DashboardDrilldownColumn(key="projectName", label="Project", kind="text"),
                DashboardDrilldownColumn(key="grossAmount", label="Gross Amount", kind="currency"),
                DashboardDrilldownColumn(key="weightedAmount", label="Weighted Amount", kind="currency"),
            ],
            rows=rows,
            totals={
                "grossAmount": round(sum(float(row["grossAmount"]) for row in rows), 2),
                "weightedAmount": round(sum(float(row["weightedAmount"]) for row in rows), 2),
            },
        )

    def _build_forecast_confidence_drilldown(
        self, projects: list[DashboardProjectRecord]
    ) -> DashboardDrilldownResponse:
        rows = [
            {
                "projectName": project.name,
                "clientName": project.client_name,
                "status": STATUS_LABELS.get(project.status, project.status.title()),
                "probabilityPercent": round(project.probability_percent, 2),
                "actualsStatus": project.actuals_status.title(),
                "openIssues": len(project.issues),
                "confidenceScore": self._confidence_score(project),
                "confidenceBand": self._confidence_band(self._confidence_score(project)).title(),
                "dataSufficiencyScore": round(project.data_sufficiency_score or 0.0, 2),
                "fallbackTier": project.fallback_tier,
                "scenarioKey": project.forecast_scenario_key or "base",
                "forecastStatus": project.forecast_status,
            }
            for project in sorted(projects, key=lambda item: (-self._confidence_score(item), item.name))
        ]
        return DashboardDrilldownResponse(
            view="forecast_confidence",
            title=VIEW_TITLES["forecast_confidence"],
            columns=[
                DashboardDrilldownColumn(key="projectName", label="Project", kind="text"),
                DashboardDrilldownColumn(key="clientName", label="Client", kind="text"),
                DashboardDrilldownColumn(key="status", label="Status", kind="status"),
                DashboardDrilldownColumn(key="probabilityPercent", label="Probability %", kind="percent"),
                DashboardDrilldownColumn(key="actualsStatus", label="Actuals Status", kind="text"),
                DashboardDrilldownColumn(key="openIssues", label="Open Issues", kind="number"),
                DashboardDrilldownColumn(key="confidenceScore", label="Confidence Score", kind="number"),
                DashboardDrilldownColumn(key="confidenceBand", label="Confidence Band", kind="text"),
                DashboardDrilldownColumn(
                    key="dataSufficiencyScore",
                    label="Data Sufficiency",
                    kind="number",
                ),
                DashboardDrilldownColumn(key="fallbackTier", label="Fallback Tier", kind="text"),
                DashboardDrilldownColumn(key="scenarioKey", label="Scenario", kind="text"),
            ],
            rows=rows,
            totals={
                "projectCount": len(rows),
                "averageScore": round(sum(float(row["confidenceScore"]) for row in rows) / len(rows), 2)
                if rows
                else 0.0,
            },
        )

    def _build_benchmark_overview_drilldown(
        self, projects: list[DashboardProjectRecord]
    ) -> DashboardDrilldownResponse:
        rows = [
            {
                "projectName": project.name,
                "quotedAmount": round(project.benchmark.quoted_amount, 2),
                "actualAmount": round(project.benchmark.actual_amount or 0, 2),
                "variancePct": project.benchmark.variance_pct,
                "actualsStatus": project.benchmark.actuals_status.title(),
                "benchmarkGeneratedAt": project.benchmark.actuals_as_of_date,
            }
            for project in projects
            if project.benchmark is not None
        ]
        rows.sort(key=lambda item: (str(item["actualsStatus"]), str(item["projectName"])))
        return DashboardDrilldownResponse(
            view="benchmark_overview",
            title=VIEW_TITLES["benchmark_overview"],
            columns=[
                DashboardDrilldownColumn(key="projectName", label="Project", kind="text"),
                DashboardDrilldownColumn(key="quotedAmount", label="Quoted Amount", kind="currency"),
                DashboardDrilldownColumn(key="actualAmount", label="Actual Amount", kind="currency"),
                DashboardDrilldownColumn(key="variancePct", label="Variance %", kind="percent"),
                DashboardDrilldownColumn(key="actualsStatus", label="Actuals Status", kind="text"),
                DashboardDrilldownColumn(key="benchmarkGeneratedAt", label="Actuals As Of", kind="date"),
            ],
            rows=rows,
            totals={
                "projectCount": len(rows),
                "quotedAmount": round(sum(float(row["quotedAmount"]) for row in rows), 2),
                "actualAmount": round(sum(float(row["actualAmount"]) for row in rows), 2),
            },
        )

    def _confidence_score(self, project: DashboardProjectRecord) -> int:
        if project.forecast_confidence_score is not None:
            return max(0, min(round(project.forecast_confidence_score), 100))
        bucket_bonus = 25 if project.status in {"awarded", "active", "complete"} else 10 if project.status == "bid" else 0
        actuals_bonus = 15 if project.actuals_status == "complete" else 8 if project.actuals_status == "partial" else 0
        issue_bonus = 10 if len(project.issues) == 0 else 5 if len(project.issues) <= 2 else 0
        score = round(project.probability_percent * 0.5) + bucket_bonus + actuals_bonus + issue_bonus
        return max(0, min(score, 100))

    def _confidence_band(self, score: int) -> str:
        if score >= 75:
            return "high"
        if score >= 50:
            return "medium"
        return "low"

    def _build_variance_band_buckets(
        self, projects: list[DashboardProjectRecord]
    ) -> list[VarianceBucketSummary]:
        buckets: dict[str, VarianceBucketSummary] = {
            "material_under": VarianceBucketSummary(
                key="material_under",
                label="Under 10%+",
                project_count=0,
                quoted_amount=0,
                actual_amount=0,
                variance_amount=0,
            ),
            "under": VarianceBucketSummary(
                key="under",
                label="Under 5-10%",
                project_count=0,
                quoted_amount=0,
                actual_amount=0,
                variance_amount=0,
            ),
            "on_target": VarianceBucketSummary(
                key="on_target",
                label="Within +/-5%",
                project_count=0,
                quoted_amount=0,
                actual_amount=0,
                variance_amount=0,
            ),
            "over": VarianceBucketSummary(
                key="over",
                label="Over 5-10%",
                project_count=0,
                quoted_amount=0,
                actual_amount=0,
                variance_amount=0,
            ),
            "material_over": VarianceBucketSummary(
                key="material_over",
                label="Over 10%+",
                project_count=0,
                quoted_amount=0,
                actual_amount=0,
                variance_amount=0,
            ),
        }
        for project in projects:
            benchmark = project.benchmark
            if benchmark is None or benchmark.variance_pct is None or benchmark.variance_amount is None or benchmark.actual_amount is None:
                continue
            bucket_key = self._variance_bucket_key(benchmark.variance_pct)
            bucket = buckets[bucket_key]
            buckets[bucket_key] = VarianceBucketSummary(
                key=bucket.key,
                label=bucket.label,
                project_count=bucket.project_count + 1,
                quoted_amount=round(bucket.quoted_amount + benchmark.quoted_amount, 2),
                actual_amount=round(bucket.actual_amount + benchmark.actual_amount, 2),
                variance_amount=round(bucket.variance_amount + benchmark.variance_amount, 2),
            )
        return list(buckets.values())

    def _variance_bucket_key(self, variance_pct: float) -> str:
        if variance_pct < -10:
            return "material_under"
        if variance_pct < -5:
            return "under"
        if variance_pct <= 5:
            return "on_target"
        if variance_pct <= 10:
            return "over"
        return "material_over"

    def _format_currency(self, value: float, currency_code: str = "GBP") -> str:
        symbol = "£" if currency_code == "GBP" else "$"
        return f"{symbol}{value:,.0f}"

    def _format_percent(self, value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"{value:.1f}%"

    def _month_in_window(self, month: str, filters: DashboardFilters) -> bool:
        return self._parse_month(filters.from_month) <= self._parse_month(month) <= self._parse_month(filters.to_month)

    def _parse_month(self, value: str) -> date:
        try:
            year, month = value.split("-", 1)
            return date(int(year), int(month), 1)
        except ValueError as exc:
            raise ApiProblemException(
                422,
                f"Dashboard month '{value}' must use YYYY-MM format.",
                "Invalid Dashboard Month",
            ) from exc

    def _offset_month(self, source: date, delta: int) -> str:
        month_index = source.year * 12 + source.month - 1 + delta
        year = month_index // 12
        month = month_index % 12 + 1
        return f"{year:04d}-{month:02d}"


dashboard_service = DashboardService()
