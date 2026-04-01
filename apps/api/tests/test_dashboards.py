# ruff: noqa: E501

from __future__ import annotations

import csv
import io
import os
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import ForecastVersion, User
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


def test_operational_dashboard_returns_sections_and_filter_options(client: TestClient) -> None:
    response = client.get("/api/v1/dashboards/operational", headers=_admin_headers(client))

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["summaryCards"]
    assert body["salesPipeline"]["stages"]
    assert body["monthlyRevenueForecast"]["months"]
    assert body["awardedLostTrend"]["months"]
    assert body["quoteActualVariance"]["completeActualsCount"] == 4
    assert body["benchmarkOverview"]["benchmarkProjectCount"] == 5
    assert any(option["id"] == "project_red_room" for option in body["filterOptions"]["projects"])


def test_operational_dashboard_filters_to_selected_project(client: TestClient) -> None:
    response = client.get(
        "/api/v1/dashboards/operational?projectId=project_red_room",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["appliedFilters"]["projectId"] == "project_red_room"
    bid_stage = next(stage for stage in body["salesPipeline"]["stages"] if stage["status"] == "bid")
    complete_stage = next(
        stage for stage in body["salesPipeline"]["stages"] if stage["status"] == "complete"
    )
    assert bid_stage["projectCount"] == 1
    assert bid_stage["quoteAmount"] == 115000
    assert complete_stage["projectCount"] == 0


def test_forecast_confidence_drilldown_uses_forecast_engine_score(
    client: TestClient,
) -> None:
    forecast_response = client.get(
        "/api/v1/forecasts/projects/project_red_room",
        headers=_admin_headers(client),
    )
    assert forecast_response.status_code == 200, forecast_response.text
    forecast_body = forecast_response.json()

    response = client.get(
        "/api/v1/dashboards/drilldowns/forecast_confidence?projectId=project_red_room",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["view"] == "forecast_confidence"
    assert len(body["rows"]) == 1

    row = body["rows"][0]
    assert row["projectName"] == "Red Room Trailer Campaign"
    assert row["confidenceScore"] == round(
        float(forecast_body["currentVersion"]["confidenceScore"]),
    )
    assert row["confidenceBand"] == "High"
    assert row["scenarioKey"] == "base"


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


def test_project_comparables_route_is_mounted_and_authorized(client: TestClient) -> None:
    response = client.get(
        "/api/v1/projects/project_red_room/comparables",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target"]["projectId"] == "project_red_room"
    assert body["items"]
