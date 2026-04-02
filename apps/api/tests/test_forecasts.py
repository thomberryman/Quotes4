from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models import (
    Discipline,
    ForecastLine,
    ForecastPhasingChange,
    ForecastPhasingDraft,
    MappedActual,
    MonthlyForecastAllocation,
    Project,
    ProjectDiscipline,
    ProjectMetadata,
    ProjectScheduleRange,
    Quote,
    QuoteLineItem,
    QuoteSection,
    QuoteVersion,
    ReferenceDataValue,
    User,
)
from app.models.enums import (
    CetaRowFinancialType,
    MappedActualChangeType,
    ProjectStatus,
    QuoteLineItemType,
    QuoteVersionStatus,
    RevenueAllocationMethod,
)
from app.modules.forecasts.schemas import (
    ForecastLineAllocationsReplaceRequest,
    ForecastLineMonthAllocationWrite,
    ForecastPhasingCellWrite,
    ForecastPhasingRowUpdateRequest,
    ForecastVersionCreateRequest,
)
from app.modules.forecasts.service import forecast_service


def _login(client) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/session",
        json={
            "email": os.environ["DEV_ADMIN_EMAIL"],
            "password": os.environ["DEV_ADMIN_PASSWORD"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _admin_headers(client) -> dict[str, str]:
    session = _login(client)
    return {"Authorization": f"Bearer {session['accessToken']}"}


def _admin_actor_id(db_session) -> str:
    actor_id = db_session.scalar(select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    assert actor_id is not None
    return actor_id


def _create_revenue_phasing_project(
    db_session,
    *,
    name: str,
    line_amounts: list[tuple[str, float]],
) -> tuple[str, str]:
    actor_id = _admin_actor_id(db_session)
    start_date = date(2026, 6, 1)
    end_date = date(2026, 8, 31)
    disciplines = {
        discipline_code: db_session.scalar(
            select(Discipline).where(Discipline.code == discipline_code)
        )
        for discipline_code, _amount in line_amounts
    }

    assert all(discipline is not None for discipline in disciplines.values())

    project = Project(
        name=name,
        status=ProjectStatus.bid,
        quote_currency_code="GBP",
        start_date=start_date,
        end_date=end_date,
        estimated_execution_start_date=start_date,
        estimated_execution_end_date=end_date,
        revenue_allocation_method=RevenueAllocationMethod.cadence_profile,
        cadence_profile_type="flat_equal",
    )
    db_session.add(project)
    db_session.flush()

    for discipline_code, discipline in disciplines.items():
        assert discipline is not None
        db_session.add(
            ProjectDiscipline(
                project_id=project.id,
                discipline_id=discipline.id,
                is_primary=discipline_code == line_amounts[0][0],
                created_at=datetime.now(UTC),
            )
        )
        db_session.add(
            ProjectScheduleRange(
                project_id=project.id,
                discipline_id=discipline.id,
                label=f"{discipline.name} delivery",
                start_date=start_date,
                end_date=end_date,
                allocation_percent=100,
            )
        )

    total_amount = round(sum(amount for _discipline_code, amount in line_amounts), 2)
    quote = Quote(project_id=project.id, quote_number=f"Q-{project.id[-6:]}", title=name)
    db_session.add(quote)
    db_session.flush()

    quote_version = QuoteVersion(
        quote_id=quote.id,
        version_number=1,
        status=QuoteVersionStatus.issued,
        title=f"{name} quote",
        currency_code="GBP",
        subtotal_amount=total_amount,
        tax_amount=0,
        total_amount=total_amount,
        created_by_id=actor_id,
    )
    db_session.add(quote_version)
    db_session.flush()
    quote.current_version_id = quote_version.id

    section = QuoteSection(
        quote_version_id=quote_version.id,
        name="Services",
        sort_order=1,
        subtotal_amount=total_amount,
    )
    db_session.add(section)
    db_session.flush()

    for index, (discipline_code, amount) in enumerate(line_amounts, start=1):
        discipline = disciplines[discipline_code]
        assert discipline is not None
        db_session.add(
            QuoteLineItem(
                quote_section_id=section.id,
                sort_order=index,
                line_type=QuoteLineItemType.service,
                discipline_id=discipline.id,
                description=f"{discipline.name} services",
                quantity=1,
                unit="project",
                rate=amount,
                amount=amount,
            )
        )
    db_session.flush()

    version = forecast_service.create_or_clone_version(
        db_session,
        project.id,
        ForecastVersionCreateRequest(title=f"{name} forecast"),
        actor_id=actor_id,
    )
    db_session.commit()
    return project.id, version.id


def _row_amounts_by_month(row: dict[str, object]) -> dict[str, float]:
    return {
        cell["month"]: cell["amount"]
        for cell in row["cells"]
    }


def _row_cell(row: dict[str, object], month: str) -> dict[str, object]:
    return next(cell for cell in row["cells"] if cell["month"] == month)


def test_forecast_policy_exposes_persisted_profiles_and_templates(client) -> None:
    session_response = client.post(
        "/api/v1/auth/session",
        json={
            "email": os.environ["DEV_ADMIN_EMAIL"],
            "password": os.environ["DEV_ADMIN_PASSWORD"],
        },
    )
    assert session_response.status_code == 200, session_response.text

    response = client.get(
        "/api/v1/forecasts/policy",
        headers={"Authorization": f"Bearer {session_response.json()['accessToken']}"},
    )

    assert response.status_code == 200
    payload = response.json()

    profile_keys = {item["key"] for item in payload["curveProfiles"]}
    template_keys = {item["key"] for item in payload["sequencingTemplates"]}

    assert {"even", "front_loaded", "mid_loaded", "back_loaded"} <= profile_keys
    assert {"default", "trailer_promo", "episodic_localisation"} <= template_keys


def test_forecast_accuracy_summary_uses_seeded_sample_data(client) -> None:
    session_response = client.post(
        "/api/v1/auth/session",
        json={
            "email": os.environ["DEV_ADMIN_EMAIL"],
            "password": os.environ["DEV_ADMIN_PASSWORD"],
        },
    )
    assert session_response.status_code == 200, session_response.text

    response = client.get(
        "/api/v1/forecasts/accuracy",
        headers={"Authorization": f"Bearer {session_response.json()['accessToken']}"},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["metrics"] == {
        "comparisonProjectCount": 5,
        "resolvedProjectCount": 4,
        "partialProjectCount": 1,
        "monthlyCoverageProjectCount": 0,
        "disciplineCoverageProjectCount": 4,
        "meanAbsoluteError": 9250.0,
        "meanAbsolutePercentageError": 7.58,
        "weightedAbsolutePercentageError": 7.66,
        "meanBiasAmount": 9250.0,
        "meanBiasPercentage": 7.58,
        "withinTenPercentRate": 100.0,
    }

    assert payload["forecastVsActual"][0] == {
        "projectId": "project_blue_echo",
        "projectName": "Blue Echo Spot Burst",
        "projectStatus": "complete",
        "scenarioKey": "base",
        "confidenceScore": pytest.approx(60.9),
        "actualsStatus": "complete",
        "actualSource": "benchmark_summary",
        "forecastAmount": 116000.0,
        "actualAmount": 128500.0,
        "varianceAmount": 12500.0,
        "variancePct": 10.78,
        "absolutePercentageError": 9.73,
    }

    assert payload["monthlyVariance"] == []

    assert [item["disciplineCode"] for item in payload["disciplineVariance"][:3]] == [
        "online",
        "offline",
        "grade",
    ]
    assert payload["disciplineVariance"][0]["meanAbsolutePercentageError"] == 8.04
    assert payload["disciplineVariance"][0]["sampleCount"] == 4

    assert payload["confidenceCalibration"] == [
        {
            "bucketKey": "medium",
            "label": "Medium confidence",
            "projectCount": 4,
            "averageConfidenceScore": pytest.approx(68.33),
            "averageAccuracyScore": 92.42,
            "meanAbsolutePercentageError": 7.58,
            "overconfidenceGap": -24.09,
            "withinRangeRate": 100.0,
        }
    ]

    assert payload["scenarioAccuracy"] == [
        {
            "scenarioKey": "base",
            "projectCount": 4,
            "meanVarianceAmount": 2959.05,
            "meanAbsolutePercentageError": 3.38,
            "meanBiasPercentage": 2.21,
            "withinTenPercentRate": 100.0,
            "closestToActualRate": 75.0,
        },
        {
            "scenarioKey": "upside",
            "projectCount": 4,
            "meanVarianceAmount": -1752.58,
            "meanAbsolutePercentageError": 4.77,
            "meanBiasPercentage": -1.71,
            "withinTenPercentRate": 100.0,
            "closestToActualRate": 25.0,
        },
        {
            "scenarioKey": "downside",
            "projectCount": 4,
            "meanVarianceAmount": 14738.14,
            "meanAbsolutePercentageError": 11.98,
            "meanBiasPercentage": 11.98,
            "withinTenPercentRate": 50.0,
            "closestToActualRate": 0.0,
        },
    ]

    assert [
        (item["kind"], item["label"])
        for item in payload["weaknesses"]
    ] == [
        ("scenario", "Downside"),
        ("project", "Blue Echo Spot Burst"),
        ("discipline", "Online"),
    ]
    assert [item["title"] for item in payload["recommendations"]] == [
        "Retune Online discipline assumptions",
        "Rebalance scenario multipliers against realized outcomes",
        "Increase month-level actual coverage before trusting timing accuracy",
    ]


def test_recalculate_uses_discipline_prediction_bias_in_line_plan(
    db_session,
    monkeypatch,
) -> None:
    actor_id = db_session.scalar(select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    discipline = db_session.scalar(select(Discipline).where(Discipline.code == "offline"))

    assert actor_id is not None
    assert discipline is not None

    db_session.add(
        ReferenceDataValue(
            category="forecast_curve_profile",
            key="flat_offline",
            label="Flat Offline",
            sort_order=1,
            is_active=True,
            metadata_json={
                "shapeKey": "even",
                "description": "Neutral offline baseline for timing tests.",
                "defaultDisciplineCodes": ["offline"],
            },
        )
    )

    project = Project(
        name="Prediction Bias Forecast Project",
        status=ProjectStatus.bid,
        quote_currency_code="GBP",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
    )
    db_session.add(project)
    db_session.flush()

    db_session.add(
        ProjectMetadata(
            project_id=project.id,
            budget_target=10000,
            metadata_json={
                "forecasting": {
                    "sequencingOverrides": {
                        "offline": {
                            "templateKey": "project_override",
                            "stageKey": "editorial",
                            "startPct": 0.0,
                            "endPct": 1.0,
                            "overlapPct": 0.0,
                        }
                    }
                }
            },
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

    quote = Quote(project_id=project.id, quote_number="Q-PRED-BIAS", title="Prediction Bias Quote")
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

    monkeypatch.setattr(
        forecast_service,
        "_load_prediction_detail",
        lambda session, project, scenario_key="base": {
            "runId": None,
            "scenarioKey": scenario_key,
            "confidenceScore": 52.0,
            "dataSufficiencyScore": 49.0,
            "fallbackTier": "system_default",
            "methodologySummary": "Prediction discipline signal timing test.",
            "scenario": {
                "scenarioKey": scenario_key,
                "disciplineUsage": [
                    {
                        "disciplineId": discipline.id,
                        "disciplineCode": "offline",
                        "predictedAmountMedian": 8000,
                        "predictedSharePct": 80,
                        "predictedVariancePct": 18,
                        "overrunRisk": "high",
                        "confidenceScore": 68,
                        "dataSufficiencyScore": 61,
                        "fallbackTier": "discipline_baseline",
                    }
                ],
                "monthlyRevenueSpread": [],
            },
        },
    )

    version = forecast_service.create_or_clone_version(
        db_session,
        project.id,
        ForecastVersionCreateRequest(title="Prediction Bias Draft"),
        actor_id=actor_id,
    )

    assert len(version.lines) == 1
    line = version.lines[0]
    amounts_by_month = {allocation.month: allocation.amount for allocation in line.allocations}

    assert line.allocation_profile_key == "flat_offline"
    assert line.forecast_method_key == "hybrid"
    assert amounts_by_month["2026-02"] > amounts_by_month["2026-01"]
    assert line.fallback_tier == "discipline_baseline"
    assert line.confidence_score is not None and line.confidence_score > 55
    assert line.forecast_inputs is not None
    assert float(line.forecast_inputs["quoteVsPredictionDeltaPct"]) > 20
    assert any(item.key == "discipline_prediction" for item in line.explanations)
    assert line.allocations[-1].high_amount is not None
    assert line.allocations[-1].high_amount > line.allocations[-1].amount

    db_session.commit()


def test_recalculate_applies_schedule_shift_and_expansion_without_project_curve(
    db_session,
    monkeypatch,
) -> None:
    actor_id = db_session.scalar(select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    discipline = db_session.scalar(select(Discipline).where(Discipline.code == "offline"))

    assert actor_id is not None
    assert discipline is not None

    db_session.add(
        ReferenceDataValue(
            category="forecast_curve_profile",
            key="flat_offline",
            label="Flat Offline",
            sort_order=1,
            is_active=True,
            metadata_json={
                "shapeKey": "even",
                "defaultDisciplineCodes": ["offline"],
            },
        )
    )

    project = Project(
        name="Shifted Forecast Project",
        status=ProjectStatus.bid,
        quote_currency_code="GBP",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
    )
    db_session.add(project)
    db_session.flush()

    db_session.add(
        ProjectMetadata(
            project_id=project.id,
            budget_target=9000,
            metadata_json={
                "forecasting": {
                    "sequencingOverrides": {
                        "offline": {
                            "templateKey": "project_override",
                            "stageKey": "editorial",
                            "startPct": 0.0,
                            "endPct": 1.0,
                            "overlapPct": 0.0,
                        }
                    },
                    "scheduleAdjustment": {
                        "expansionPct": 50,
                    },
                }
            },
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

    quote = Quote(project_id=project.id, quote_number="Q-SHIFTED", title="Shifted Quote")
    db_session.add(quote)
    db_session.flush()

    quote_version = QuoteVersion(
        quote_id=quote.id,
        version_number=1,
        status=QuoteVersionStatus.issued,
        title="Issued Quote",
        currency_code="GBP",
        subtotal_amount=9000,
        tax_amount=0,
        total_amount=9000,
        created_by_id=actor_id,
    )
    db_session.add(quote_version)
    db_session.flush()
    quote.current_version_id = quote_version.id

    section = QuoteSection(
        quote_version_id=quote_version.id,
        name="Editorial",
        sort_order=1,
        subtotal_amount=9000,
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
            rate=9000,
            amount=9000,
        )
    )
    db_session.flush()

    monkeypatch.setattr(
        forecast_service,
        "_load_prediction_detail",
        lambda session, project, scenario_key="base": {
            "runId": None,
            "scenarioKey": scenario_key,
            "confidenceScore": 58.0,
            "dataSufficiencyScore": 54.0,
            "fallbackTier": "same_project_type_all_clients",
            "methodologySummary": "Scenario shift fallback timing test.",
            "scenario": {
                "scenarioKey": scenario_key,
                "disciplineUsage": [],
                "monthlyRevenueSpread": [],
                "assumptionOverrides": {
                    "scheduleShiftMonths": 1,
                },
            },
        },
    )

    version = forecast_service.create_or_clone_version(
        db_session,
        project.id,
        ForecastVersionCreateRequest(title="Shifted Draft"),
        actor_id=actor_id,
    )

    assert len(version.lines) == 1
    line = version.lines[0]
    months = [allocation.month for allocation in line.allocations]

    assert months == ["2026-02", "2026-03", "2026-04"]
    assert line.forecast_inputs is not None
    assert line.forecast_inputs["appliedScheduleShiftMonths"] == 1
    assert float(line.forecast_inputs["durationScaleMultiplier"]) > 1
    assert any(item.key == "schedule_adjustment" for item in line.explanations)

    db_session.commit()


def test_recalculate_preserves_partial_manual_override_without_collapsing_split_lines(
    db_session,
) -> None:
    actor_id = db_session.scalar(select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    discipline = db_session.scalar(select(Discipline).where(Discipline.code == "offline"))

    assert actor_id is not None
    assert discipline is not None

    project = Project(
        name="Split Forecast Project",
        status=ProjectStatus.bid,
        quote_currency_code="GBP",
    )
    db_session.add(project)
    db_session.flush()

    db_session.add_all(
        [
            ProjectScheduleRange(
                project_id=project.id,
                discipline_id=discipline.id,
                label="Prep",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                allocation_percent=40,
            ),
            ProjectScheduleRange(
                project_id=project.id,
                discipline_id=discipline.id,
                label="Finish",
                start_date=date(2026, 2, 1),
                end_date=date(2026, 2, 28),
                allocation_percent=60,
            ),
        ]
    )

    quote = Quote(project_id=project.id, quote_number="Q-SPLIT", title="Split Quote")
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
        ForecastVersionCreateRequest(title="Draft Forecast"),
        actor_id=actor_id,
    )

    assert len(version.lines) == 2
    prep_line = next(line for line in version.lines if line.label.endswith("Prep"))

    version = forecast_service.replace_line_allocations(
        db_session,
        prep_line.id,
        ForecastLineAllocationsReplaceRequest(
            expected_updated_at=version.updated_at,
            allocation_method="manual",
            allocations=[
                ForecastLineMonthAllocationWrite(month="2026-01", amount=4000),
            ],
            reason="Front-load prep manually",
        ),
        actor_id=actor_id,
    )

    recalculated, _message = forecast_service.recalculate_project(
        db_session,
        project.id,
        actor_id=actor_id,
    )

    assert recalculated is not None
    assert len(recalculated.lines) == 2
    assert {line.allocation_method for line in recalculated.lines} == {"manual", "schedule"}
    assert sum(line.total_amount for line in recalculated.lines) == 10000

    manual_line = next(line for line in recalculated.lines if line.allocation_method == "manual")
    schedule_line = next(
        line for line in recalculated.lines if line.allocation_method == "schedule"
    )

    assert manual_line.label.endswith("Prep")
    assert manual_line.total_amount == 4000
    assert manual_line.forecast_method_key == "manual"
    assert len(manual_line.allocations) == 1
    assert manual_line.allocations[0].month == "2026-01"
    assert manual_line.allocations[0].amount == 4000
    assert manual_line.allocations[0].weighted_amount == round(
        manual_line.allocations[0].amount * (recalculated.probability_percent / 100),
        2,
    )
    assert manual_line.allocations[0].allocation_source == "manual_override"
    assert schedule_line.label.endswith("Finish")
    assert schedule_line.total_amount == 6000
    assert schedule_line.forecast_method_key in {"curve", "hybrid", "linear"}
    assert recalculated.change_summary is not None
    assert recalculated.change_summary["changedMonthCount"] >= 0

    db_session.commit()


def test_recalculate_uses_persisted_curve_profile_defaults(db_session) -> None:
    actor_id = db_session.scalar(select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    discipline = db_session.scalar(select(Discipline).where(Discipline.code == "offline"))

    assert actor_id is not None
    assert discipline is not None

    db_session.add(
        ReferenceDataValue(
            category="forecast_curve_profile",
            key="late_cash",
            label="Late Cash",
            sort_order=1,
            is_active=True,
            metadata_json={
                "shapeKey": "back_loaded",
                "description": "Push offline revenue later when approvals are slow.",
                "defaultDisciplineCodes": ["offline"],
                "startMultiplier": 0.25,
                "endMultiplier": 2.0,
            },
        )
    )

    project = Project(
        name="Curve Profile Forecast Project",
        status=ProjectStatus.bid,
        quote_currency_code="GBP",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
    )
    db_session.add(project)
    db_session.flush()

    db_session.add(
        ProjectMetadata(
            project_id=project.id,
            budget_target=10000,
            metadata_json={
                "forecasting": {
                    "sequencingOverrides": {
                        "offline": {
                            "templateKey": "project_override",
                            "stageKey": "editorial",
                            "startPct": 0.0,
                            "endPct": 1.0,
                            "overlapPct": 0.0,
                        }
                    }
                }
            },
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

    quote = Quote(project_id=project.id, quote_number="Q-CURVE", title="Curve Profile Quote")
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
        ForecastVersionCreateRequest(title="Curve Profile Draft"),
        actor_id=actor_id,
    )

    assert len(version.lines) == 1
    line = version.lines[0]
    amounts_by_month = {allocation.month: allocation.amount for allocation in line.allocations}

    assert line.allocation_profile_key == "late_cash"
    assert amounts_by_month["2026-01"] < amounts_by_month["2026-02"]

    db_session.commit()


def test_recalculate_uses_persisted_sequence_template_defaults(db_session) -> None:
    actor_id = db_session.scalar(select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    discipline = db_session.scalar(select(Discipline).where(Discipline.code == "offline"))

    assert actor_id is not None
    assert discipline is not None

    db_session.add(
        ReferenceDataValue(
            category="forecast_sequence_template",
            key="late_finish_custom",
            label="Late Finish Custom",
            sort_order=5,
            is_active=True,
            metadata_json={
                "projectFormatKeys": ["late_finish_custom"],
                "stages": [
                    {
                        "disciplineCode": "offline",
                        "stageKey": "editorial",
                        "startPct": 0.55,
                        "endPct": 1.0,
                        "overlapPct": 0.0,
                    }
                ],
            },
        )
    )

    project = Project(
        name="Sequence Template Forecast Project",
        status=ProjectStatus.bid,
        quote_currency_code="GBP",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
    )
    db_session.add(project)
    db_session.flush()

    db_session.add(
        ProjectMetadata(
            project_id=project.id,
            project_format_key="late_finish_custom",
            budget_target=10000,
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

    quote = Quote(project_id=project.id, quote_number="Q-SEQUENCE", title="Sequence Quote")
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
        ForecastVersionCreateRequest(title="Sequence Template Draft"),
        actor_id=actor_id,
    )

    assert len(version.lines) == 1
    line = version.lines[0]
    amounts_by_month = {allocation.month: allocation.amount for allocation in line.allocations}

    assert line.sequencing_template_key == "late_finish_custom"
    assert amounts_by_month["2026-01"] < amounts_by_month["2026-02"]

    db_session.commit()


def test_forecast_recalculation_blends_actuals_and_remaining_work(
    db_session,
) -> None:
    actor_id = db_session.scalar(select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"]))
    discipline = db_session.scalar(select(Discipline).where(Discipline.code == "offline"))

    assert actor_id is not None
    assert discipline is not None

    project = Project(
        name="Actuals Blend Forecast Project",
        status=ProjectStatus.active,
        quote_currency_code="GBP",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 28),
    )
    db_session.add(project)
    db_session.flush()

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

    quote = Quote(project_id=project.id, quote_number="Q-ACTUALS", title="Actuals Blend Quote")
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

    quote_line = QuoteLineItem(
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
    db_session.add(quote_line)
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
            actual_business_key="actuals-blend-jan",
            supersedes_mapped_actual_id=None,
            is_current=True,
            change_type=MappedActualChangeType.new,
            mapped_by_id=actor_id,
            mapped_at=quote_version.created_at,
        )
    )
    db_session.flush()

    version = forecast_service.create_or_clone_version(
        db_session,
        project.id,
        ForecastVersionCreateRequest(title="Forecast With Actuals"),
        actor_id=actor_id,
    )

    assert len(version.lines) == 1
    line = version.lines[0]
    assert line.actuals_to_date_amount == 2500
    assert line.remaining_amount == 7500
    assert [allocation.month for allocation in line.allocations] == ["2026-01", "2026-02"]
    january = next(allocation for allocation in line.allocations if allocation.month == "2026-01")
    february = next(allocation for allocation in line.allocations if allocation.month == "2026-02")
    assert january.amount == 2500
    assert january.actual_amount == 2500
    assert january.allocation_source == "actual"
    assert january.low_amount == 2500
    assert january.high_amount == 2500
    assert february.amount == 7500
    assert february.allocation_source == "forecast"
    assert february.low_amount is not None
    assert february.high_amount is not None
    assert february.high_amount >= february.amount
    assert line.forecast_method_key in {"curve", "hybrid", "linear"}
    assert version.project_monthly_rollups[0].actual_amount == 2500


def test_line_editor_and_phasing_workspace_share_manual_override_storage_and_rollups(
    db_session,
) -> None:
    actor_id = _admin_actor_id(db_session)
    line_project_id, line_version_id = _create_revenue_phasing_project(
        db_session,
        name="Line Editor Alignment",
        line_amounts=[("offline", 9000)],
    )
    phasing_project_id, _phasing_version_id = _create_revenue_phasing_project(
        db_session,
        name="Phasing Alignment",
        line_amounts=[("offline", 9000)],
    )

    line_detail = forecast_service.get_version(db_session, line_version_id)
    line_row = line_detail.lines[0]
    line_updated = forecast_service.replace_line_allocations(
        db_session,
        line_row.id,
        ForecastLineAllocationsReplaceRequest(
            expected_updated_at=line_detail.updated_at,
            allocation_method="manual",
            allocations=[
                ForecastLineMonthAllocationWrite(month="2026-06", amount=4000),
                ForecastLineMonthAllocationWrite(month="2026-07", amount=3000),
                ForecastLineMonthAllocationWrite(month="2026-08", amount=2000),
            ],
            reason="Aligned manual phasing.",
        ),
        actor_id=actor_id,
    )

    phasing_detail = forecast_service.get_project_forecast(db_session, phasing_project_id)
    assert phasing_detail.current_version is not None
    forecast_service.update_phasing_row(
        db_session,
        phasing_project_id,
        ForecastPhasingRowUpdateRequest(
            forecast_version_id=phasing_detail.current_version.id,
            expected_updated_at=phasing_detail.current_version.updated_at,
            row_mode="project",
            replace_existing_overrides=True,
            reason="Aligned manual phasing.",
            cells=[
                ForecastPhasingCellWrite(month="2026-06", amount=4000, is_locked=True),
                ForecastPhasingCellWrite(month="2026-07", amount=3000, is_locked=True),
                ForecastPhasingCellWrite(month="2026-08", amount=2000, is_locked=True),
            ],
        ),
        actor_id=actor_id,
    )

    phasing_after = forecast_service.get_project_forecast(db_session, phasing_project_id)
    assert phasing_after.current_version is not None

    line_allocations = [
        (
            allocation.month,
            allocation.amount,
            allocation.is_manual_override,
            allocation.is_locked,
            allocation.manual_note,
        )
        for allocation in line_updated.lines[0].allocations
    ]
    phasing_allocations = [
        (
            allocation.month,
            allocation.amount,
            allocation.is_manual_override,
            allocation.is_locked,
            allocation.manual_note,
        )
        for allocation in phasing_after.current_version.lines[0].allocations
    ]

    assert line_project_id != phasing_project_id
    assert line_allocations == phasing_allocations
    assert line_updated.project_monthly_rollups == phasing_after.current_version.project_monthly_rollups
    assert line_updated.discipline_monthly_rollups == phasing_after.current_version.discipline_monthly_rollups
    assert all(allocation[2] is True for allocation in line_allocations)
    assert all(allocation[3] is True for allocation in line_allocations)


def test_revenue_phasing_workspace_supports_project_and_discipline_views(
    client,
    db_session,
) -> None:
    project_id, _version_id = _create_revenue_phasing_project(
        db_session,
        name="Revenue Phasing Workspace Views",
        line_amounts=[("offline", 6000), ("online", 3000)],
    )
    headers = _admin_headers(client)

    project_response = client.get(
        (
            "/api/v1/forecasts/phasing-workspace"
            f"?projectId={project_id}&fromMonth=2026-06&toMonth=2026-08&rowMode=project"
        ),
        headers=headers,
    )
    assert project_response.status_code == 200, project_response.text
    project_workspace = project_response.json()

    assert project_workspace["months"] == ["2026-06", "2026-07", "2026-08"]
    assert len(project_workspace["rows"]) == 1

    project_row = project_workspace["rows"][0]
    assert project_row["projectId"] == project_id
    assert project_row["executionStartDate"] == "2026-06-01"
    assert project_row["executionEndDate"] == "2026-08-31"
    assert project_row["basePhasingProfile"] == "flat_equal"
    assert project_row["totalAmount"] == 9000.0
    assert _row_amounts_by_month(project_row) == {
        "2026-06": 3000.0,
        "2026-07": 3000.0,
        "2026-08": 3000.0,
    }

    discipline_response = client.get(
        (
            "/api/v1/forecasts/phasing-workspace"
            f"?projectId={project_id}&fromMonth=2026-06&toMonth=2026-08&rowMode=discipline"
        ),
        headers=headers,
    )
    assert discipline_response.status_code == 200, discipline_response.text
    discipline_workspace = discipline_response.json()

    assert len(discipline_workspace["rows"]) == 2
    assert sum(row["totalAmount"] for row in discipline_workspace["rows"]) == pytest.approx(9000.0)

    offline_row = next(
        row for row in discipline_workspace["rows"] if row["disciplineName"] == "Offline"
    )
    online_row = next(
        row for row in discipline_workspace["rows"] if row["disciplineName"] == "Online"
    )
    assert _row_amounts_by_month(offline_row) == {
        "2026-06": 2000.0,
        "2026-07": 2000.0,
        "2026-08": 2000.0,
    }
    assert _row_amounts_by_month(online_row) == {
        "2026-06": 1000.0,
        "2026-07": 1000.0,
        "2026-08": 1000.0,
    }


def test_revenue_phasing_preview_respects_locked_months(
    client,
    db_session,
) -> None:
    project_id, _version_id = _create_revenue_phasing_project(
        db_session,
        name="Revenue Phasing Preview",
        line_amounts=[("offline", 9000)],
    )

    response = client.post(
        "/api/v1/forecasts/phasing-workspace/preview",
        headers=_admin_headers(client),
        json={
            "projectId": project_id,
            "rowMode": "project",
            "fromMonth": "2026-06",
            "toMonth": "2026-08",
            "action": "cadence_profile",
            "cadenceProfileType": "back_loaded",
            "lockedMonths": ["2026-06"],
        },
    )

    assert response.status_code == 200, response.text
    preview = response.json()

    assert preview["projectId"] == project_id
    assert [cell["month"] for cell in preview["cells"]] == ["2026-07", "2026-08"]
    assert sum(cell["amount"] for cell in preview["cells"]) == pytest.approx(6000.0)
    assert preview["cells"][1]["amount"] > preview["cells"][0]["amount"]


def test_revenue_phasing_update_rebalances_remaining_months_and_records_changes(
    client,
    db_session,
) -> None:
    project_id, _version_id = _create_revenue_phasing_project(
        db_session,
        name="Revenue Phasing Project Save",
        line_amounts=[("offline", 9000)],
    )
    headers = _admin_headers(client)
    workspace_response = client.get(
        (
            "/api/v1/forecasts/phasing-workspace"
            f"?projectId={project_id}&fromMonth=2026-06&toMonth=2026-08&rowMode=project"
        ),
        headers=headers,
    )
    assert workspace_response.status_code == 200, workspace_response.text
    row = workspace_response.json()["rows"][0]

    save_response = client.put(
        f"/api/v1/forecasts/projects/{project_id}/phasing",
        headers=headers,
        json={
            "forecastVersionId": row["forecastVersionId"],
            "expectedUpdatedAt": row["forecastVersionUpdatedAt"],
            "rowMode": "project",
            "reason": "Client moved more revenue to the end of the job.",
            "cells": [
                {"month": "2026-06", "amount": 1000, "isLocked": True},
                {"month": "2026-07", "amount": 2000, "isLocked": False},
            ],
        },
    )

    assert save_response.status_code == 200, save_response.text
    workspace = save_response.json()
    updated_row = workspace["rows"][0]

    assert updated_row["totalAmount"] == pytest.approx(9000.0)
    assert _row_amounts_by_month(updated_row) == {
        "2026-06": 1000.0,
        "2026-07": 2000.0,
        "2026-08": 6000.0,
    }
    assert _row_cell(updated_row, "2026-06")["isManualOverride"] is True
    assert _row_cell(updated_row, "2026-06")["isLocked"] is True
    assert _row_cell(updated_row, "2026-07")["isManualOverride"] is True
    assert _row_cell(updated_row, "2026-08")["isManualOverride"] is False

    changes = list(
        db_session.scalars(
            select(ForecastPhasingChange)
            .where(ForecastPhasingChange.project_id == project_id)
            .order_by(ForecastPhasingChange.month)
        )
    )
    assert [change.month.isoformat() for change in changes] == [
        "2026-06-01",
        "2026-07-01",
        "2026-08-01",
    ]
    assert changes[0].after_amount == 1000.0
    assert changes[0].after_locked is True
    assert changes[1].after_amount == 2000.0
    assert changes[2].after_amount == 6000.0

    manual_allocations = list(
        db_session.scalars(
            select(MonthlyForecastAllocation)
            .join(MonthlyForecastAllocation.forecast_line)
            .where(ForecastLine.forecast_version_id == updated_row["forecastVersionId"])
            .where(MonthlyForecastAllocation.is_manual_override.is_(True))
            .order_by(MonthlyForecastAllocation.month)
        )
    )
    assert [allocation.month.isoformat() for allocation in manual_allocations] == [
        "2026-06-01",
        "2026-07-01",
    ]


def test_revenue_phasing_update_can_merge_into_existing_overrides(
    client,
    db_session,
) -> None:
    project_id, _version_id = _create_revenue_phasing_project(
        db_session,
        name="Revenue Phasing Merge Save",
        line_amounts=[("offline", 9000)],
    )
    headers = _admin_headers(client)

    initial_workspace_response = client.get(
        (
            "/api/v1/forecasts/phasing-workspace"
            f"?projectId={project_id}&fromMonth=2026-06&toMonth=2026-08&rowMode=project"
        ),
        headers=headers,
    )
    assert initial_workspace_response.status_code == 200, initial_workspace_response.text
    initial_row = initial_workspace_response.json()["rows"][0]

    first_save_response = client.put(
        f"/api/v1/forecasts/projects/{project_id}/phasing",
        headers=headers,
        json={
            "forecastVersionId": initial_row["forecastVersionId"],
            "expectedUpdatedAt": initial_row["forecastVersionUpdatedAt"],
            "rowMode": "project",
            "reason": "Initial locked June phasing.",
            "cells": [
                {"month": "2026-06", "amount": 1000, "isLocked": True},
            ],
        },
    )
    assert first_save_response.status_code == 200, first_save_response.text
    first_row = first_save_response.json()["rows"][0]
    assert _row_amounts_by_month(first_row) == {
        "2026-06": 1000.0,
        "2026-07": 4000.0,
        "2026-08": 4000.0,
    }

    merge_save_response = client.put(
        f"/api/v1/forecasts/projects/{project_id}/phasing",
        headers=headers,
        json={
            "forecastVersionId": first_row["forecastVersionId"],
            "expectedUpdatedAt": first_row["forecastVersionUpdatedAt"],
            "rowMode": "project",
            "replaceExistingOverrides": False,
            "reason": "Merge a July adjustment without clearing June.",
            "cells": [
                {"month": "2026-07", "amount": 2000, "isLocked": False},
            ],
        },
    )
    assert merge_save_response.status_code == 200, merge_save_response.text
    merged_row = merge_save_response.json()["rows"][0]

    assert _row_amounts_by_month(merged_row) == {
        "2026-06": 1000.0,
        "2026-07": 2000.0,
        "2026-08": 6000.0,
    }
    assert _row_cell(merged_row, "2026-06")["isLocked"] is True
    assert _row_cell(merged_row, "2026-06")["isManualOverride"] is True
    assert _row_cell(merged_row, "2026-07")["isManualOverride"] is True


def test_revenue_phasing_draft_persists_and_is_returned_in_workspace(
    client,
    db_session,
) -> None:
    project_id, _version_id = _create_revenue_phasing_project(
        db_session,
        name="Revenue Phasing Shared Draft",
        line_amounts=[("offline", 9000)],
    )
    headers = _admin_headers(client)

    workspace_response = client.get(
        (
            "/api/v1/forecasts/phasing-workspace"
            f"?projectId={project_id}&fromMonth=2026-06&toMonth=2026-08&rowMode=project"
        ),
        headers=headers,
    )
    assert workspace_response.status_code == 200, workspace_response.text
    row = workspace_response.json()["rows"][0]

    draft_response = client.put(
        f"/api/v1/forecasts/projects/{project_id}/phasing-draft",
        headers=headers,
        json={
            "rowMode": "project",
            "saveMode": "merge",
            "currentState": {
                "forecastVersionId": row["forecastVersionId"],
                "expectedUpdatedAt": row["forecastVersionUpdatedAt"],
                "reason": "Shared working phasing draft.",
                "cells": [
                    {"month": "2026-06", "amount": 1000, "isLocked": True},
                    {"month": "2026-07", "amount": 2000, "isLocked": False},
                ],
            },
            "pastStates": [
                {
                    "forecastVersionId": row["forecastVersionId"],
                    "expectedUpdatedAt": row["forecastVersionUpdatedAt"],
                    "reason": "Baseline before shared draft.",
                    "cells": [],
                }
            ],
            "futureStates": [],
        },
    )
    assert draft_response.status_code == 200, draft_response.text
    draft = draft_response.json()
    assert draft["saveMode"] == "merge"
    assert draft["updatedByEmail"] == os.environ["DEV_ADMIN_EMAIL"]
    assert [cell["month"] for cell in draft["currentState"]["cells"]] == ["2026-06", "2026-07"]
    assert len(draft["pastStates"]) == 1

    refreshed_workspace_response = client.get(
        (
            "/api/v1/forecasts/phasing-workspace"
            f"?projectId={project_id}&fromMonth=2026-06&toMonth=2026-08&rowMode=project"
        ),
        headers=headers,
    )
    assert refreshed_workspace_response.status_code == 200, refreshed_workspace_response.text
    refreshed_row = refreshed_workspace_response.json()["rows"][0]
    active_draft = refreshed_row["activeDraft"]
    assert active_draft is not None
    assert active_draft["saveMode"] == "merge"
    assert active_draft["currentState"]["reason"] == "Shared working phasing draft."
    assert [cell["month"] for cell in active_draft["currentState"]["cells"]] == [
        "2026-06",
        "2026-07",
    ]
    assert len(active_draft["pastStates"]) == 1

    persisted_draft = db_session.scalar(
        select(ForecastPhasingDraft).where(ForecastPhasingDraft.project_id == project_id)
    )
    assert persisted_draft is not None
    assert persisted_draft.row_mode == "project"
    assert persisted_draft.save_mode == "merge"


def test_revenue_phasing_draft_can_be_discarded(
    client,
    db_session,
) -> None:
    project_id, _version_id = _create_revenue_phasing_project(
        db_session,
        name="Revenue Phasing Draft Discard",
        line_amounts=[("offline", 9000)],
    )
    headers = _admin_headers(client)

    workspace_response = client.get(
        (
            "/api/v1/forecasts/phasing-workspace"
            f"?projectId={project_id}&fromMonth=2026-06&toMonth=2026-08&rowMode=project"
        ),
        headers=headers,
    )
    assert workspace_response.status_code == 200, workspace_response.text
    row = workspace_response.json()["rows"][0]

    draft_response = client.put(
        f"/api/v1/forecasts/projects/{project_id}/phasing-draft",
        headers=headers,
        json={
            "rowMode": "project",
            "currentState": {
                "forecastVersionId": row["forecastVersionId"],
                "expectedUpdatedAt": row["forecastVersionUpdatedAt"],
                "reason": "Temporary draft to discard.",
                "cells": [
                    {"month": "2026-06", "amount": 1500, "isLocked": True},
                ],
            },
            "pastStates": [],
            "futureStates": [],
        },
    )
    assert draft_response.status_code == 200, draft_response.text

    discarded_response = client.delete(
        (
            f"/api/v1/forecasts/projects/{project_id}/phasing-draft"
            f"?forecastVersionId={row['forecastVersionId']}&rowMode=project"
        ),
        headers=headers,
    )
    assert discarded_response.status_code == 200, discarded_response.text
    discarded_row = discarded_response.json()["rows"][0]
    assert discarded_row["activeDraft"] is None

    persisted_drafts = list(
        db_session.scalars(
            select(ForecastPhasingDraft).where(ForecastPhasingDraft.project_id == project_id)
        )
    )
    assert persisted_drafts == []


def test_revenue_phasing_update_can_target_single_discipline_row(
    client,
    db_session,
) -> None:
    project_id, _version_id = _create_revenue_phasing_project(
        db_session,
        name="Revenue Phasing Discipline Save",
        line_amounts=[("offline", 6000), ("online", 3000)],
    )
    headers = _admin_headers(client)
    workspace_response = client.get(
        (
            "/api/v1/forecasts/phasing-workspace"
            f"?projectId={project_id}&fromMonth=2026-06&toMonth=2026-08&rowMode=discipline"
        ),
        headers=headers,
    )
    assert workspace_response.status_code == 200, workspace_response.text
    offline_row = next(
        row
        for row in workspace_response.json()["rows"]
        if row["disciplineName"] == "Offline"
    )

    save_response = client.put(
        f"/api/v1/forecasts/projects/{project_id}/phasing",
        headers=headers,
        json={
            "forecastVersionId": offline_row["forecastVersionId"],
            "expectedUpdatedAt": offline_row["forecastVersionUpdatedAt"],
            "rowMode": "discipline",
            "disciplineId": offline_row["disciplineId"],
            "reason": "Offline workload shifted into the final month.",
            "cells": [
                {"month": "2026-06", "amount": 1000, "isLocked": True},
                {"month": "2026-07", "amount": 1000, "isLocked": False},
            ],
        },
    )

    assert save_response.status_code == 200, save_response.text
    updated_workspace = save_response.json()
    assert len(updated_workspace["rows"]) == 1

    updated_offline_row = updated_workspace["rows"][0]
    assert updated_offline_row["disciplineName"] == "Offline"
    assert _row_amounts_by_month(updated_offline_row) == {
        "2026-06": 1000.0,
        "2026-07": 1000.0,
        "2026-08": 4000.0,
    }

    project_workspace_response = client.get(
        (
            "/api/v1/forecasts/phasing-workspace"
            f"?projectId={project_id}&fromMonth=2026-06&toMonth=2026-08&rowMode=project"
        ),
        headers=headers,
    )
    assert project_workspace_response.status_code == 200, project_workspace_response.text
    project_row = project_workspace_response.json()["rows"][0]
    assert _row_amounts_by_month(project_row) == {
        "2026-06": 2000.0,
        "2026-07": 2000.0,
        "2026-08": 5000.0,
    }
