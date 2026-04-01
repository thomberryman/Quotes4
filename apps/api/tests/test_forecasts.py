from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import select

from app.models import (
    Discipline,
    MappedActual,
    Project,
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
)
from app.modules.forecasts.schemas import (
    ForecastLineAllocationsReplaceRequest,
    ForecastLineMonthAllocationWrite,
    ForecastVersionCreateRequest,
)
from app.modules.forecasts.service import forecast_service


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
