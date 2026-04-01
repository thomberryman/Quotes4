from __future__ import annotations

import os
from datetime import date

from sqlalchemy import select

from app.models import (
    Discipline,
    Project,
    ProjectScheduleRange,
    Quote,
    QuoteLineItem,
    QuoteSection,
    QuoteVersion,
    User,
)
from app.models.enums import ProjectStatus, QuoteLineItemType, QuoteVersionStatus
from app.modules.forecasts.schemas import (
    ForecastLineAllocationsReplaceRequest,
    ForecastLineMonthAllocationWrite,
    ForecastVersionCreateRequest,
)
from app.modules.forecasts.service import forecast_service


def test_recalculate_preserves_partial_manual_override_without_collapsing_split_lines(
    db_session,
) -> None:
    actor_id = db_session.scalar(
        select(User.id).where(User.email == os.environ["DEV_ADMIN_EMAIL"])
    )
    discipline = db_session.scalar(
        select(Discipline).where(Discipline.code == "offline")
    )

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

    manual_line = next(
        line for line in recalculated.lines if line.allocation_method == "manual"
    )
    schedule_line = next(
        line for line in recalculated.lines if line.allocation_method == "schedule"
    )

    assert manual_line.label.endswith("Prep")
    assert manual_line.total_amount == 4000
    assert len(manual_line.allocations) == 1
    assert manual_line.allocations[0].month == "2026-01"
    assert manual_line.allocations[0].amount == 4000
    assert manual_line.allocations[0].weighted_amount == 4000
    assert schedule_line.label.endswith("Finish")
    assert schedule_line.total_amount == 6000

    db_session.commit()
