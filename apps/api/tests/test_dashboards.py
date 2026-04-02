# ruff: noqa: E501

from __future__ import annotations

import csv
import io
import os
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import (
    Company,
    Discipline,
    ForecastLine,
    ForecastVersion,
    MappedActual,
    MonthlyForecastAllocation,
    Project,
    ProjectDiscipline,
    ProjectParty,
    ProjectScheduleRange,
    Quote,
    QuoteLineItem,
    QuoteSection,
    QuoteVersion,
    User,
)
from app.models.enums import (
    CetaRowFinancialType,
    ForecastVersionStatus,
    MappedActualChangeType,
    ProjectPartyRole,
    ProjectStatus,
    QuoteLineItemType,
    QuoteVersionStatus,
)
from app.modules.forecasts.schemas import (
    ForecastLineAllocationsReplaceRequest,
    ForecastLineMonthAllocationWrite,
    ForecastVersionCreateRequest,
)
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


def _admin_actor_id(db_session) -> str:
    actor_id = db_session.scalar(select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    assert actor_id is not None
    return actor_id


def _create_long_horizon_bid_project(db_session) -> str:
    actor_id = _admin_actor_id(db_session)
    client_company = db_session.scalar(select(Company).order_by(Company.name))
    discipline = db_session.scalar(select(Discipline).where(Discipline.code == "offline"))

    assert client_company is not None
    assert discipline is not None

    project = Project(
        name="Long Horizon Revenue Campaign",
        status=ProjectStatus.bid,
        quote_currency_code="GBP",
        start_date=date(2027, 1, 1),
        end_date=date(2028, 1, 31),
        bid_submitted_at=datetime(2026, 1, 15, tzinfo=UTC),
    )
    db_session.add(project)
    db_session.flush()

    db_session.add(
        ProjectParty(
            project_id=project.id,
            company_id=client_company.id,
            role=ProjectPartyRole.client,
            is_primary=True,
        )
    )
    db_session.add(
        ProjectDiscipline(
            project_id=project.id,
            discipline_id=discipline.id,
            is_primary=True,
            created_at=datetime.now(UTC),
        )
    )
    db_session.add(
        ProjectScheduleRange(
            project_id=project.id,
            discipline_id=discipline.id,
            label="Offline run",
            start_date=date(2027, 1, 1),
            end_date=date(2028, 1, 31),
            allocation_percent=100,
        )
    )

    quote = Quote(project_id=project.id, quote_number="Q-LONG-001", title="Long Horizon Quote")
    db_session.add(quote)
    db_session.flush()

    quote_version = QuoteVersion(
        quote_id=quote.id,
        version_number=1,
        status=QuoteVersionStatus.issued,
        title="Issued long-range quote",
        currency_code="GBP",
        issued_at=datetime(2026, 1, 15, tzinfo=UTC),
        subtotal_amount=130000,
        tax_amount=0,
        total_amount=130000,
    )
    db_session.add(quote_version)
    db_session.flush()
    quote.current_version_id = quote_version.id

    section = QuoteSection(
        quote_version_id=quote_version.id,
        name="Services",
        sort_order=1,
        subtotal_amount=130000,
    )
    db_session.add(section)
    db_session.flush()

    db_session.add(
        QuoteLineItem(
            quote_section_id=section.id,
            sort_order=1,
            line_type=QuoteLineItemType.service,
            discipline_id=discipline.id,
            description="Long horizon offline package",
            quantity=1,
            unit="job",
            rate=130000,
            amount=130000,
        )
    )
    db_session.flush()

    forecast_service.create_or_clone_version(
        db_session,
        project.id,
        ForecastVersionCreateRequest(
            title="Long horizon forecast",
            probability_percent=60,
        ),
        actor_id=actor_id,
    )
    db_session.commit()
    return project.id


def _create_actuals_blend_dashboard_project(db_session) -> str:
    actor_id = _admin_actor_id(db_session)
    client_company = db_session.scalar(select(Company).order_by(Company.name))
    discipline = db_session.scalar(select(Discipline).where(Discipline.code == "offline"))

    assert client_company is not None
    assert discipline is not None

    project = Project(
        name="Dashboard Actuals Blend Project",
        status=ProjectStatus.active,
        quote_currency_code="GBP",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
    )
    db_session.add(project)
    db_session.flush()

    db_session.add(
        ProjectParty(
            project_id=project.id,
            company_id=client_company.id,
            role=ProjectPartyRole.client,
            is_primary=True,
        )
    )
    db_session.add(
        ProjectDiscipline(
            project_id=project.id,
            discipline_id=discipline.id,
            is_primary=True,
            created_at=datetime.now(UTC),
        )
    )
    db_session.add(
        ProjectScheduleRange(
            project_id=project.id,
            discipline_id=discipline.id,
            label="Edit",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 2, 28),
            allocation_percent=100,
        )
    )

    quote = Quote(project_id=project.id, quote_number="Q-DASH-ACTUALS", title="Dashboard Actuals Quote")
    db_session.add(quote)
    db_session.flush()

    quote_version = QuoteVersion(
        quote_id=quote.id,
        version_number=1,
        status=QuoteVersionStatus.issued,
        title="Issued Quote",
        currency_code="GBP",
        subtotal_amount=10000,
        tax_amount=0,
        total_amount=10000,
        created_by_id=actor_id,
    )
    db_session.add(quote_version)
    db_session.flush()
    quote.current_version_id = quote_version.id

    section = QuoteSection(
        quote_version_id=quote_version.id,
        name="Editorial",
        sort_order=1,
        subtotal_amount=10000,
    )
    db_session.add(section)
    db_session.flush()

    db_session.add(
        QuoteLineItem(
            quote_section_id=section.id,
            sort_order=1,
            line_type=QuoteLineItemType.service,
            discipline_id=discipline.id,
            description="Offline edit",
            quantity=1,
            unit="project",
            rate=10000,
            amount=10000,
        )
    )
    db_session.flush()

    db_session.add(
        MappedActual(
            project_id=project.id,
            discipline_id=discipline.id,
            source_ceta_import_id=None,
            source_ceta_import_row_id=None,
            mapping_decision_id=None,
            work_date=date(2026, 1, 15),
            posting_date=date(2026, 1, 20),
            description="January posted actual",
            vendor_name=None,
            amount=2500,
            currency_code="GBP",
            financial_type=CetaRowFinancialType.revenue,
            cost_category_key=None,
            revenue_category_key="editing",
            actual_business_key=f"dashboard-actuals-{project.id}",
            supersedes_mapped_actual_id=None,
            is_current=True,
            change_type=MappedActualChangeType.new,
            mapped_by_id=actor_id,
            mapped_at=quote_version.created_at,
        )
    )
    db_session.flush()

    forecast_service.create_or_clone_version(
        db_session,
        project.id,
        ForecastVersionCreateRequest(title="Dashboard Actuals Forecast"),
        actor_id=actor_id,
    )
    db_session.commit()
    return project.id


def _create_overburn_dashboard_project(db_session) -> str:
    actor_id = _admin_actor_id(db_session)
    client_company = db_session.scalar(select(Company).order_by(Company.name))
    discipline = db_session.scalar(select(Discipline).where(Discipline.code == "offline"))

    assert client_company is not None
    assert discipline is not None

    project = Project(
        name="Dashboard Overburn Project",
        status=ProjectStatus.active,
        quote_currency_code="GBP",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )
    db_session.add(project)
    db_session.flush()

    db_session.add(
        ProjectParty(
            project_id=project.id,
            company_id=client_company.id,
            role=ProjectPartyRole.client,
            is_primary=True,
        )
    )
    db_session.add(
        ProjectDiscipline(
            project_id=project.id,
            discipline_id=discipline.id,
            is_primary=True,
            created_at=datetime.now(UTC),
        )
    )
    db_session.add(
        ProjectScheduleRange(
            project_id=project.id,
            discipline_id=discipline.id,
            label="Edit",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            allocation_percent=100,
        )
    )

    quote = Quote(project_id=project.id, quote_number="Q-DASH-OVERBURN", title="Dashboard Overburn Quote")
    db_session.add(quote)
    db_session.flush()

    quote_version = QuoteVersion(
        quote_id=quote.id,
        version_number=1,
        status=QuoteVersionStatus.issued,
        title="Issued Quote",
        currency_code="GBP",
        subtotal_amount=10000,
        tax_amount=0,
        total_amount=10000,
        created_by_id=actor_id,
    )
    db_session.add(quote_version)
    db_session.flush()
    quote.current_version_id = quote_version.id

    section = QuoteSection(
        quote_version_id=quote_version.id,
        name="Editorial",
        sort_order=1,
        subtotal_amount=10000,
    )
    db_session.add(section)
    db_session.flush()

    db_session.add(
        QuoteLineItem(
            quote_section_id=section.id,
            sort_order=1,
            line_type=QuoteLineItemType.service,
            discipline_id=discipline.id,
            description="Offline edit",
            quantity=1,
            unit="project",
            rate=10000,
            amount=10000,
        )
    )
    db_session.flush()

    db_session.add(
        MappedActual(
            project_id=project.id,
            discipline_id=discipline.id,
            source_ceta_import_id=None,
            source_ceta_import_row_id=None,
            mapping_decision_id=None,
            work_date=date(2026, 1, 15),
            posting_date=date(2026, 1, 20),
            description="Overburn posted actual",
            vendor_name=None,
            amount=12000,
            currency_code="GBP",
            financial_type=CetaRowFinancialType.revenue,
            cost_category_key=None,
            revenue_category_key="editing",
            actual_business_key=f"dashboard-overburn-{project.id}",
            supersedes_mapped_actual_id=None,
            is_current=True,
            change_type=MappedActualChangeType.new,
            mapped_by_id=actor_id,
            mapped_at=quote_version.created_at,
        )
    )
    db_session.flush()

    forecast_service.create_or_clone_version(
        db_session,
        project.id,
        ForecastVersionCreateRequest(title="Dashboard Overburn Forecast"),
        actor_id=actor_id,
    )
    db_session.commit()
    return project.id


def _create_mixed_method_dashboard_project(db_session) -> str:
    actor_id = _admin_actor_id(db_session)
    client_company = db_session.scalar(select(Company).order_by(Company.name))
    discipline = db_session.scalar(select(Discipline).where(Discipline.code == "offline"))

    assert client_company is not None
    assert discipline is not None

    project = Project(
        name="Dashboard Mixed Method Project",
        status=ProjectStatus.bid,
        quote_currency_code="GBP",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )
    db_session.add(project)
    db_session.flush()

    db_session.add(
        ProjectParty(
            project_id=project.id,
            company_id=client_company.id,
            role=ProjectPartyRole.client,
            is_primary=True,
        )
    )
    db_session.add(
        ProjectDiscipline(
            project_id=project.id,
            discipline_id=discipline.id,
            is_primary=True,
            created_at=datetime.now(UTC),
        )
    )
    db_session.add_all(
        [
            ProjectScheduleRange(
                project_id=project.id,
                discipline_id=discipline.id,
                label="Prep",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 15),
                allocation_percent=40,
            ),
            ProjectScheduleRange(
                project_id=project.id,
                discipline_id=discipline.id,
                label="Finish",
                start_date=date(2026, 1, 16),
                end_date=date(2026, 1, 31),
                allocation_percent=60,
            ),
        ]
    )

    quote = Quote(project_id=project.id, quote_number="Q-DASH-MIXED", title="Dashboard Mixed Quote")
    db_session.add(quote)
    db_session.flush()

    quote_version = QuoteVersion(
        quote_id=quote.id,
        version_number=1,
        status=QuoteVersionStatus.issued,
        title="Issued Quote",
        currency_code="GBP",
        subtotal_amount=10000,
        tax_amount=0,
        total_amount=10000,
        created_by_id=actor_id,
    )
    db_session.add(quote_version)
    db_session.flush()
    quote.current_version_id = quote_version.id

    section = QuoteSection(
        quote_version_id=quote_version.id,
        name="Editorial",
        sort_order=1,
        subtotal_amount=10000,
    )
    db_session.add(section)
    db_session.flush()

    db_session.add(
        QuoteLineItem(
            quote_section_id=section.id,
            sort_order=1,
            line_type=QuoteLineItemType.service,
            discipline_id=discipline.id,
            description="Offline edit",
            quantity=1,
            unit="project",
            rate=10000,
            amount=10000,
        )
    )
    db_session.flush()

    version = forecast_service.create_or_clone_version(
        db_session,
        project.id,
        ForecastVersionCreateRequest(title="Dashboard Mixed Forecast"),
        actor_id=actor_id,
    )
    prep_line = next(line for line in version.lines if line.label.endswith("Prep"))

    forecast_service.replace_line_allocations(
        db_session,
        prep_line.id,
        ForecastLineAllocationsReplaceRequest(
            expected_updated_at=version.updated_at,
            allocation_method="manual",
            allocations=[
                ForecastLineMonthAllocationWrite(month="2026-01", amount=4000),
            ],
            reason="Manual January prep phasing.",
        ),
        actor_id=actor_id,
    )

    forecast_service.recalculate_project(
        db_session,
        project.id,
        actor_id=actor_id,
    )
    db_session.commit()
    return project.id


def test_operational_dashboard_returns_sections_and_filter_options(client: TestClient) -> None:
    response = client.get("/api/v1/dashboards/operational", headers=_admin_headers(client))

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["forecastDataset"]["projects"]
    assert body["forecastDataset"]["aggregations"]["totalsByMonth"]
    assert body["forecastDataset"]["aggregations"]["totalsByStatus"]
    assert body["summaryCards"]
    assert body["salesPipeline"]["stages"]
    assert body["monthlyRevenueForecast"]["months"]
    assert body["forecastRevenue"]["months"]
    assert body["forecastRevenue"]["monthlyStatusTotals"]
    assert body["forecastRevenue"]["overallStatusTotals"]
    assert body["forecastRevenue"]["projectRows"]
    assert body["awardedLostTrend"]["months"]
    assert body["quoteActualVariance"]["completeActualsCount"] == 4
    assert body["benchmarkOverview"]["benchmarkProjectCount"] == 5
    assert any(option["id"] == "project_red_room" for option in body["filterOptions"]["projects"])


def test_operational_dashboard_exposes_unified_forecast_dataset_contract(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/dashboards/operational", headers=_admin_headers(client))

    assert response.status_code == 200, response.text
    dataset = response.json()["forecastDataset"]

    assert set(dataset) == {
        "generatedAt",
        "currencyCode",
        "fromMonth",
        "toMonth",
        "scenarioKey",
        "projects",
        "monthlyRows",
        "aggregations",
    }
    assert set(dataset["aggregations"]) == {
        "totalsByMonth",
        "totalsByStatus",
        "totalsByDiscipline",
    }
    assert all(
        set(project) == {
            "projectId",
            "projectName",
            "client",
            "clientId",
            "clientName",
            "status",
            "operationalStatus",
            "quoteVersionId",
            "sourceQuoteVersionId",
            "isSourceQuoteCurrent",
            "forecastVersionId",
            "forecastStatus",
            "scenarioKey",
            "executionStartDate",
            "executionEndDate",
            "totalProjectValue",
            "totalForecastValue",
            "windowForecastValue",
            "weightedTotalForecastValue",
            "windowWeightedForecastValue",
            "probabilityPercent",
            "allocationMethodUsed",
            "allocationProfileKey",
            "basePhasingProfile",
            "manualOverrideLineCount",
            "overrideFlags",
            "confidenceScore",
            "dataSufficiencyScore",
            "fallbackTier",
            "changeSummary",
            "explanationSummary",
            "issues",
            "projectMonths",
            "disciplineRows",
        }
        for project in dataset["projects"]
    )
    assert all(
        set(row) == {
            "month",
            "revenueValue",
            "projectId",
            "discipline",
            "allocationMethod",
            "overrideFlag",
        }
        for row in dataset["monthlyRows"]
    )
    assert {item["status"] for item in dataset["aggregations"]["totalsByStatus"]} == {
        "estimated",
        "awarded",
        "lost",
    }
    assert {row["allocationMethod"] for row in dataset["monthlyRows"]} <= {
        "schedule",
        "manual",
    }
    assert {project["status"] for project in dataset["projects"]} <= {
        "estimated",
        "awarded",
        "lost",
    }
    assert all(
        set(project["overrideFlags"]) == {
            "hasManualOverrides",
            "hasLockedMonths",
            "hasActualizedMonths",
        }
        for project in dataset["projects"]
    )
    assert all(
        set(value) == {
            "month",
            "amount",
            "weightedAmount",
            "actualAmount",
            "bookedAmount",
        }
        for project in dataset["projects"]
        for value in project["projectMonths"]
    )
    assert all(
        set(row) == {
            "disciplineId",
            "disciplineName",
            "allocationMethodUsed",
            "allocationProfileKey",
            "lineCount",
            "manualOverrideLineCount",
            "totalAmount",
            "weightedTotalAmount",
            "monthValues",
        }
        for project in dataset["projects"]
        for row in project["disciplineRows"]
    )


def test_operational_dashboard_filters_to_selected_project(client: TestClient) -> None:
    baseline = client.get("/api/v1/dashboards/operational", headers=_admin_headers(client))
    assert baseline.status_code == 200, baseline.text
    baseline_body = baseline.json()
    target_project = baseline_body["forecastDataset"]["projects"][0]
    from_month = baseline_body["appliedFilters"]["fromMonth"]
    to_month = baseline_body["appliedFilters"]["toMonth"]

    response = client.get(
        f"/api/v1/dashboards/operational?projectId={target_project['projectId']}&fromMonth={from_month}&toMonth={to_month}",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["appliedFilters"]["projectId"] == target_project["projectId"]
    stage_counts = {
        stage["status"]: stage["projectCount"]
        for stage in body["salesPipeline"]["stages"]
    }
    assert sum(stage_counts.values()) == 1


def test_forecast_confidence_drilldown_uses_forecast_engine_score(
    client: TestClient,
) -> None:
    dashboard_response = client.get(
        "/api/v1/dashboards/operational",
        headers=_admin_headers(client),
    )
    assert dashboard_response.status_code == 200, dashboard_response.text
    dashboard_body = dashboard_response.json()
    target_project = dashboard_body["forecastDataset"]["projects"][0]
    from_month = dashboard_body["appliedFilters"]["fromMonth"]
    to_month = dashboard_body["appliedFilters"]["toMonth"]

    forecast_response = client.get(
        f"/api/v1/forecasts/projects/{target_project['projectId']}",
        headers=_admin_headers(client),
    )
    assert forecast_response.status_code == 200, forecast_response.text
    forecast_body = forecast_response.json()

    response = client.get(
        f"/api/v1/dashboards/drilldowns/forecast_confidence?projectId={target_project['projectId']}&fromMonth={from_month}&toMonth={to_month}",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["view"] == "forecast_confidence"
    assert len(body["rows"]) == 1

    row = body["rows"][0]
    assert row["projectName"] == target_project["projectName"]
    assert row["confidenceScore"] == round(
        float(forecast_body["currentVersion"]["confidenceScore"]),
    )
    assert row["confidenceBand"] in {"High", "Medium", "Low"}
    assert row["scenarioKey"] == forecast_body["currentVersion"]["scenarioKey"]


def test_benchmark_overview_aggregates_complete_actuals(client: TestClient) -> None:
    response = client.get("/api/v1/dashboards/operational", headers=_admin_headers(client))

    assert response.status_code == 200, response.text
    body = response.json()
    benchmark_overview = body["benchmarkOverview"]

    assert benchmark_overview["completeActualsCount"] == 4
    assert benchmark_overview["medianVariancePct"] == 7.73
    assert any(
        bucket["key"] == "over" and bucket["projectCount"] == 3
        for bucket in benchmark_overview["varianceBands"]
    )
    assert any(
        discipline["disciplineId"] == "online" and discipline["projectCount"] == 4
        for discipline in benchmark_overview["disciplines"]
    )


def test_dashboard_csv_export_matches_drilldown_columns(client: TestClient) -> None:
    response = client.get(
        "/api/v1/dashboards/drilldowns/variance/csv",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "quotes4-variance.csv" in response.headers["content-disposition"]

    reader = csv.DictReader(io.StringIO(response.text))
    rows = list(reader)
    assert reader.fieldnames == [
        "projectName",
        "disciplineName",
        "quotedAmount",
        "actualAmount",
        "varianceAmount",
        "variancePct",
        "actualsStatus",
        "actualsAsOfDate",
    ]
    assert rows
    assert any(row["projectName"] == "Black Glass Series Launch" for row in rows)


def test_operational_dashboard_supports_scenario_rollups(
    client: TestClient,
    db_session,
) -> None:
    actor_id = db_session.scalar(select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    assert actor_id is not None

    forecast = forecast_service.get_project_forecast(db_session, "project_red_room")
    assert forecast.current_version_id is not None

    created_version = forecast_service.create_or_clone_version(
        db_session,
        "project_red_room",
        ForecastVersionCreateRequest(
            base_version_id=forecast.current_version_id,
            title="Downside scenario portfolio draft",
            probability_percent=55,
        ),
        actor_id=actor_id,
    )
    version_entity = db_session.get(ForecastVersion, created_version.id)
    assert version_entity is not None
    version_entity.scenario_key = "downside"
    version_entity.confidence_score = 61
    version_entity.data_sufficiency_score = 58
    version_entity.updated_at = datetime.now(UTC)
    db_session.commit()

    response = client.get(
        "/api/v1/dashboards/operational?projectId=project_red_room&scenarioKey=downside",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["appliedFilters"]["scenarioKey"] == "downside"
    assert body["monthlyRevenueForecast"]["months"]
    assert any(option["id"] == "downside" for option in body["filterOptions"]["scenarios"])

    response = client.get(
        "/api/v1/dashboards/drilldowns/forecast_confidence?projectId=project_red_room&scenarioKey=downside",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    drilldown = response.json()
    assert len(drilldown["rows"]) == 1
    assert drilldown["rows"][0]["scenarioKey"] == "downside"
    assert drilldown["rows"][0]["confidenceScore"] == 61


def test_forecast_revenue_section_reconciles_months_status_totals_and_project_rows(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/dashboards/operational", headers=_admin_headers(client))

    assert response.status_code == 200, response.text
    payload = response.json()
    revenue = payload["forecastRevenue"]

    monthly_status = {item["month"]: item for item in revenue["monthlyStatusTotals"]}
    assert set(monthly_status) == set(revenue["months"])

    row_month_totals = {
        month: {
            "bid": 0.0,
            "weightedBid": 0.0,
            "awarded": 0.0,
            "active": 0.0,
            "complete": 0.0,
            "booked": 0.0,
            "lost": 0.0,
        }
        for month in revenue["months"]
    }
    overall_totals = {
        item["status"]: {
            "total": item["totalAmount"],
            "weighted": item["weightedTotalAmount"],
        }
        for item in revenue["overallStatusTotals"]
    }
    computed_overall = {
        status: {"total": 0.0, "weighted": 0.0}
        for status in overall_totals
    }

    for row in revenue["projectRows"]:
        computed_overall[row["status"]]["total"] += row["windowRevenue"]
        computed_overall[row["status"]]["weighted"] += row["windowWeightedRevenue"]

        for value in row["monthValues"]:
            if row["status"] == "bid":
                row_month_totals[value["month"]]["bid"] += value["amount"]
                row_month_totals[value["month"]]["weightedBid"] += value["weightedAmount"]
            elif row["status"] == "awarded":
                row_month_totals[value["month"]]["awarded"] += value["amount"]
                row_month_totals[value["month"]]["booked"] += value["bookedAmount"]
            elif row["status"] == "active":
                row_month_totals[value["month"]]["active"] += value["amount"]
                row_month_totals[value["month"]]["booked"] += value["bookedAmount"]
            elif row["status"] == "complete":
                row_month_totals[value["month"]]["complete"] += value["amount"]
                row_month_totals[value["month"]]["booked"] += value["bookedAmount"]
            elif row["status"] == "lost":
                row_month_totals[value["month"]]["lost"] += value["amount"]

    for month, expected in row_month_totals.items():
        actual = monthly_status[month]
        assert actual["bidAmount"] == round(expected["bid"], 2)
        assert actual["weightedBidAmount"] == round(expected["weightedBid"], 2)
        assert actual["awardedAmount"] == round(expected["awarded"], 2)
        assert actual["activeAmount"] == round(expected["active"], 2)
        assert actual["completeAmount"] == round(expected["complete"], 2)
        assert actual["bookedAmount"] == round(expected["booked"], 2)
        assert actual["lostAmount"] == round(expected["lost"], 2)

    for status, totals in computed_overall.items():
        assert overall_totals[status]["total"] == round(totals["total"], 2)
        assert overall_totals[status]["weighted"] == round(totals["weighted"], 2)

    assert any(
        item["status"] == "bid"
        and item["totalAmount"] > item["weightedTotalAmount"]
        for item in revenue["overallStatusTotals"]
    )


def test_forecast_dataset_reconciles_projects_rows_and_aggregations(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/dashboards/operational", headers=_admin_headers(client))

    assert response.status_code == 200, response.text
    dataset = response.json()["forecastDataset"]

    project_lookup = {
        project["projectId"]: project
        for project in dataset["projects"]
    }
    project_window_totals = {project_id: 0.0 for project_id in project_lookup}
    month_totals = {
        item["month"]: 0.0 for item in dataset["aggregations"]["totalsByMonth"]
    }
    status_totals = {
        item["status"]: 0.0 for item in dataset["aggregations"]["totalsByStatus"]
    }
    discipline_totals: dict[str | None, float] = {}

    for row in dataset["monthlyRows"]:
        project_window_totals[row["projectId"]] += row["revenueValue"]
        month_totals[row["month"]] += row["revenueValue"]
        status_totals[project_lookup[row["projectId"]]["status"]] += row["revenueValue"]
        discipline_totals[row["discipline"]] = (
            discipline_totals.get(row["discipline"], 0.0) + row["revenueValue"]
        )

    for project_id, expected_total in project_window_totals.items():
        assert round(expected_total, 2) == round(project_lookup[project_id]["windowForecastValue"], 2)

    for total in dataset["aggregations"]["totalsByMonth"]:
        assert round(month_totals[total["month"]], 2) == round(total["revenueValue"], 2)

    for total in dataset["aggregations"]["totalsByStatus"]:
        assert round(status_totals[total["status"]], 2) == round(total["revenueValue"], 2)

    declared_discipline_totals = {
        item["discipline"]: item["revenueValue"]
        for item in dataset["aggregations"]["totalsByDiscipline"]
    }
    assert set(declared_discipline_totals) == set(discipline_totals)
    for discipline, expected_total in discipline_totals.items():
        assert round(declared_discipline_totals[discipline], 2) == round(expected_total, 2)

    raw_total = round(sum(row["revenueValue"] for row in dataset["monthlyRows"]), 2)
    assert raw_total == round(
        sum(project["windowForecastValue"] for project in dataset["projects"]),
        2,
    )
    assert raw_total == round(
        sum(item["revenueValue"] for item in dataset["aggregations"]["totalsByMonth"]),
        2,
    )
    assert raw_total == round(
        sum(item["revenueValue"] for item in dataset["aggregations"]["totalsByStatus"]),
        2,
    )
    assert raw_total == round(
        sum(item["revenueValue"] for item in dataset["aggregations"]["totalsByDiscipline"]),
        2,
    )


def test_forecast_revenue_section_supports_long_horizon_projects_and_quote_lead_time(
    client: TestClient,
    db_session,
) -> None:
    project_id = _create_long_horizon_bid_project(db_session)

    response = client.get(
        f"/api/v1/dashboards/operational?projectId={project_id}&fromMonth=2027-01&toMonth=2028-01",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    revenue = response.json()["forecastRevenue"]
    assert len(revenue["months"]) == 13
    assert len(revenue["projectRows"]) == 1

    row = revenue["projectRows"][0]
    non_zero_months = [item for item in row["monthValues"] if item["amount"] > 0]

    assert row["projectId"] == project_id
    assert row["spanningMonthCount"] == 13
    assert row["quoteToExecutionLeadMonths"] == 12
    assert row["executionStartDate"] == "2027-01-01"
    assert row["executionEndDate"] == "2028-01-31"
    assert len(non_zero_months) == 13
    assert row["totalRevenue"] == 130000.0
    assert row["windowRevenue"] == 130000.0
    assert row["basePhasingProfile"] == "system_default"
    assert row["forecastMethod"] in {"curve", "hybrid", "linear", "schedule", "manual", "mixed"}
    assert row["disciplineRows"][0]["disciplineName"] == "Offline"


def test_forecast_dataset_supports_mixed_manual_and_schedule_rows(
    client: TestClient,
    db_session,
) -> None:
    project_id = _create_mixed_method_dashboard_project(db_session)

    response = client.get(
        f"/api/v1/dashboards/operational?projectId={project_id}&fromMonth=2026-01&toMonth=2026-01",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    rows = response.json()["forecastDataset"]["monthlyRows"]
    target_rows = [row for row in rows if row["projectId"] == project_id]

    assert len(target_rows) == 2
    assert any(
        row["month"] == "2026-01"
        and row["discipline"] == "offline"
        and row["allocationMethod"] == "manual"
        and row["overrideFlag"] is True
        and row["revenueValue"] == 4000.0
        for row in target_rows
    )
    assert any(
        row["month"] == "2026-01"
        and row["discipline"] == "offline"
        and row["allocationMethod"] == "schedule"
        and row["overrideFlag"] is False
        and row["revenueValue"] == 6000.0
        for row in target_rows
    )


def test_forecast_dataset_reflects_actuals_assimilation(
    client: TestClient,
    db_session,
) -> None:
    project_id = _create_actuals_blend_dashboard_project(db_session)

    response = client.get(
        f"/api/v1/dashboards/operational?projectId={project_id}&fromMonth=2026-01&toMonth=2026-02",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    dataset = response.json()["forecastDataset"]
    assert dataset["projects"][0]["status"] == "awarded"

    january = next(row for row in dataset["monthlyRows"] if row["month"] == "2026-01")
    february = next(row for row in dataset["monthlyRows"] if row["month"] == "2026-02")

    assert january["projectId"] == project_id
    assert january["discipline"] == "offline"
    assert january["allocationMethod"] == "schedule"
    assert january["overrideFlag"] is False
    assert january["revenueValue"] == 2500.0
    assert february["revenueValue"] == 7500.0


def test_forecast_dataset_falls_back_from_invalid_draft_to_latest_valid_version(
    client: TestClient,
    db_session,
) -> None:
    project_id = _create_actuals_blend_dashboard_project(db_session)
    actor_id = _admin_actor_id(db_session)

    forecast = forecast_service.get_project_forecast(db_session, project_id)
    assert forecast.current_version_id is not None
    current_version = db_session.get(ForecastVersion, forecast.current_version_id)
    assert current_version is not None
    if current_version.status != ForecastVersionStatus.locked:
        forecast_service.lock_version(
            db_session,
            forecast.current_version_id,
            actor_id=actor_id,
        )
        db_session.commit()

    invalid_draft = forecast_service.create_or_clone_version(
        db_session,
        project_id,
        ForecastVersionCreateRequest(
            base_version_id=forecast.current_version_id,
            title="Invalid Draft",
        ),
        actor_id=actor_id,
    )
    draft_line = db_session.scalar(
        select(ForecastLine).where(ForecastLine.forecast_version_id == invalid_draft.id)
    )
    assert draft_line is not None
    january_allocation = db_session.scalar(
        select(MonthlyForecastAllocation).where(
            MonthlyForecastAllocation.forecast_line_id == draft_line.id,
            MonthlyForecastAllocation.month == date(2026, 1, 1),
        )
    )
    assert january_allocation is not None
    db_session.delete(january_allocation)
    db_session.commit()

    invalid_version = forecast_service.get_version(db_session, invalid_draft.id)
    assert any(check.blocking for check in invalid_version.lines[0].sanity_checks)

    response = client.get(
        f"/api/v1/dashboards/operational?projectId={project_id}&fromMonth=2026-01&toMonth=2026-02",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    dataset = response.json()["forecastDataset"]
    january = next(row for row in dataset["monthlyRows"] if row["month"] == "2026-01")
    february = next(row for row in dataset["monthlyRows"] if row["month"] == "2026-02")

    assert january["revenueValue"] == 2500.0
    assert february["revenueValue"] == 7500.0
    assert dataset["projects"][0]["totalForecastValue"] == 10000.0


def test_forecast_dataset_keeps_zero_months_and_omits_zero_value_projects_outside_window(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/dashboards/operational?projectId=project_red_room&fromMonth=2040-01&toMonth=2040-03",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    dataset = response.json()["forecastDataset"]

    assert dataset["projects"] == []
    assert dataset["monthlyRows"] == []
    assert [item["month"] for item in dataset["aggregations"]["totalsByMonth"]] == [
        "2040-01",
        "2040-02",
        "2040-03",
    ]
    assert all(item["revenueValue"] == 0.0 for item in dataset["aggregations"]["totalsByMonth"])


def test_dashboard_separates_quote_totals_from_forecast_totals_and_reuses_dataset_rows(
    client: TestClient,
    db_session,
) -> None:
    project_id = _create_overburn_dashboard_project(db_session)

    response = client.get(
        f"/api/v1/dashboards/operational?projectId={project_id}&fromMonth=2026-01&toMonth=2026-02",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    dataset_project = payload["forecastDataset"]["projects"][0]
    revenue_row = payload["forecastRevenue"]["projectRows"][0]
    stage = next(
        item for item in payload["salesPipeline"]["stages"] if item["status"] == "active"
    )

    assert dataset_project["totalForecastValue"] == 12000.0
    assert revenue_row["totalRevenue"] == dataset_project["totalForecastValue"]
    assert revenue_row["windowRevenue"] == dataset_project["totalForecastValue"]
    assert round(sum(row["revenueValue"] for row in payload["forecastDataset"]["monthlyRows"]), 2) == 12000.0
    assert stage["quoteAmount"] == 10000.0
    assert stage["bookedAmount"] == 10000.0


def test_project_comparables_route_is_mounted_and_authorized(client: TestClient) -> None:
    response = client.get(
        "/api/v1/projects/project_red_room/comparables",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target"]["projectId"] == "project_red_room"
    assert body["items"]
