from __future__ import annotations

import os
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import (
    ActualMappingRule,
    CetaImport,
    Forecast,
    ForecastVersion,
    MappedActual,
    Project,
    ProjectExternalReference,
    Quote,
    QuoteVersion,
    ReferenceTermAlias,
    UploadedFile,
)
from app.models.enums import (
    CetaImportStatus,
    CetaRowFinancialType,
    ForecastVersionStatus,
    MappedActualChangeType,
    ProjectStatus,
    QuoteVersionStatus,
    UploadedFileCategory,
    UploadedFileStatus,
)

TEST_CHECKSUM = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _assert_status(response, expected_status: int) -> dict[str, object]:
    assert response.status_code == expected_status, response.text
    return response.json()


def _login_admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={
            "email": os.environ["DEV_ADMIN_EMAIL"],
            "password": os.environ["DEV_ADMIN_PASSWORD"],
        },
    )
    payload = _assert_status(response, 200)
    return {"Authorization": f"Bearer {payload['accessToken']}"}


def _worker_headers() -> dict[str, str]:
    return {"X-Worker-Token": os.environ["WORKER_CALLBACK_TOKEN"]}


def _create_project_financial_baseline(db_session):
    project = Project(
        code="BGS1-TRAILER",
        name="Black Glass S1 Launch Campaign",
        status=ProjectStatus.active,
        quote_currency_code="GBP",
    )
    db_session.add(project)
    db_session.flush()

    quote = Quote(project_id=project.id, title="Black Glass Main Quote")
    db_session.add(quote)
    db_session.flush()
    quote_version = QuoteVersion(
        quote_id=quote.id,
        version_number=1,
        status=QuoteVersionStatus.issued,
        title="Issued quote",
        currency_code="GBP",
        subtotal_amount=10000,
        tax_amount=0,
        total_amount=10000,
    )
    db_session.add(quote_version)
    db_session.flush()
    quote.current_version_id = quote_version.id

    forecast = Forecast(project_id=project.id)
    db_session.add(forecast)
    db_session.flush()
    forecast_version = ForecastVersion(
        forecast_id=forecast.id,
        version_number=1,
        status=ForecastVersionStatus.locked,
        title="Locked forecast",
        total_amount=9000,
    )
    db_session.add(forecast_version)
    db_session.flush()
    forecast.current_version_id = forecast_version.id

    return project


def _create_uploaded_file(
    db_session,
    *,
    storage_key: str = "actuals/batch-1/generic-ledger.csv",
) -> UploadedFile:
    uploaded_file = UploadedFile(
        storage_key=storage_key,
        original_filename="april-export.csv",
        mime_type="text/csv",
        size_bytes=4096,
        checksum_sha256=TEST_CHECKSUM,
        file_category=UploadedFileCategory.ceta_export,
        status=UploadedFileStatus.uploaded,
        created_at=datetime.now(UTC),
        uploaded_at=datetime.now(UTC),
    )
    db_session.add(uploaded_file)
    db_session.commit()
    return uploaded_file


def _create_current_actual(
    db_session,
    *,
    project_id: str,
    business_key: str,
    amount: float,
    description: str = "Existing actual",
    work_date: date = date(2026, 4, 8),
) -> MappedActual:
    actual = MappedActual(
        project_id=project_id,
        discipline_id=None,
        source_ceta_import_id=None,
        source_ceta_import_row_id=None,
        mapping_decision_id=None,
        work_date=work_date,
        posting_date=work_date,
        description=description,
        vendor_name="Halo Post",
        amount=amount,
        currency_code="GBP",
        financial_type=CetaRowFinancialType.cost,
        cost_category_key="editorial_labor",
        revenue_category_key=None,
        actual_business_key=business_key,
        supersedes_mapped_actual_id=None,
        is_current=True,
        change_type=MappedActualChangeType.new,
        mapped_by_id=None,
        mapped_at=datetime.now(UTC),
    )
    db_session.add(actual)
    db_session.commit()
    return actual


def _stage_batch(
    client: TestClient,
    headers: dict[str, str],
    uploaded_file_id: str,
    *,
    project_id: str | None = None,
    coverage_mode: str = "snapshot",
    rows: list[dict[str, object]],
    batch_issues: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    batch = _assert_status(
        client.post(
            "/api/v1/actuals-imports/batches",
            headers=headers,
            json={
                "uploadedFileId": uploaded_file_id,
                "coverageMode": coverage_mode,
                "projectId": project_id,
                "sourceSystem": "ceta",
            },
        ),
        201,
    )
    process = _assert_status(
        client.post(
            f"/api/v1/actuals-imports/batches/{batch['id']}/process",
            headers=headers,
        ),
        202,
    )
    _assert_status(
        client.post(
            f"/api/v1/actuals-imports/batches/{batch['id']}/worker-result",
            headers=_worker_headers(),
            json={
                "jobId": process["jobId"],
                "status": "in_review",
                "parserName": "test-parser",
                "parserVersion": "2026.03.31",
                "parserProfile": "generic-ledger",
                "sourceSystem": "ceta",
                "coverageStart": "2026-04-01",
                "coverageEnd": "2026-04-30",
                "batchIssues": batch_issues or [],
                "rows": rows,
            },
        ),
        200,
    )
    return batch


def test_actuals_import_batch_process_and_variance_rollup(client: TestClient, db_session) -> None:
    headers = _login_admin(client)
    project = _create_project_financial_baseline(db_session)
    uploaded_file = _create_uploaded_file(db_session)
    _create_current_actual(
        db_session,
        project_id=project.id,
        business_key="historic-actual-1",
        amount=2000,
    )

    batch = _assert_status(
        client.post(
            "/api/v1/actuals-imports/batches",
            headers=headers,
            json={
                "uploadedFileId": uploaded_file.id,
                "coverageMode": "snapshot",
                "projectId": project.id,
                "sourceSystem": "ceta",
            },
        ),
        201,
    )
    processed = _assert_status(
        client.post(
            f"/api/v1/actuals-imports/batches/{batch['id']}/process",
            headers=headers,
        ),
        202,
    )
    assert processed["queueName"] == "ceta_import"

    detail = _assert_status(
        client.post(
            f"/api/v1/actuals-imports/batches/{batch['id']}/worker-result",
            headers=_worker_headers(),
            json={
                "jobId": processed["jobId"],
                "status": "in_review",
                "parserName": "test-parser",
                "parserVersion": "2026.03.31",
                "parserProfile": "generic-ledger",
                "sourceSystem": "ceta",
                "coverageStart": "2026-04-01",
                "coverageEnd": "2026-04-30",
                "rows": [
                    {
                        "rowNumber": 1,
                        "sourceRowUid": "row-1",
                        "rowHash": "row-hash-1",
                        "businessKeyHash": "business-key-1",
                        "externalProjectCode": "BGS1-TRAILER",
                        "normalizedProjectCode": "bgs1-trailer",
                        "workDate": "2026-04-08",
                        "postingDate": "2026-04-08",
                        "sourceDisciplineCode": "online",
                        "description": "Conform suite",
                        "normalizedDescription": "conform suite",
                        "vendorName": "Halo Post",
                        "normalizedVendorName": "halo post",
                        "amount": 2350,
                        "currencyCode": "GBP",
                        "financialType": "cost",
                        "rawPayload": {"description": "Conform suite"},
                        "issues": [],
                    }
                ],
            },
        ),
        200,
    )

    assert detail["status"] == "in_review"
    assert detail["rowCount"] == 1
    assert detail["varianceProjects"][0]["importAmount"] == 2350
    assert detail["varianceProjects"][0]["currentQuoteAmount"] == 10000
    assert detail["varianceProjects"][0]["currentForecastAmount"] == 9000
    assert detail["varianceProjects"][0]["currentActualAmount"] == 2000
    assert detail["reviewBuckets"][1]["key"] == "ambiguous"


def test_actuals_import_worker_result_requires_matching_job(
    client: TestClient, db_session
) -> None:
    headers = _login_admin(client)
    project = _create_project_financial_baseline(db_session)
    uploaded_file = _create_uploaded_file(db_session)

    batch = _assert_status(
        client.post(
            "/api/v1/actuals-imports/batches",
            headers=headers,
            json={
                "uploadedFileId": uploaded_file.id,
                "coverageMode": "snapshot",
                "projectId": project.id,
                "sourceSystem": "ceta",
            },
        ),
        201,
    )
    _assert_status(
        client.post(
            f"/api/v1/actuals-imports/batches/{batch['id']}/process",
            headers=headers,
        ),
        202,
    )

    rejected = client.post(
        f"/api/v1/actuals-imports/batches/{batch['id']}/worker-result",
        headers=_worker_headers(),
        json={
            "jobId": "job-worker-mismatch",
            "status": "in_review",
            "parserName": "test-parser",
            "parserVersion": "2026.03.31",
            "parserProfile": "generic-ledger",
            "sourceSystem": "ceta",
            "coverageStart": "2026-04-01",
            "coverageEnd": "2026-04-30",
            "rows": [],
        },
    )
    assert rejected.status_code == 409


def test_actuals_import_decision_persists_mapping_artifacts_and_posts_actual(
    client: TestClient, db_session
) -> None:
    headers = _login_admin(client)
    project = _create_project_financial_baseline(db_session)
    uploaded_file = _create_uploaded_file(
        db_session,
        storage_key="actuals/batch-2/vendor-summary.csv",
    )

    batch = _stage_batch(
        client,
        headers,
        uploaded_file.id,
        project_id=project.id,
        rows=[
            {
                "rowNumber": 1,
                "sourceRowUid": "row-1",
                "rowHash": "row-hash-1",
                "businessKeyHash": "decision-key-1",
                "externalProjectCode": "BGS1-TRAILER",
                "normalizedProjectCode": "bgs1-trailer",
                "workDate": "2026-04-08",
                "postingDate": "2026-04-08",
                "sourceDisciplineCode": "online",
                "description": "Conform suite",
                "normalizedDescription": "conform suite",
                "vendorName": "Halo Post",
                "normalizedVendorName": "halo post",
                "amount": 2350,
                "currencyCode": "GBP",
                "financialType": "cost",
                "rawPayload": {"description": "Conform suite"},
                "issues": [],
            }
        ],
    )
    rows = _assert_status(
        client.get(
            f"/api/v1/actuals-imports/batches/{batch['id']}/rows",
            headers=headers,
        ),
        200,
    )
    row_id = rows["items"][0]["id"]

    updated = _assert_status(
        client.patch(
            f"/api/v1/actuals-imports/rows/{row_id}/decision",
            headers=headers,
            json={
                "mappedProjectId": project.id,
                "financialType": "cost",
                "costCategoryKey": "editorial_labor",
                "approvalAction": "post_new",
                "reviewerNote": "Approved after finance review.",
                "saveProjectExternalReference": True,
                "saveCategoryAlias": True,
                "saveRule": True,
                "ruleName": "Halo conform",
            },
        ),
        200,
    )
    assert updated["items"][0]["latestDecision"]["approvalAction"] == "post_new"

    approved = _assert_status(
        client.post(
            f"/api/v1/actuals-imports/batches/{batch['id']}/approve",
            headers=headers,
            json={"withdrawActualIds": []},
        ),
        200,
    )
    assert approved["approvedActualCount"] == 1

    db_session.expire_all()
    assert (
        db_session.scalar(select(CetaImport).where(CetaImport.id == batch["id"])).status
        == CetaImportStatus.approved
    )
    assert db_session.scalar(select(ProjectExternalReference)) is not None
    assert db_session.scalar(select(ReferenceTermAlias)) is not None
    assert db_session.scalar(select(ActualMappingRule)) is not None
    posted_actual = db_session.scalar(
        select(MappedActual).where(
            MappedActual.actual_business_key == "decision-key-1"
        )
    )
    assert posted_actual is not None
    assert float(posted_actual.amount) == 2350


def test_actuals_import_approval_requires_review_and_handles_supersede_and_withdraw(
    client: TestClient, db_session
) -> None:
    headers = _login_admin(client)
    project = _create_project_financial_baseline(db_session)
    uploaded_file = _create_uploaded_file(
        db_session,
        storage_key="actuals/batch-3/revenue-mixed.csv",
    )
    repeated_actual = _create_current_actual(
        db_session,
        project_id=project.id,
        business_key="repeat-key",
        amount=1200,
        description="Edit assist prep",
        work_date=date(2026, 4, 8),
    )
    withdrawn_actual = _create_current_actual(
        db_session,
        project_id=project.id,
        business_key="withdraw-key",
        amount=500,
        description="Obsolete current actual",
        work_date=date(2026, 4, 12),
    )

    batch = _stage_batch(
        client,
        headers,
        uploaded_file.id,
        project_id=project.id,
        rows=[
            {
                "rowNumber": 1,
                "sourceRowUid": "row-1",
                "rowHash": "row-hash-1",
                "businessKeyHash": "repeat-key",
                "externalProjectCode": "BGS1-TRAILER",
                "normalizedProjectCode": "bgs1-trailer",
                "workDate": "2026-04-08",
                "postingDate": "2026-04-08",
                "sourceDisciplineCode": "online",
                "description": "Edit assist prep",
                "normalizedDescription": "edit assist prep",
                "vendorName": "Halo Post",
                "normalizedVendorName": "halo post",
                "amount": 1350,
                "currencyCode": "GBP",
                "financialType": "cost",
                "rawPayload": {"description": "Edit assist prep"},
                "issues": [],
            }
        ],
    )
    blocked = client.post(
        f"/api/v1/actuals-imports/batches/{batch['id']}/approve",
        headers=headers,
        json={"withdrawActualIds": []},
    )
    assert blocked.status_code == 409

    rows = _assert_status(
        client.get(
            f"/api/v1/actuals-imports/batches/{batch['id']}/rows",
            headers=headers,
        ),
        200,
    )
    row_id = rows["items"][0]["id"]
    _assert_status(
        client.patch(
            f"/api/v1/actuals-imports/rows/{row_id}/decision",
            headers=headers,
            json={
                "mappedProjectId": project.id,
                "financialType": "cost",
                "costCategoryKey": "editorial_labor",
                "approvalAction": "supersede_existing",
                "matchedExistingActualId": repeated_actual.id,
            },
        ),
        200,
    )

    approved = _assert_status(
        client.post(
            f"/api/v1/actuals-imports/batches/{batch['id']}/approve",
            headers=headers,
            json={"withdrawActualIds": [withdrawn_actual.id]},
        ),
        200,
    )
    assert approved["supersededActualCount"] == 1
    assert approved["withdrawnActualCount"] == 1

    db_session.expire_all()
    repeated_actual_db = db_session.get(MappedActual, repeated_actual.id)
    withdrawn_actual_db = db_session.get(MappedActual, withdrawn_actual.id)
    replacement = db_session.scalar(
        select(MappedActual).where(MappedActual.supersedes_mapped_actual_id == repeated_actual.id)
    )
    assert repeated_actual_db is not None and repeated_actual_db.is_current is False
    assert withdrawn_actual_db is not None and withdrawn_actual_db.is_current is False
    assert replacement is not None
    assert float(replacement.amount) == 1350


def test_actuals_import_approval_rejects_withdrawals_outside_snapshot_candidates(
    client: TestClient, db_session
) -> None:
    headers = _login_admin(client)
    project = _create_project_financial_baseline(db_session)
    other_project = Project(
        code="OTHER-PROJECT",
        name="Other Project",
        status=ProjectStatus.active,
        quote_currency_code="GBP",
    )
    db_session.add(other_project)
    db_session.commit()
    uploaded_file = _create_uploaded_file(
        db_session,
        storage_key="actuals/batch-4/generic-ledger.csv",
    )
    unrelated_actual = _create_current_actual(
        db_session,
        project_id=other_project.id,
        business_key="unrelated-key",
        amount=750,
        description="Unrelated actual",
    )

    batch = _stage_batch(
        client,
        headers,
        uploaded_file.id,
        project_id=project.id,
        rows=[
            {
                "rowNumber": 1,
                "sourceRowUid": "row-1",
                "rowHash": "row-hash-1",
                "businessKeyHash": "decision-key-2",
                "externalProjectCode": "BGS1-TRAILER",
                "normalizedProjectCode": "bgs1-trailer",
                "workDate": "2026-04-08",
                "postingDate": "2026-04-08",
                "sourceDisciplineCode": "online",
                "description": "Conform suite",
                "normalizedDescription": "conform suite",
                "vendorName": "Halo Post",
                "normalizedVendorName": "halo post",
                "amount": 2350,
                "currencyCode": "GBP",
                "financialType": "cost",
                "rawPayload": {"description": "Conform suite"},
                "issues": [],
            }
        ],
    )
    rows = _assert_status(
        client.get(
            f"/api/v1/actuals-imports/batches/{batch['id']}/rows",
            headers=headers,
        ),
        200,
    )
    row_id = rows["items"][0]["id"]
    _assert_status(
        client.patch(
            f"/api/v1/actuals-imports/rows/{row_id}/decision",
            headers=headers,
            json={
                "mappedProjectId": project.id,
                "financialType": "cost",
                "costCategoryKey": "editorial_labor",
                "approvalAction": "post_new",
            },
        ),
        200,
    )

    rejected = client.post(
        f"/api/v1/actuals-imports/batches/{batch['id']}/approve",
        headers=headers,
        json={"withdrawActualIds": [unrelated_actual.id]},
    )
    assert rejected.status_code == 422
