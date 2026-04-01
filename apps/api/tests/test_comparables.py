from __future__ import annotations

import os
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    ComparableProjectLink,
    Discipline,
    Project,
    ProjectBenchmarkDisciplineSummary,
    ProjectBenchmarkSummary,
    ProjectDiscipline,
    ProjectMetadata,
    ProjectParty,
    Quote,
    QuoteVersion,
)
from app.models.enums import (
    BenchmarkActualsStatus,
    ComparableProjectLinkDisposition,
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


def _discipline_id(session: Session, code: str) -> str:
    discipline_id = session.scalar(select(Discipline.id).where(Discipline.code == code))
    assert discipline_id is not None
    return discipline_id


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
) -> None:
    line_amounts = line_amounts or [
        ("offline", quote_total * 0.4),
        ("online", quote_total * 0.35),
        ("grade", quote_total * 0.25),
    ]
    client_company_id = _company_id(session, client_normalized_name)
    streamer_company_id = _company_id(session, "netstream")
    discipline_ids = {code: _discipline_id(session, code) for code, _ in line_amounts}

    project = Project(
        id=project_id,
        code=project_id[-12:].upper(),
        name=name,
        status=status,
        quote_currency_code=currency_code,
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


def test_project_recommendations_use_persisted_project_data(
    client: TestClient,
    db_session: Session,
) -> None:
    _add_project(
        db_session,
        project_id="project_db_target",
        name="Database Target Project",
        status=ProjectStatus.bid,
        client_normalized_name="north star pictures",
        quote_total=100000,
        duration_weeks=8,
        currency_code="EUR",
    )
    _add_project(
        db_session,
        project_id="project_db_candidate_1",
        name="Database Candidate One",
        status=ProjectStatus.complete,
        client_normalized_name="north star pictures",
        quote_total=98000,
        duration_weeks=8,
        currency_code="EUR",
        benchmark_actual=105000,
    )
    _add_project(
        db_session,
        project_id="project_db_candidate_2",
        name="Database Candidate Two",
        status=ProjectStatus.complete,
        client_normalized_name="bbc studios",
        quote_total=110000,
        duration_weeks=9,
        currency_code="EUR",
        benchmark_actual=119000,
    )
    _add_project(
        db_session,
        project_id="project_db_candidate_3",
        name="Database Candidate Three",
        status=ProjectStatus.complete,
        client_normalized_name="silverline media",
        quote_total=122000,
        duration_weeks=7,
        currency_code="EUR",
        benchmark_actual=131000,
    )
    db_session.commit()

    headers = _admin_headers(client)
    comparables_response = client.get(
        "/api/v1/projects/project_db_target/comparables",
        headers=headers,
    )
    recommendations_response = client.get(
        "/api/v1/projects/project_db_target/recommendations",
        headers=headers,
    )
    discipline_recommendations_response = client.get(
        "/api/v1/projects/project_db_target/recommendations?disciplineId=online",
        headers=headers,
    )

    assert comparables_response.status_code == 200, comparables_response.text
    assert recommendations_response.status_code == 200, recommendations_response.text
    assert (
        discipline_recommendations_response.status_code == 200
    ), discipline_recommendations_response.text

    comparables_body = comparables_response.json()
    recommendations_body = recommendations_response.json()
    discipline_recommendations_body = discipline_recommendations_response.json()

    assert comparables_body["target"]["projectId"] == "project_db_target"
    assert comparables_body["target"]["quoteVersionId"] is not None
    assert {
        "project_db_candidate_1",
        "project_db_candidate_2",
        "project_db_candidate_3",
    }.issubset({item["projectId"] for item in comparables_body["items"]})
    assert recommendations_body["target"]["quoteCurrencyCode"] == "EUR"
    assert recommendations_body["comparablesUsed"] == [
        "project_db_candidate_1",
        "project_db_candidate_2",
        "project_db_candidate_3",
    ]
    assert all(item["matchedFactors"] for item in comparables_body["items"])

    assert recommendations_body["overallQuoteRange"]["low"] == 98000
    assert recommendations_body["overallQuoteRange"]["high"] == 122000
    assert recommendations_body["overallQuoteRange"]["sampleSize"] == 3
    assert recommendations_body["overallActualInformedRange"]["median"] > recommendations_body[
        "overallQuoteRange"
    ]["median"]
    assert discipline_recommendations_body["comparablesUsed"] == [
        "project_db_candidate_1",
        "project_db_candidate_2",
        "project_db_candidate_3",
    ]
    assert len(discipline_recommendations_body["disciplineRanges"]) == 1
    assert discipline_recommendations_body["disciplineRanges"][0]["disciplineId"] == "online"
    assert discipline_recommendations_body["disciplineRanges"][0]["sampleSize"] == 3
    assert (
        discipline_recommendations_body["disciplineRanges"][0]["observedVarianceMedianPct"]
        is not None
    )


def test_project_comparable_selection_persists_manual_overrides(
    client: TestClient,
    db_session: Session,
) -> None:
    _add_project(
        db_session,
        project_id="project_db_selection_target",
        name="Selection Target Project",
        status=ProjectStatus.bid,
        client_normalized_name="north star pictures",
        quote_total=100000,
        duration_weeks=8,
    )
    _add_project(
        db_session,
        project_id="project_db_selection_keep",
        name="Selection Candidate Keep",
        status=ProjectStatus.complete,
        client_normalized_name="north star pictures",
        quote_total=101000,
        duration_weeks=8,
        benchmark_actual=108000,
    )
    _add_project(
        db_session,
        project_id="project_db_selection_drop",
        name="Selection Candidate Drop",
        status=ProjectStatus.complete,
        client_normalized_name="aurora creative",
        quote_total=117000,
        duration_weeks=8,
        benchmark_actual=126000,
    )
    db_session.commit()

    headers = _admin_headers(client)
    response = client.put(
        "/api/v1/projects/project_db_selection_target/comparable-selection",
        headers=headers,
        json={
            "pinnedProjectIds": ["project_db_selection_keep"],
            "excludedProjectIds": ["project_db_selection_drop"],
            "note": "Manual comparable review",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pinnedProjectIds"] == ["project_db_selection_keep"]
    assert body["excludedProjectIds"] == ["project_db_selection_drop"]
    assert body["note"] == "Manual comparable review"

    db_session.expire_all()
    persisted_links = list(
        db_session.scalars(
            select(ComparableProjectLink).where(
                ComparableProjectLink.project_id == "project_db_selection_target"
            )
        )
    )
    assert {(link.comparable_project_id, link.disposition) for link in persisted_links} == {
        ("project_db_selection_keep", ComparableProjectLinkDisposition.pinned),
        ("project_db_selection_drop", ComparableProjectLinkDisposition.excluded),
    }
    assert all(link.reasons_json for link in persisted_links)

    comparables_response = client.get(
        "/api/v1/projects/project_db_selection_target/comparables",
        headers=headers,
    )
    assert comparables_response.status_code == 200, comparables_response.text
    items = {
        item["projectId"]: item["selectionState"]
        for item in comparables_response.json()["items"]
    }
    assert items["project_db_selection_keep"] == "pinned"
    assert items["project_db_selection_drop"] == "excluded"
