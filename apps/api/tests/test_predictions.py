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
    QuoteVersion,
)
from app.models.enums import (
    BenchmarkActualsStatus,
    CetaRowFinancialType,
    MappedActualChangeType,
    ProjectPartyRole,
    ProjectStatus,
    QuoteVersionStatus,
)


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


def _add_project(
    session: Session,
    *,
    project_id: str,
    name: str,
    status: ProjectStatus,
    client_normalized_name: str,
    quote_total: float,
    duration_weeks: int,
    currency_code: str = "GBP",
    benchmark_actual: float | None = None,
    line_amounts: list[tuple[str, float]] | None = None,
    schedule_ranges: list[tuple[str, date, date, float | None, str | None]] | None = None,
) -> None:
    line_amounts = line_amounts or [
        ("offline", quote_total * 0.4),
        ("online", quote_total * 0.35),
        ("grade", quote_total * 0.25),
    ]
    if schedule_ranges is None:
        schedule_ranges = [
            ("Prep", date(2026, 1, 1), date(2026, 1, 31), 45.0, "offline"),
            ("Finish", date(2026, 2, 1), date(2026, 2, 28), 55.0, "online"),
        ]

    client_company_id = _company_id(session, client_normalized_name)
    streamer_company_id = _company_id(session, "netstream")
    discipline_ids = {code: _discipline(session, code).id for code, _ in line_amounts}

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

    session.add(
        ProjectMetadata(
            project_id=project.id,
            format_type="trailer_promo",
            duration_weeks=duration_weeks,
            episode_count=1,
            language="en-GB",
            budget_target=quote_total,
            metadata_json={
                "deliverableKeys": ["final_picture_master", "caption_package"],
                "localizationKeys": ["caption_package:en-GB"],
                "complexityProfile": {
                    "finishing": "complex",
                    "audio": "standard",
                    "vfx": "low",
                },
            },
        )
    )
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
    for index, (discipline_code, _) in enumerate(line_amounts):
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
    )
    session.add(quote_version)
    session.flush()
    quote.current_version_id = quote_version.id

    if benchmark_actual is None:
        return

    variance_amount = benchmark_actual - quote_total
    variance_pct = round((variance_amount / quote_total) * 100, 2)
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


def _add_cost_actuals(
    session: Session,
    *,
    project_id: str,
    rows: list[tuple[str | None, float]],
    currency_code: str = "GBP",
) -> None:
    for index, (discipline_code, amount) in enumerate(rows, start=1):
        discipline_id = _discipline(session, discipline_code).id if discipline_code else None
        day = min(index, 28)
        session.add(
            MappedActual(
                project_id=project_id,
                discipline_id=discipline_id,
                work_date=date(2026, 3, day),
                posting_date=date(2026, 3, day),
                description=f"Cost actual {index}",
                vendor_name="Trusted Vendor",
                amount=amount,
                currency_code=currency_code,
                financial_type=CetaRowFinancialType.cost,
                cost_category_key="third_party" if index % 2 == 0 else "labour",
                revenue_category_key=None,
                actual_business_key=f"{project_id}-cost-{index}",
                supersedes_mapped_actual_id=None,
                is_current=True,
                change_type=MappedActualChangeType.new,
                mapped_by_id=None,
                mapped_at=datetime(2026, 3, day, 12, 0, tzinfo=UTC),
            )
        )


def test_project_predictive_guidance_returns_quote_mix_spread_and_risk_flags(
    client: TestClient,
    db_session: Session,
) -> None:
    _add_project(
        db_session,
        project_id="project_pred_target",
        name="Predictive Target",
        status=ProjectStatus.bid,
        client_normalized_name="north star pictures",
        quote_total=100000,
        duration_weeks=6,
        currency_code="SEK",
        schedule_ranges=[
            ("Launch", date(2026, 4, 1), date(2026, 4, 30), 40.0, "offline"),
            ("Delivery", date(2026, 5, 1), date(2026, 5, 31), 60.0, "online"),
        ],
    )
    _add_project(
        db_session,
        project_id="project_pred_candidate_1",
        name="Predictive Candidate One",
        status=ProjectStatus.complete,
        client_normalized_name="north star pictures",
        quote_total=95000,
        duration_weeks=8,
        currency_code="SEK",
        benchmark_actual=104500,
        schedule_ranges=[
            ("Prep", date(2026, 1, 1), date(2026, 1, 31), 45.0, "offline"),
            ("Finish", date(2026, 2, 1), date(2026, 2, 28), 55.0, "online"),
        ],
    )
    _add_project(
        db_session,
        project_id="project_pred_candidate_2",
        name="Predictive Candidate Two",
        status=ProjectStatus.complete,
        client_normalized_name="north star pictures",
        quote_total=108000,
        duration_weeks=8,
        currency_code="SEK",
        benchmark_actual=118800,
        line_amounts=[
            ("offline", 48600),
            ("online", 32400),
            ("sound", 27000),
        ],
        schedule_ranges=[
            ("Build", date(2026, 2, 1), date(2026, 2, 28), 35.0, "offline"),
            ("Ship", date(2026, 3, 1), date(2026, 3, 31), 65.0, "sound"),
        ],
    )
    _add_project(
        db_session,
        project_id="project_pred_candidate_3",
        name="Predictive Candidate Three",
        status=ProjectStatus.complete,
        client_normalized_name="north star pictures",
        quote_total=120000,
        duration_weeks=9,
        currency_code="SEK",
        benchmark_actual=126000,
        line_amounts=[
            ("offline", 60000),
            ("grade", 36000),
            ("sound", 24000),
        ],
        schedule_ranges=[
            ("Picture", date(2026, 3, 1), date(2026, 3, 31), 50.0, "offline"),
            ("Audio", date(2026, 4, 1), date(2026, 4, 30), 50.0, "sound"),
        ],
    )
    db_session.commit()

    response = client.get(
        "/api/v1/projects/project_pred_target/predictive-guidance",
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["target"]["projectId"] == "project_pred_target"
    assert payload["comparableQuoteRange"] is not None
    assert payload["actualInformedQuoteRange"] is not None
    assert payload["likelyQuoteRange"]["basis"] == "actual_informed_history"
    assert payload["likelyQuoteRange"]["median"] > payload["comparableQuoteRange"]["median"]
    assert payload["modelInfo"]["comparableProjectsUsed"] == 3
    assert payload["modelInfo"]["monthlyProfileCount"] == 3

    assert len(payload["disciplineUsage"]) >= 2
    assert any(
        item["disciplineCode"] == "offline" and item["usageRatePct"] >= 90
        for item in payload["disciplineUsage"]
    )

    assert [item["month"] for item in payload["monthlyRevenueSpread"]] == [
        "2026-04",
        "2026-05",
    ]
    median_share_total = round(
        sum(item["medianSharePct"] for item in payload["monthlyRevenueSpread"]),
        1,
    )
    assert median_share_total == 100.0

    risk_keys = {flag["key"] for flag in payload["overrunRisk"]["flags"]}
    assert "historical_overrun_pattern" in risk_keys
    assert "schedule_compression" in risk_keys
    assert payload["overrunRisk"]["level"] in {"medium", "high"}
    assert {signal["key"] for signal in payload["riskSignals"]}.isdisjoint(
        {"missing_target_schedule_calendar", "insufficient_monthly_history"}
    )


def test_project_predictive_guidance_surfaces_missing_target_calendar_signal(
    client: TestClient,
    db_session: Session,
) -> None:
    _add_project(
        db_session,
        project_id="project_pred_no_calendar_target",
        name="Predictive No Calendar Target",
        status=ProjectStatus.bid,
        client_normalized_name="north star pictures",
        quote_total=100000,
        duration_weeks=6,
        currency_code="SEK",
        schedule_ranges=[],
    )
    for index, quote_total in enumerate((95000, 105000, 118000), start=1):
        _add_project(
            db_session,
            project_id=f"project_pred_no_calendar_candidate_{index}",
            name=f"Predictive No Calendar Candidate {index}",
            status=ProjectStatus.complete,
            client_normalized_name="north star pictures",
            quote_total=quote_total,
            duration_weeks=8,
            currency_code="SEK",
            benchmark_actual=round(quote_total * 1.08, 2),
        )
    db_session.commit()

    response = client.get(
        "/api/v1/projects/project_pred_no_calendar_target/predictive-guidance",
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["monthlyRevenueSpread"] == []
    assert "missing_target_schedule_calendar" in {
        signal["key"] for signal in payload["riskSignals"]
    }


def test_project_predictive_guidance_honors_selected_quote_version_context(
    client: TestClient,
    db_session: Session,
) -> None:
    _add_project(
        db_session,
        project_id="project_pred_vguid_target",
        name="Predictive Version Target",
        status=ProjectStatus.bid,
        client_normalized_name="north star pictures",
        quote_total=100000,
        duration_weeks=6,
        currency_code="GBP",
    )
    for index, quote_total in enumerate((95000, 105000, 118000), start=1):
        _add_project(
            db_session,
            project_id=f"project_pvguid_hist_{index}",
            name=f"Predictive Version Candidate {index}",
            status=ProjectStatus.complete,
            client_normalized_name="north star pictures",
            quote_total=quote_total,
            duration_weeks=8,
            currency_code="GBP",
            benchmark_actual=round(quote_total * 1.08, 2),
        )

    quote = db_session.scalar(select(Quote).where(Quote.project_id == "project_pred_vguid_target"))
    assert quote is not None
    alternate_version = QuoteVersion(
        quote_id=quote.id,
        version_number=2,
        status=QuoteVersionStatus.draft,
        title="Alternative quote version",
        currency_code="GBP",
        subtotal_amount=112000,
        tax_amount=0,
        total_amount=112000,
    )
    db_session.add(alternate_version)
    db_session.commit()

    response = client.get(
        (
            "/api/v1/projects/project_pred_vguid_target/predictive-guidance"
            f"?quoteVersionId={alternate_version.id}"
        ),
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["requestContext"]["quoteVersionId"] == alternate_version.id
    assert payload["target"]["quoteVersionId"] == alternate_version.id


def test_prediction_run_scenarios_include_advisory_spend_outlook_and_scale_by_actual_multiplier(
    client: TestClient,
    db_session: Session,
) -> None:
    _add_project(
        db_session,
        project_id="project_pred_spend_target",
        name="Predictive Spend Target",
        status=ProjectStatus.bid,
        client_normalized_name="north star pictures",
        quote_total=132000,
        duration_weeks=6,
        currency_code="GBP",
        line_amounts=[
            ("offline", 54000),
            ("online", 46200),
            ("sound", 31800),
        ],
        schedule_ranges=[
            ("Prep", date(2026, 4, 1), date(2026, 4, 20), 35.0, "offline"),
            ("Finish", date(2026, 4, 21), date(2026, 5, 31), 65.0, "online"),
        ],
    )
    for index, quote_total in enumerate((124000, 138000, 149000), start=1):
        _add_project(
            db_session,
            project_id=f"project_pred_spend_candidate_{index}",
            name=f"Predictive Spend Candidate {index}",
            status=ProjectStatus.complete,
            client_normalized_name="north star pictures",
            quote_total=quote_total,
            duration_weeks=8 + index,
            currency_code="GBP",
            benchmark_actual=round(quote_total * 1.09, 2),
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
        )

    _add_cost_actuals(
        db_session,
        project_id="project_pred_spend_target",
        currency_code="GBP",
        rows=[("offline", 18000), ("online", 9000)],
    )
    _add_cost_actuals(
        db_session,
        project_id="project_pred_spend_candidate_1",
        currency_code="GBP",
        rows=[("offline", 28000), ("online", 12000), ("sound", 8000)],
    )
    _add_cost_actuals(
        db_session,
        project_id="project_pred_spend_candidate_2",
        currency_code="GBP",
        rows=[("offline", 32000), ("online", 15000), ("sound", 7000)],
    )
    _add_cost_actuals(
        db_session,
        project_id="project_pred_spend_candidate_3",
        currency_code="GBP",
        rows=[("offline", 29000), ("online", 13000), ("sound", 10000)],
    )
    db_session.commit()

    response = client.post(
        "/api/v1/projects/project_pred_spend_target/prediction-runs",
        headers=_admin_headers(client),
        json={
            "limit": 25,
            "scenarioAssumptions": {
                "upside": {"actualMultiplier": 0.9, "varianceDeltaPct": -3},
                "downside": {"actualMultiplier": 1.2, "varianceDeltaPct": 6},
            },
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()

    scenarios = {item["scenarioKey"]: item for item in payload["scenarios"]}
    base = scenarios["base"]
    upside = scenarios["upside"]
    downside = scenarios["downside"]

    assert base["spendSummary"] is not None
    assert base["spendSummary"]["basis"] == "comparable_cost_history"
    assert base["spendSummary"]["predictedTotalCost"] >= base["spendSummary"]["currentActualCost"]
    assert len(base["spendSummary"]["disciplineSpend"]) >= 2
    assert downside["spendSummary"]["predictedTotalCost"] > base["spendSummary"]["predictedTotalCost"]
    assert upside["spendSummary"]["predictedTotalCost"] < base["spendSummary"]["predictedTotalCost"]
    assert downside["spendSummary"]["currentActualCost"] == base["spendSummary"]["currentActualCost"]
    assert all(
        item["predictedTotalCost"] >= item["currentActualCost"]
        for item in downside["spendSummary"]["disciplineSpend"]
    )


def test_prediction_run_spend_outlook_reports_not_available_without_cost_history(
    client: TestClient,
    db_session: Session,
) -> None:
    _add_project(
        db_session,
        project_id="project_pred_spend_gap_target",
        name="Predictive Spend Gap Target",
        status=ProjectStatus.bid,
        client_normalized_name="north star pictures",
        quote_total=98000,
        duration_weeks=5,
        currency_code="GBP",
    )
    for index, quote_total in enumerate((92000, 101000, 110000), start=1):
        _add_project(
            db_session,
            project_id=f"project_pred_spend_gap_candidate_{index}",
            name=f"Predictive Spend Gap Candidate {index}",
            status=ProjectStatus.complete,
            client_normalized_name="north star pictures",
            quote_total=quote_total,
            duration_weeks=7 + index,
            currency_code="GBP",
            benchmark_actual=round(quote_total * 1.07, 2),
        )
    db_session.commit()

    response = client.post(
        "/api/v1/projects/project_pred_spend_gap_target/prediction-runs",
        headers=_admin_headers(client),
        json={"limit": 25},
    )
    assert response.status_code == 201, response.text
    payload = response.json()

    base = next(item for item in payload["scenarios"] if item["scenarioKey"] == "base")
    assert base["spendSummary"] is not None
    assert base["spendSummary"]["basis"] == "insufficient_cost_history"
    assert base["spendSummary"]["predictedTotalCost"] is None
    assert base["spendSummary"]["predictedRemainingCost"] is None
    assert base["spendSummary"]["disciplineSpend"] == []


def test_prediction_run_endpoints_support_overrides_scenarios_and_forecast_promotion(
    client: TestClient,
    db_session: Session,
) -> None:
    _add_project(
        db_session,
        project_id="project_pred_run_target",
        name="Predictive Run Target",
        status=ProjectStatus.bid,
        client_normalized_name="north star pictures",
        quote_total=132000,
        duration_weeks=6,
        currency_code="GBP",
        schedule_ranges=[
            ("Prep", date(2026, 4, 1), date(2026, 4, 20), 35.0, "offline"),
            ("Finish", date(2026, 4, 21), date(2026, 5, 31), 65.0, "online"),
        ],
    )
    for index, quote_total in enumerate((124000, 138000, 149000), start=1):
        _add_project(
            db_session,
            project_id=f"project_pred_run_candidate_{index}",
            name=f"Predictive Run Candidate {index}",
            status=ProjectStatus.complete,
            client_normalized_name="north star pictures",
            quote_total=quote_total,
            duration_weeks=8 + index,
            currency_code="GBP",
            benchmark_actual=round(quote_total * 1.09, 2),
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
        )
    _add_cost_actuals(
        db_session,
        project_id="project_pred_run_target",
        currency_code="GBP",
        rows=[("offline", 17500), ("online", 9500)],
    )
    _add_cost_actuals(
        db_session,
        project_id="project_pred_run_candidate_1",
        currency_code="GBP",
        rows=[("offline", 28500), ("online", 12500), ("sound", 7000)],
    )
    _add_cost_actuals(
        db_session,
        project_id="project_pred_run_candidate_2",
        currency_code="GBP",
        rows=[("offline", 31000), ("online", 14250), ("sound", 7750)],
    )
    _add_cost_actuals(
        db_session,
        project_id="project_pred_run_candidate_3",
        currency_code="GBP",
        rows=[("offline", 32750), ("online", 15000), ("sound", 8500)],
    )
    db_session.commit()

    response = client.post(
        "/api/v1/projects/project_pred_run_target/prediction-runs",
        headers=_admin_headers(client),
        json={
            "limit": 25,
            "scenarioAssumptions": {
                "downside": {
                    "actualMultiplier": 1.15,
                    "scheduleShiftMonths": 1,
                    "varianceDeltaPct": 6,
                    "winProbabilityDeltaPct": -12,
                }
            },
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()

    run_id = payload["id"]
    assert payload["fallbackTier"] == "high_similarity_history"
    assert payload["featureSnapshot"]["maturityStage"] == "stage_2"
    assert payload["modelInfo"]["comparableProjectsUsed"] >= 3
    assert len(payload["scenarios"]) == 3
    downside_scenario = next(
        item for item in payload["scenarios"] if item["scenarioKey"] == "downside"
    )
    assert downside_scenario["updatedAt"] is not None
    assert downside_scenario["spendSummary"] is not None
    assert downside_scenario["assumptionOverrides"]["scheduleShiftMonths"] == 1
    assert downside_scenario["assumptionOverrides"]["actualMultiplier"] == 1.15
    assert downside_scenario["projectedWeightedRevenue"] is not None

    response = client.get(
        "/api/v1/projects/project_pred_run_target/prediction-runs",
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    list_payload = response.json()
    assert [item["id"] for item in list_payload["items"]] == [run_id]

    response = client.patch(
        f"/api/v1/projects/project_pred_run_target/prediction-runs/{run_id}/overrides",
        headers=_admin_headers(client),
        json={
            "items": [
                {
                    "moduleKey": "quote_guidance",
                    "targetKey": "overall_quote",
                    "status": "partial_accept",
                    "overrideValue": {
                        "recommendedLow": 138000,
                        "recommendedMedian": 144500,
                        "recommendedHigh": 151000,
                    },
                    "note": "Adjusted for strategic account positioning.",
                },
                {
                    "moduleKey": "win_probability",
                    "targetKey": "win_probability",
                    "status": "manual_override",
                    "overrideValue": {
                        "probabilityPct": 63,
                    },
                    "note": "Sales lead confirmed stronger client pull-through.",
                },
            ]
        },
    )
    assert response.status_code == 200, response.text
    override_payload = response.json()
    assert override_payload["likelyQuoteRange"]["acceptanceStatus"] == "partial_accept"
    assert override_payload["likelyQuoteRange"]["recommendedMedian"] == 144500
    assert override_payload["winProbability"]["overrideStatus"] == "manual_override"
    assert override_payload["winProbability"]["probabilityPct"] == 63
    downside_scenario = next(
        item for item in override_payload["scenarios"] if item["scenarioKey"] == "downside"
    )

    response = client.patch(
        f"/api/v1/projects/project_pred_run_target/prediction-runs/{run_id}/scenarios/downside",
        headers=_admin_headers(client),
        json={
            "expectedUpdatedAt": downside_scenario["updatedAt"],
            "assumptionOverrides": {
                "actualMultiplier": 1.2,
                "scheduleShiftMonths": 2,
                "varianceDeltaPct": 8,
                "winProbabilityDeltaPct": -18,
            },
        },
    )
    assert response.status_code == 200, response.text
    scenario_payload = response.json()
    downside_scenario = next(
        item for item in scenario_payload["scenarios"] if item["scenarioKey"] == "downside"
    )
    assert downside_scenario["assumptionOverrides"]["actualMultiplier"] == 1.2
    assert downside_scenario["assumptionOverrides"]["scheduleShiftMonths"] == 2
    assert downside_scenario["spendSummary"]["predictedTotalCost"] >= downside_scenario["spendSummary"]["currentActualCost"]
    assert downside_scenario["monthlyRevenueSpread"][0]["month"] >= "2026-06"

    response = client.post(
        f"/api/v1/projects/project_pred_run_target/prediction-runs/{run_id}/promote-scenario",
        headers=_admin_headers(client),
        json={
            "scenarioKey": "downside",
            "title": "Downside reforecast draft",
            "notesText": "Promoted from predictive scenario workspace.",
            "revisionReason": "Scenario planning handoff",
            "probabilityPercent": 55,
        },
    )
    assert response.status_code == 200, response.text
    promote_payload = response.json()
    assert promote_payload["predictionRunId"] == run_id
    promoted_forecast_version_id = promote_payload["promotedForecastVersionId"]

    forecast_version = db_session.get(ForecastVersion, promoted_forecast_version_id)
    assert forecast_version is not None
    assert forecast_version.title == "Downside reforecast draft"
    assert float(forecast_version.probability_percent) == 55
    assert float(forecast_version.total_amount) != downside_scenario["spendSummary"]["predictedTotalCost"]
    assert float(forecast_version.total_amount) > downside_scenario["spendSummary"]["predictedTotalCost"]
    assert forecast_version.scenario_key == "downside"
    assert forecast_version.engine_source == "unified_forecast_engine"
    assert forecast_version.prediction_run_id == run_id
    assert forecast_version.prediction_scenario_key == "downside"
    assert len(forecast_version.lines) >= 1
    assert any(
        line.forecast_method_key in {"hybrid", "curve", "milestone"}
        for line in forecast_version.lines
    )
    assert any(
        allocation.low_amount is not None and allocation.high_amount is not None
        for line in forecast_version.lines
        for allocation in line.allocations
    )

    response = client.get(
        f"/api/v1/projects/project_pred_run_target/prediction-runs/{run_id}",
        headers=_admin_headers(client),
    )
    assert response.status_code == 200, response.text
    refreshed_payload = response.json()
    promoted_scenario = next(
        item for item in refreshed_payload["scenarios"] if item["scenarioKey"] == "downside"
    )
    assert promoted_scenario["promotedForecastVersionId"] == promoted_forecast_version_id
    assert promoted_scenario["promotedAt"] is not None
