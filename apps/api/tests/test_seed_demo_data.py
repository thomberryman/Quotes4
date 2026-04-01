from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_engine, get_session_factory, reset_db_state
from app.models import (
    Base,
    CetaImport,
    Company,
    CompanyClassification,
    Contact,
    ForecastLine,
    ForecastVersion,
    MappedActual,
    Project,
    ProjectBenchmarkSummary,
    ProjectExternalReference,
    Quote,
    QuoteVersion,
    ReferenceTermAlias,
    User,
)
from app.models.enums import (
    BenchmarkActualsStatus,
    CetaImportStatus,
    CompanyClassificationType,
    ForecastAllocationMethod,
    ForecastVersionStatus,
    QuoteVersionStatus,
)
from app.modules.actuals_imports.service import actuals_import_service
from app.seed import run_seed


def test_demo_seed_populates_counterparties_contacts_projects_and_quotes(db_session) -> None:
    client_names = {
        name
        for name in db_session.scalars(
            select(Company.normalized_name)
            .join(CompanyClassification, CompanyClassification.company_id == Company.id)
            .where(CompanyClassification.classification == CompanyClassificationType.client)
        )
    }

    assert {
        "bbc studios",
        "north star pictures",
        "silverline media",
        "aurora creative",
        "global media",
        "studio east",
    }.issubset(client_names)
    assert len(list(db_session.scalars(select(Contact)))) >= 15

    project_ids = {project.id for project in db_session.scalars(select(Project)).all()}
    assert {
        "project_red_room",
        "project_black_glass",
        "project_north_passage",
        "project_silver_tide",
        "project_blue_echo",
        "project_global_cut",
        "project_amber_lane",
        "project_ember_fade",
    }.issubset(project_ids)

    red_room_quote = db_session.scalar(
        select(Quote).where(Quote.project_id == "project_red_room")
    )
    assert red_room_quote is not None
    red_room_versions = list(
        db_session.scalars(
            select(QuoteVersion)
            .where(QuoteVersion.quote_id == red_room_quote.id)
            .order_by(QuoteVersion.version_number)
        )
    )
    assert [version.version_number for version in red_room_versions] == [1, 2]
    assert red_room_versions[-1].status == QuoteVersionStatus.issued
    assert red_room_quote.current_version_id == red_room_versions[-1].id

    black_glass_quote = db_session.scalar(
        select(Quote).where(Quote.project_id == "project_black_glass")
    )
    assert black_glass_quote is not None
    black_glass_current = db_session.get(QuoteVersion, black_glass_quote.current_version_id)
    assert black_glass_current is not None
    assert black_glass_current.status == QuoteVersionStatus.accepted


def test_demo_seed_populates_forecasts_actuals_imports_and_variance_examples(
    db_session,
) -> None:
    forecast_statuses = {
        version.status for version in db_session.scalars(select(ForecastVersion)).all()
    }
    assert ForecastVersionStatus.draft in forecast_statuses
    assert ForecastVersionStatus.submitted in forecast_statuses
    assert ForecastVersionStatus.locked in forecast_statuses

    manual_line_count = len(
        list(
            db_session.scalars(
                select(ForecastLine).where(
                    ForecastLine.allocation_method == ForecastAllocationMethod.manual
                )
            )
        )
    )
    assert manual_line_count >= 2

    batch_statuses = {batch.status for batch in db_session.scalars(select(CetaImport)).all()}
    assert CetaImportStatus.uploaded in batch_statuses
    assert CetaImportStatus.in_review in batch_statuses
    assert CetaImportStatus.approved in batch_statuses

    benchmark_summaries = list(db_session.scalars(select(ProjectBenchmarkSummary)))
    assert any(
        summary.actuals_status == BenchmarkActualsStatus.complete
        for summary in benchmark_summaries
    )
    assert any(
        summary.actuals_status == BenchmarkActualsStatus.partial
        for summary in benchmark_summaries
    )
    assert any(
        summary.quote_to_actual_variance_amount is not None
        and float(summary.quote_to_actual_variance_amount) > 0
        for summary in benchmark_summaries
    )

    mapped_actual_count = len(list(db_session.scalars(select(MappedActual))))
    assert mapped_actual_count >= 6
    assert db_session.scalar(select(ProjectExternalReference.id)) is not None
    assert db_session.scalar(select(ReferenceTermAlias.id)) is not None

    red_room_batch = db_session.scalar(
        select(CetaImport).where(CetaImport.project_id == "project_red_room")
    )
    assert red_room_batch is not None
    red_room_rows = actuals_import_service.list_rows(db_session, red_room_batch.id).items
    red_room_queues = {row.review_queue for row in red_room_rows}
    assert {"ready", "ambiguous", "blocking"}.issubset(red_room_queues)


def test_baseline_seed_skips_demo_records(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'quotes4_baseline_seed.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    reset_db_state()

    try:
        Base.metadata.create_all(bind=get_engine())
        run_seed(seed_mode="baseline")

        with get_session_factory()() as session:
            assert session.scalar(select(Project.id)) is None
            assert session.scalar(select(ForecastVersion.id)) is None
            assert session.scalar(select(CetaImport.id)) is None
            assert session.scalar(select(ProjectExternalReference.id)) is None
            assert session.scalar(select(User.id)) is not None
            assert session.scalar(select(ReferenceTermAlias.id)) is not None
    finally:
        get_settings.cache_clear()
        reset_db_state()
