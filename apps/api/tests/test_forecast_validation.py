from __future__ import annotations

import os
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    Discipline,
    ForecastVersion,
    MappedActual,
    Project,
    ProjectBenchmarkDisciplineSummary,
    ProjectBenchmarkSummary,
    ProjectDiscipline,
    ProjectMetadata,
    ProjectParty,
    ProjectScheduleRange,
    Quote,
    QuoteLineItem,
    QuoteSection,
    QuoteVersion,
    User,
)
from app.models.enums import (
    BenchmarkActualsStatus,
    CetaRowFinancialType,
    MappedActualChangeType,
    ProjectPartyRole,
    ProjectStatus,
    QuoteLineItemType,
    QuoteVersionStatus,
)
from app.modules.forecasts.engine import (
    ForecastEngineLineInput,
    ForecastEngineProjectContext,
    ForecastEngineScheduleRange,
    build_line_plan,
)
from app.modules.forecasts.schemas import ForecastVersionCreateRequest
from app.modules.forecasts.service import forecast_service


def _login(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/session",
        json={
            "email": os.environ["DEV_ADMIN_EMAIL"],
            "password": os.environ["DEV_ADMIN_PASSWORD"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _admin_headers(client: TestClient) -> dict[str, str]:
    session = _login(client)
    return {"Authorization": f"Bearer {session['accessToken']}"}


def _admin_actor_id(session: Session) -> str:
    actor_id = session.scalar(select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    assert actor_id is not None
    return actor_id


def _company_id(session: Session, normalized_name: str) -> str:
    company_id = session.scalar(
        select(Company.id).where(Company.normalized_name == normalized_name)
    )
    assert company_id is not None
    return company_id


def _discipline(session: Session, code: str) -> Discipline:
    discipline = session.scalar(select(Discipline).where(Discipline.code == code))
    assert discipline is not None
    return discipline


def _allocation_amounts_by_month(line) -> dict[str, float]:
    return {allocation.month: allocation.amount for allocation in line.allocations}


def _validation_flags(
    *,
    quote_total: float | None = None,
    forecast_total: float | None = None,
    forecast_issues: list[str] | None = None,
    scenario_months: list[str] | None = None,
    forecast_months: list[str] | None = None,
) -> list[str]:
    flags: list[str] = []
    normalized_issues = [issue.lower() for issue in (forecast_issues or [])]

    if (
        quote_total is not None
        and forecast_total is not None
        and forecast_total > quote_total
        and not any("overrun" in issue or "actual" in issue for issue in normalized_issues)
    ):
        flags.append("actuals_exceed_quote_without_explicit_overburn_flag")

    if (
        scenario_months
        and forecast_months
        and (
            scenario_months[0] > forecast_months[0]
            or scenario_months[-1] > forecast_months[-1]
        )
    ):
        flags.append("scenario_schedule_shift_not_reflected_in_forecast")

    return flags


def _create_post_project(
    session: Session,
    *,
    project_id: str,
    name: str,
    status: ProjectStatus,
    quote_total: float,
    duration_weeks: int,
    line_amounts: list[tuple[str, float]],
    schedule_ranges: list[tuple[str, date, date, float | None, str | None]],
    currency_code: str = "GBP",
    client_normalized_name: str = "north star pictures",
    project_format_key: str = "trailer_promo",
    metadata_json: dict[str, object] | None = None,
    benchmark_actual: float | None = None,
    actuals: list[tuple[str, date, date, float, str]] | None = None,
) -> str:
    actor_id = _admin_actor_id(session)
    discipline_codes = {
        code
        for code, _ in line_amounts
        if code is not None
    } | {
        str(discipline_code)
        for _, _, _, _, discipline_code in schedule_ranges
        if discipline_code is not None
    } | {
        discipline_code
        for discipline_code, *_rest in (actuals or [])
    }
    discipline_ids = {code: _discipline(session, code).id for code in discipline_codes}

    project = Project(
        id=project_id,
        code=project_id[-12:].upper(),
        name=name,
        status=status,
        quote_currency_code=currency_code,
        start_date=min(item[1] for item in schedule_ranges) if schedule_ranges else None,
        end_date=max(item[2] for item in schedule_ranges) if schedule_ranges else None,
    )
    session.add(project)
    session.flush()

    project_metadata_json = dict(metadata_json or {})
    episode_count = int(project_metadata_json.get("episodeCount") or 1)
    session.add(
        ProjectMetadata(
            project_id=project.id,
            format_type=project_format_key,
            project_format_key=project_format_key,
            duration_weeks=duration_weeks,
            episode_count=episode_count,
            language="en-GB",
            budget_target=quote_total,
            metadata_json=project_metadata_json,
        )
    )

    client_company_id = _company_id(session, client_normalized_name)
    streamer_company_id = _company_id(session, "netstream")
    session.add(
        ProjectParty(
            project_id=project.id,
            company_id=client_company_id,
            role=ProjectPartyRole.client,
            is_primary=True,
        )
    )
    session.add(
        ProjectParty(
            project_id=project.id,
            company_id=streamer_company_id,
            role=ProjectPartyRole.streamer,
            is_primary=True,
        )
    )

    created_at = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
    for index, discipline_code in enumerate(sorted(discipline_codes)):
        session.add(
            ProjectDiscipline(
                project_id=project.id,
                discipline_id=discipline_ids[discipline_code],
                is_primary=index == 0,
                created_at=created_at,
            )
        )

    for label, start_date, end_date, allocation_percent, discipline_code in schedule_ranges:
        session.add(
            ProjectScheduleRange(
                project_id=project.id,
                discipline_id=discipline_ids.get(discipline_code)
                if discipline_code is not None
                else None,
                label=label,
                start_date=start_date,
                end_date=end_date,
                allocation_percent=allocation_percent,
            )
        )

    quote = Quote(
        project_id=project.id,
        quote_number=f"{project_id}-Q1",
        title=f"{name} Quote",
    )
    session.add(quote)
    session.flush()

    quote_version = QuoteVersion(
        quote_id=quote.id,
        version_number=1,
        status=QuoteVersionStatus.issued,
        title=f"{name} Issued Quote",
        currency_code=currency_code,
        issued_at=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
        subtotal_amount=quote_total,
        tax_amount=0,
        total_amount=quote_total,
        created_by_id=actor_id,
    )
    session.add(quote_version)
    session.flush()
    quote.current_version_id = quote_version.id

    section = QuoteSection(
        quote_version_id=quote_version.id,
        name="Services",
        sort_order=1,
        subtotal_amount=quote_total,
    )
    session.add(section)
    session.flush()

    for sort_order, (discipline_code, amount) in enumerate(line_amounts, start=1):
        session.add(
            QuoteLineItem(
                quote_section_id=section.id,
                sort_order=sort_order,
                line_type=QuoteLineItemType.service,
                discipline_id=discipline_ids[discipline_code],
                description=f"{discipline_code.title()} work",
                quantity=1,
                unit="project",
                rate=amount,
                amount=amount,
            )
        )

    if benchmark_actual is not None:
        variance_amount = benchmark_actual - quote_total
        variance_pct = round((variance_amount / quote_total) * 100, 2) if quote_total else 0.0
        benchmark_summary = ProjectBenchmarkSummary(
            project_id=project.id,
            source_quote_version_id=quote_version.id,
            currency_code=currency_code,
            quoted_amount=quote_total,
            actual_amount=benchmark_actual,
            quote_to_actual_variance_amount=variance_amount,
            quote_to_actual_variance_pct=variance_pct,
            actuals_status=BenchmarkActualsStatus.complete,
            actuals_as_of_date=date(2026, 3, 31),
            generated_at=datetime(2026, 3, 31, 12, 0, tzinfo=UTC),
        )
        session.add(benchmark_summary)
        session.flush()
        for discipline_code, quoted_amount in line_amounts:
            actual_amount = round(quoted_amount * (1 + variance_pct / 100), 2)
            session.add(
                ProjectBenchmarkDisciplineSummary(
                    benchmark_summary_id=benchmark_summary.id,
                    discipline_id=discipline_ids[discipline_code],
                    quoted_amount=quoted_amount,
                    actual_amount=actual_amount,
                    quote_to_actual_variance_amount=round(actual_amount - quoted_amount, 2),
                    quote_to_actual_variance_pct=variance_pct,
                    actuals_status=BenchmarkActualsStatus.complete,
                    generated_at=datetime(2026, 3, 31, 12, 0, tzinfo=UTC),
                )
            )

    for discipline_code, work_date, posting_date, amount, description in actuals or []:
        session.add(
            MappedActual(
                project_id=project.id,
                discipline_id=discipline_ids[discipline_code],
                source_ceta_import_id=None,
                source_ceta_import_row_id=None,
                mapping_decision_id=None,
                work_date=work_date,
                posting_date=posting_date,
                description=description,
                vendor_name=None,
                amount=amount,
                currency_code=currency_code,
                financial_type=CetaRowFinancialType.revenue,
                cost_category_key=None,
                revenue_category_key="post_revenue",
                actual_business_key=f"{project.id}-{discipline_code}-{posting_date.isoformat()}",
                supersedes_mapped_actual_id=None,
                is_current=True,
                change_type=MappedActualChangeType.new,
                mapped_by_id=actor_id,
                mapped_at=created_at,
            )
        )

    session.flush()
    return project.id


def test_validation_core_post_scenario_matches_timing_weighting_and_dashboard_rollups(
    client: TestClient,
    db_session: Session,
) -> None:
    actor_id = _admin_actor_id(db_session)
    project_id = _create_post_project(
        db_session,
        project_id="project_val_core",
        name="Validation Core Trailer",
        status=ProjectStatus.bid,
        quote_total=100000,
        duration_weeks=16,
        line_amounts=[
            ("offline", 40000),
            ("online", 35000),
            ("sound", 25000),
        ],
        schedule_ranges=[
            ("Offline edit", date(2026, 4, 1), date(2026, 5, 31), 40.0, "offline"),
            ("Online finish", date(2026, 5, 1), date(2026, 7, 31), 35.0, "online"),
            ("Sound mix", date(2026, 6, 1), date(2026, 7, 31), 25.0, "sound"),
        ],
    )

    version = forecast_service.create_or_clone_version(
        db_session,
        project_id,
        ForecastVersionCreateRequest(
            title="Core validation forecast",
            probability_percent=65,
        ),
        actor_id=actor_id,
    )
    db_session.commit()

    lines_by_discipline = {line.discipline_id: line for line in version.lines}
    offline_id = _discipline(db_session, "offline").id
    online_id = _discipline(db_session, "online").id
    sound_id = _discipline(db_session, "sound").id

    offline_amounts = _allocation_amounts_by_month(lines_by_discipline[offline_id])
    online_amounts = _allocation_amounts_by_month(lines_by_discipline[online_id])
    sound_amounts = _allocation_amounts_by_month(lines_by_discipline[sound_id])

    assert lines_by_discipline[offline_id].allocation_profile_key == "front_loaded"
    assert lines_by_discipline[online_id].allocation_profile_key == "mid_loaded"
    assert lines_by_discipline[sound_id].allocation_profile_key == "back_loaded"

    assert offline_amounts["2026-04"] > offline_amounts["2026-05"]
    assert online_amounts["2026-06"] > online_amounts["2026-05"]
    assert online_amounts["2026-06"] > online_amounts["2026-07"]
    assert sound_amounts["2026-07"] > sound_amounts["2026-06"]

    assert version.total_amount == 100000
    assert version.weighted_total_amount == 65000
    assert round(sum(item.amount for item in version.project_monthly_rollups), 2) == 100000
    assert round(sum(item.weighted_amount for item in version.project_monthly_rollups), 2) == 65000
    assert all(
        0 < item.weighted_amount < item.amount
        for item in version.project_monthly_rollups
        if item.amount > 0
    )

    response = client.get(
        f"/api/v1/dashboards/operational?projectId={project_id}",
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    bid_stage = next(
        stage for stage in payload["salesPipeline"]["stages"] if stage["status"] == "bid"
    )
    assert bid_stage["projectCount"] == 1
    assert bid_stage["quoteAmount"] == 100000
    assert bid_stage["weightedAmount"] == 65000

    dashboard_months = {
        item["month"]: (item["grossAmount"], item["weightedAmount"])
        for item in payload["monthlyRevenueForecast"]["months"]
    }
    for rollup in version.project_monthly_rollups:
        assert dashboard_months[rollup.month] == (rollup.amount, rollup.weighted_amount)


def test_validation_reforecast_keeps_posted_actuals_and_redistributes_remaining_work(
    db_session: Session,
) -> None:
    actor_id = _admin_actor_id(db_session)
    project_id = _create_post_project(
        db_session,
        project_id="project_val_reforecast",
        name="Validation Reforecast Active Project",
        status=ProjectStatus.active,
        quote_total=90000,
        duration_weeks=12,
        line_amounts=[("offline", 90000)],
        schedule_ranges=[
            ("Offline edit", date(2026, 4, 1), date(2026, 6, 30), 100.0, "offline"),
        ],
        actuals=[
            ("offline", date(2026, 4, 15), date(2026, 4, 20), 30000, "April invoice"),
        ],
    )

    initial = forecast_service.create_or_clone_version(
        db_session,
        project_id,
        ForecastVersionCreateRequest(title="Initial reforecast validation"),
        actor_id=actor_id,
    )
    assert [allocation.month for allocation in initial.lines[0].allocations] == [
        "2026-04",
        "2026-05",
        "2026-06",
    ]

    schedule_range = db_session.scalar(
        select(ProjectScheduleRange).where(ProjectScheduleRange.project_id == project_id)
    )
    assert schedule_range is not None
    schedule_range.end_date = date(2026, 7, 31)
    db_session.flush()

    recalculated, _message = forecast_service.recalculate_project(
        db_session,
        project_id,
        actor_id=actor_id,
    )

    line = recalculated.lines[0]
    amounts_by_month = _allocation_amounts_by_month(line)
    assert line.actuals_to_date_amount == 30000
    assert line.remaining_amount == 60000
    assert amounts_by_month["2026-04"] == 30000
    assert "2026-07" in amounts_by_month
    assert amounts_by_month["2026-07"] > 0
    assert round(sum(amounts_by_month.values()), 2) == 90000
    assert round(
        sum(amount for month, amount in amounts_by_month.items() if month != "2026-04"),
        2,
    ) == 60000
    assert all(amount >= 0 for amount in amounts_by_month.values())


def test_validation_confidence_bands_widen_when_evidence_is_weaker() -> None:
    schedule_range = ForecastEngineScheduleRange(
        id="range_confidence",
        label="Main schedule",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 7, 31),
        discipline_id="discipline_offline",
    )
    line_input = ForecastEngineLineInput(
        line_id="line_confidence",
        label="Offline edit",
        total_amount=80000,
        discipline_id="discipline_offline",
        discipline_code="offline",
        schedule_range_id="range_confidence",
    )

    strong_evidence = build_line_plan(
        ForecastEngineProjectContext(
            project_id="project_confidence_strong",
            project_format_key="trailer_promo",
            metadata_json=None,
            episode_count=1,
            duration_weeks=16,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 7, 31),
            schedule_ranges=[schedule_range],
            confidence_score=88.0,
            data_sufficiency_score=84.0,
        ),
        line_input,
    )
    weak_evidence = build_line_plan(
        ForecastEngineProjectContext(
            project_id="project_confidence_weak",
            project_format_key="trailer_promo",
            metadata_json=None,
            episode_count=1,
            duration_weeks=16,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 7, 31),
            schedule_ranges=[schedule_range],
            confidence_score=34.0,
            data_sufficiency_score=28.0,
        ),
        line_input,
    )

    strong_band_width = round(
        sum(item.high_amount - item.low_amount for item in strong_evidence.allocations),
        2,
    )
    weak_band_width = round(
        sum(item.high_amount - item.low_amount for item in weak_evidence.allocations),
        2,
    )

    assert strong_band_width < weak_band_width
    assert all(
        allocation.low_amount <= allocation.amount <= allocation.high_amount
        for allocation in strong_evidence.allocations + weak_evidence.allocations
    )


def test_validation_prediction_scenarios_order_outputs_but_flag_lost_schedule_shift_on_promotion(
    client: TestClient,
    db_session: Session,
) -> None:
    _create_post_project(
        db_session,
        project_id="project_val_scenario_target",
        name="Validation Scenario Target",
        status=ProjectStatus.bid,
        quote_total=132000,
        duration_weeks=10,
        line_amounts=[
            ("offline", 55440),
            ("online", 43560),
            ("sound", 33000),
        ],
        schedule_ranges=[
            ("Build", date(2026, 4, 1), date(2026, 4, 30), 35.0, "offline"),
            ("Finish", date(2026, 5, 1), date(2026, 6, 30), 65.0, "online"),
        ],
    )
    for index, quote_total in enumerate((124000, 138000, 149000), start=1):
        _create_post_project(
            db_session,
            project_id=f"project_val_scenario_comp_{index}",
            name=f"Validation Scenario Comparable {index}",
            status=ProjectStatus.complete,
            quote_total=quote_total,
            duration_weeks=8 + index,
            line_amounts=[
                ("offline", round(quote_total * 0.42, 2)),
                ("online", round(quote_total * 0.33, 2)),
                ("sound", round(quote_total * 0.25, 2)),
            ],
            schedule_ranges=[
                ("Build", date(2026, 1, 1), date(2026, 1, 31), 30.0, "offline"),
                ("Review", date(2026, 2, 1), date(2026, 2, 28), 30.0, "online"),
                ("Delivery", date(2026, 3, 1), date(2026, 3, 31), 40.0, "sound"),
            ],
            benchmark_actual=round(quote_total * 1.09, 2),
        )
    db_session.commit()

    response = client.post(
        "/api/v1/projects/project_val_scenario_target/prediction-runs",
        headers=_admin_headers(client),
        json={
            "limit": 25,
            "scenarioAssumptions": {
                "downside": {
                    "scheduleShiftMonths": 2,
                    "varianceDeltaPct": 8,
                    "winProbabilityDeltaPct": -18,
                }
            },
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()

    scenarios = {item["scenarioKey"]: item for item in payload["scenarios"]}
    base = scenarios["base"]
    upside = scenarios["upside"]
    downside = scenarios["downside"]

    assert (
        downside["projectedTotalRevenue"]
        < base["projectedTotalRevenue"]
        < upside["projectedTotalRevenue"]
    )
    assert (
        downside["projectedWeightedRevenue"]
        < base["projectedWeightedRevenue"]
        < upside["projectedWeightedRevenue"]
    )
    assert downside["monthlyRevenueSpread"][0]["month"] > base["monthlyRevenueSpread"][0]["month"]

    promote = client.post(
        f"/api/v1/projects/project_val_scenario_target/prediction-runs/{payload['id']}/promote-scenario",
        headers=_admin_headers(client),
        json={
            "scenarioKey": "downside",
            "title": "Downside validation promotion",
            "revisionReason": "Forecast validation",
            "probabilityPercent": 55,
        },
    )
    assert promote.status_code == 200, promote.text

    forecast_response = client.get(
        "/api/v1/forecasts/projects/project_val_scenario_target",
        headers=_admin_headers(client),
    )
    assert forecast_response.status_code == 200, forecast_response.text
    forecast_payload = forecast_response.json()
    current_version = forecast_payload["currentVersion"]

    flags = _validation_flags(
        scenario_months=[item["month"] for item in downside["monthlyRevenueSpread"]],
        forecast_months=[item["month"] for item in current_version["projectMonthlyRollups"]],
    )
    assert "scenario_schedule_shift_not_reflected_in_forecast" in flags


def test_validation_edge_case_overburn_actuals_need_operator_attention(
    db_session: Session,
) -> None:
    actor_id = _admin_actor_id(db_session)
    project_id = _create_post_project(
        db_session,
        project_id="project_val_overburn",
        name="Validation Overburn Project",
        status=ProjectStatus.active,
        quote_total=10000,
        duration_weeks=8,
        line_amounts=[("offline", 10000)],
        schedule_ranges=[
            ("Offline edit", date(2026, 1, 1), date(2026, 3, 31), 100.0, "offline"),
        ],
        actuals=[
            ("offline", date(2026, 1, 15), date(2026, 1, 20), 12000, "January overburn"),
        ],
    )

    version = forecast_service.create_or_clone_version(
        db_session,
        project_id,
        ForecastVersionCreateRequest(title="Overburn validation"),
        actor_id=actor_id,
    )

    line = version.lines[0]
    amounts_by_month = _allocation_amounts_by_month(line)
    assert line.actuals_to_date_amount == 12000
    assert line.remaining_amount == 0
    assert amounts_by_month["2026-01"] == 12000
    assert amounts_by_month["2026-02"] == 0
    assert amounts_by_month["2026-03"] == 0
    assert version.total_amount == 12000

    flags = _validation_flags(
        quote_total=10000,
        forecast_total=version.total_amount,
        forecast_issues=version.issues,
    )
    assert "actuals_exceed_quote_without_explicit_overburn_flag" in flags


def test_project_forecast_exposes_structured_sanity_checks(
    db_session: Session,
) -> None:
    actor_id = _admin_actor_id(db_session)
    project_id = _create_post_project(
        db_session,
        project_id="project_val_runtime_checks",
        name="Runtime Sanity Checks Project",
        status=ProjectStatus.bid,
        quote_total=25000,
        duration_weeks=8,
        line_amounts=[("offline", 25000)],
        schedule_ranges=[
            ("Offline edit", date(2026, 4, 1), date(2026, 5, 31), 100.0, "offline"),
        ],
    )

    forecast_service.create_or_clone_version(
        db_session,
        project_id,
        ForecastVersionCreateRequest(title="Runtime sanity check version"),
        actor_id=actor_id,
    )
    detail_before = forecast_service.get_project_forecast(db_session, project_id)
    assert detail_before.current_version_id is not None
    version_entity = db_session.get(ForecastVersion, detail_before.current_version_id)
    assert version_entity is not None
    version_entity.fallback_tier = None
    db_session.flush()

    detail = forecast_service.get_project_forecast(db_session, project_id)

    assert detail.current_version is not None
    assert "sanityChecks" in detail.model_dump(mode="json", by_alias=True)
    assert any(
        check.key == "fallback_tier_missing"
        for check in detail.current_version.sanity_checks
    )
