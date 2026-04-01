from __future__ import annotations

import os

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import (
    PdfExtractionFieldResult,
    PdfExtractionLineItemResult,
    PdfExtractionRun,
    QuoteVersionFile,
)

TEST_CHECKSUM = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _assert_status(response, expected_status: int) -> dict[str, object]:
    assert response.status_code == expected_status, response.text
    return response.json()


def _bearer_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _worker_headers() -> dict[str, str]:
    return {"X-Worker-Token": os.environ["WORKER_CALLBACK_TOKEN"]}


def _login(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/session",
        json={
            "email": os.environ["DEV_ADMIN_EMAIL"],
            "password": os.environ["DEV_ADMIN_PASSWORD"],
        },
    )
    return _assert_status(response, 200)


def test_quote_ingestion_core_flow(client: TestClient, db_session) -> None:
    session = _login(client)
    headers = _bearer_headers(str(session["accessToken"]))

    project = _assert_status(
        client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "name": "Red Room Trailer Campaign",
                "status": "bid",
                "quoteCurrencyCode": "GBP",
            },
        ),
        201,
    )

    upload_intent = _assert_status(
        client.post(
            "/api/v1/quote-ingestion/uploads/presign",
            headers=headers,
            json={
                "fileName": "red-room-quote.pdf",
                "contentType": "application/pdf",
                "sizeBytes": 1024,
                "checksumSha256": TEST_CHECKSUM,
            },
        ),
        201,
    )
    assert upload_intent["file"]["fileCategory"] == "quote_pdf"

    finalized = _assert_status(
        client.post(
            "/api/v1/quote-ingestion/uploads/finalize",
            headers=headers,
            json={
                "fileId": upload_intent["file"]["fileId"],
                "objectKey": upload_intent["file"]["objectKey"],
                "checksumSha256": TEST_CHECKSUM,
            },
        ),
        200,
    )
    assert finalized["file"]["status"] == "uploaded"

    run = _assert_status(
        client.post(
            "/api/v1/quote-ingestion/runs",
            headers=headers,
            json={
                "uploadedFileId": finalized["file"]["fileId"],
                "projectId": project["id"],
                "parserProfile": "generic-layout",
            },
        ),
        201,
    )
    assert run["status"] == "queued"

    unauthorized_worker_result = client.post(
        f"/api/v1/quote-ingestion/runs/{run['id']}/worker-result",
        json={"jobId": run["jobId"], "status": "failed"},
    )
    assert unauthorized_worker_result.status_code == 401

    worker_result = _assert_status(
        client.post(
            f"/api/v1/quote-ingestion/runs/{run['id']}/worker-result",
            headers=_worker_headers(),
            json={
                "jobId": run["jobId"],
                "status": "in_review",
                "parserName": "generic-layout-parser",
                "parserVersion": "2026.03.30",
                "parserProfile": "generic-layout",
                "pageCount": 2,
                "textPageCount": 2,
                "rawText": "Client: North Star Pictures",
                "warnings": [],
                "fieldCandidates": [
                    {
                        "fieldPath": "client.name",
                        "occurrenceIndex": 0,
                        "rawValue": "North Star Pictures",
                        "normalizedText": "North Star Pictures",
                        "confidenceScore": 0.97,
                        "pageNumber": 1,
                        "sourceSnippet": "Client: North Star Pictures",
                        "sourceBounds": {"page": 1, "x": 10, "y": 10, "width": 100, "height": 20},
                    },
                    {
                        "fieldPath": "project.title",
                        "occurrenceIndex": 0,
                        "rawValue": "Red Room Trailer Campaign",
                        "normalizedText": "Red Room Trailer Campaign",
                        "confidenceScore": 0.95,
                        "pageNumber": 1,
                        "sourceSnippet": "Project: Red Room Trailer Campaign",
                        "sourceBounds": {"page": 1, "x": 10, "y": 30, "width": 120, "height": 20},
                    },
                    {
                        "fieldPath": "quote.title",
                        "occurrenceIndex": 0,
                        "rawValue": "Red Room Trailer Campaign - Offline Edit",
                        "normalizedText": "Red Room Trailer Campaign - Offline Edit",
                        "confidenceScore": 0.96,
                        "pageNumber": 1,
                        "sourceSnippet": "TITLE: Red Room Trailer Campaign - Offline Edit",
                        "sourceBounds": {"page": 1, "x": 10, "y": 40, "width": 160, "height": 20},
                    },
                    {
                        "fieldPath": "quote.date",
                        "occurrenceIndex": 0,
                        "rawValue": "2026-03-14",
                        "normalizedDate": "2026-03-14",
                        "confidenceScore": 0.94,
                        "pageNumber": 1,
                        "sourceSnippet": "Date: 2026-03-14",
                        "sourceBounds": {"page": 1, "x": 10, "y": 50, "width": 120, "height": 20},
                    },
                    {
                        "fieldPath": "quote.currency_code",
                        "occurrenceIndex": 0,
                        "rawValue": "GBP",
                        "normalizedText": "GBP",
                        "confidenceScore": 0.98,
                        "pageNumber": 1,
                        "sourceSnippet": "Currency: GBP",
                        "sourceBounds": {"page": 1, "x": 10, "y": 70, "width": 80, "height": 20},
                    },
                    {
                        "fieldPath": "quote.source_version_label",
                        "occurrenceIndex": 0,
                        "rawValue": "v2",
                        "normalizedText": "v2",
                        "confidenceScore": 0.9,
                        "pageNumber": 1,
                        "sourceSnippet": "Version: v2",
                        "sourceBounds": {"page": 1, "x": 10, "y": 90, "width": 80, "height": 20},
                    },
                    {
                        "fieldPath": "quote.quote_number",
                        "occurrenceIndex": 0,
                        "rawValue": "6073",
                        "normalizedText": "6073",
                        "confidenceScore": 0.99,
                        "pageNumber": 1,
                        "sourceSnippet": "QUOTE ID: 6073",
                        "sourceBounds": {"page": 1, "x": 10, "y": 100, "width": 80, "height": 20},
                    },
                    {
                        "fieldPath": "totals.subtotal",
                        "occurrenceIndex": 0,
                        "rawValue": "12750.00",
                        "normalizedAmount": 12750.0,
                        "confidenceScore": 0.9,
                        "pageNumber": 2,
                        "sourceSnippet": "Subtotal 12750.00",
                        "sourceBounds": {"page": 2, "x": 10, "y": 10, "width": 120, "height": 20},
                    },
                    {
                        "fieldPath": "totals.tax",
                        "occurrenceIndex": 0,
                        "rawValue": "0.00",
                        "normalizedAmount": 0.0,
                        "confidenceScore": 0.88,
                        "pageNumber": 2,
                        "sourceSnippet": "Tax 0.00",
                        "sourceBounds": {"page": 2, "x": 10, "y": 30, "width": 80, "height": 20},
                    },
                    {
                        "fieldPath": "totals.total",
                        "occurrenceIndex": 0,
                        "rawValue": "12750.00",
                        "normalizedAmount": 12750.0,
                        "confidenceScore": 0.92,
                        "pageNumber": 2,
                        "sourceSnippet": "Total 12750.00",
                        "sourceBounds": {"page": 2, "x": 10, "y": 50, "width": 120, "height": 20},
                    },
                ],
                "lineItemCandidates": [
                    {
                        "sortOrder": 1,
                        "sectionLabel": "Offline Edit",
                        "lineType": "service",
                        "description": "Lead Editor",
                        "quantity": 15.0,
                        "unit": "day",
                        "rate": 850.0,
                        "amount": 12750.0,
                        "confidenceScore": 0.93,
                        "pageNumber": 2,
                        "sourceSnippet": "Lead Editor 15 day @ 850.00 = 12750.00",
                        "sourceBounds": {"page": 2, "x": 92, "y": 410, "width": 362, "height": 24},
                    }
                ],
                "projectId": project["id"],
            },
        ),
        200,
    )
    assert worker_result["status"] == "in_review"
    assert worker_result["confidenceSummary"]["high"] >= 1

    required_fields = {
        "client.name",
        "quote.title",
        "quote.quote_number",
        "quote.date",
        "quote.currency_code",
        "totals.total",
        "totals.subtotal",
        "totals.tax",
        "quote.source_version_label",
    }
    review = _assert_status(
        client.patch(
            f"/api/v1/quote-ingestion/runs/{run['id']}/review",
            headers=headers,
            json={
                "selectedProjectId": project["id"],
                "selectedTargetMode": "new_quote",
                "fieldDecisions": [
                    {
                        "fieldPath": decision["fieldPath"],
                        "selectedResultId": decision["selectedResultId"],
                        "reviewedText": decision["reviewedText"],
                        "reviewedAmount": decision["reviewedAmount"],
                        "reviewedDate": decision["reviewedDate"],
                        "reviewStatus": "approved",
                        "reviewerNote": None,
                    }
                    for decision in worker_result["fieldDecisions"]
                    if decision["fieldPath"] in required_fields
                ],
                "lineItemDecisions": [
                    {
                        "sortOrder": decision["sortOrder"],
                        "sourceResultId": decision["sourceResultId"],
                        "sectionLabel": decision["sectionLabel"],
                        "lineType": decision["lineType"],
                        "description": decision["description"],
                        "quantity": decision["quantity"],
                        "unit": decision["unit"],
                        "rate": decision["rate"],
                        "amount": decision["amount"],
                        "reviewStatus": "approved",
                        "reviewerNote": None,
                    }
                    for decision in worker_result["lineItemDecisions"]
                ],
            },
        ),
        200,
    )
    assert review["approvalBlockers"] == []

    approval = _assert_status(
        client.post(
            f"/api/v1/quote-ingestion/runs/{run['id']}/approve",
            headers=headers,
            json={},
        ),
        200,
    )
    assert approval["status"] == "approved"

    approved_run = _assert_status(
        client.get(f"/api/v1/quote-ingestion/runs/{run['id']}", headers=headers),
        200,
    )
    assert approved_run["approvedQuoteId"] == approval["approvedQuoteId"]
    assert approved_run["approvedQuoteVersionId"] == approval["approvedQuoteVersionId"]

    quote = _assert_status(
        client.get(f"/api/v1/quotes/{approval['approvedQuoteId']}", headers=headers),
        200,
    )
    version = _assert_status(
        client.get(
            f"/api/v1/quotes/versions/{approval['approvedQuoteVersionId']}",
            headers=headers,
        ),
        200,
    )
    assert quote["projectId"] == project["id"]
    assert quote["quoteNumber"] == "6073"
    assert quote["title"] == "Red Room Trailer Campaign - Offline Edit"
    assert version["sourceVersionLabel"] == "v2"
    assert version["totalAmount"] == 12750.0
    assert len(version["sections"]) == 1

    audit_events = _assert_status(
        client.get(
            f"/api/v1/audit/events?entityType=pdf_extraction_run&entityId={run['id']}",
            headers=headers,
        ),
        200,
    )
    actions = {item["action"] for item in audit_events["items"]}
    assert "quote_ingestion.run.created" in actions
    assert "quote_ingestion.worker_result.applied" in actions
    assert "quote_ingestion.review.updated" in actions
    assert "quote_ingestion.approved" in actions

    persisted_run = db_session.get(PdfExtractionRun, run["id"])
    assert persisted_run is not None
    assert persisted_run.approved_quote_version_id == approval["approvedQuoteVersionId"]

    persisted_fields = list(
      db_session.scalars(
          select(PdfExtractionFieldResult).where(PdfExtractionFieldResult.run_id == run["id"])
      )
    )
    persisted_line_items = list(
      db_session.scalars(
          select(PdfExtractionLineItemResult).where(
              PdfExtractionLineItemResult.run_id == run["id"]
          )
      )
    )
    source_file_links = list(
      db_session.scalars(
          select(QuoteVersionFile).where(
              QuoteVersionFile.quote_version_id == approval["approvedQuoteVersionId"]
    )
    )
    )
    assert len(persisted_fields) == 10
    assert len(persisted_line_items) == 1
    assert len(source_file_links) == 1


def test_quote_ingestion_preview_rejects_unsafe_object_keys(client: TestClient) -> None:
    session = _login(client)
    headers = _bearer_headers(str(session["accessToken"]))

    response = client.get(
        "/api/v1/quote-ingestion/preview",
        headers=headers,
        params={"object_key": "http://example.com/quote.pdf"},
    )
    assert response.status_code == 422


def test_quote_ingestion_prefers_exact_quote_id_match_for_new_versions(
    client: TestClient,
) -> None:
    session = _login(client)
    headers = _bearer_headers(str(session["accessToken"]))

    project = _assert_status(
        client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "name": "People of the Book",
                "status": "bid",
                "quoteCurrencyCode": "GBP",
            },
        ),
        201,
    )
    quote = _assert_status(
        client.post(
            "/api/v1/quotes",
            headers=headers,
            json={
                "projectId": project["id"],
                "quoteNumber": "6076",
                "title": "People of the Book - Sound Finishing",
            },
        ),
        201,
    )

    upload_intent = _assert_status(
        client.post(
            "/api/v1/quote-ingestion/uploads/presign",
            headers=headers,
            json={
                "fileName": "people-of-the-book-sound-finishing-latest.pdf",
                "contentType": "application/pdf",
                "sizeBytes": 1024,
                "checksumSha256": TEST_CHECKSUM,
            },
        ),
        201,
    )
    finalized = _assert_status(
        client.post(
            "/api/v1/quote-ingestion/uploads/finalize",
            headers=headers,
            json={
                "fileId": upload_intent["file"]["fileId"],
                "objectKey": upload_intent["file"]["objectKey"],
                "checksumSha256": TEST_CHECKSUM,
            },
        ),
        200,
    )
    run = _assert_status(
        client.post(
            "/api/v1/quote-ingestion/runs",
            headers=headers,
            json={
                "uploadedFileId": finalized["file"]["fileId"],
                "parserProfile": "harbor-estimate",
            },
        ),
        201,
    )

    worker_result = _assert_status(
        client.post(
            f"/api/v1/quote-ingestion/runs/{run['id']}/worker-result",
            headers=_worker_headers(),
            json={
                "jobId": run["jobId"],
                "status": "in_review",
                "parserName": "harbor-estimate-parser",
                "parserVersion": "2026.03.31",
                "parserProfile": "harbor-estimate",
                "pageCount": 2,
                "textPageCount": 2,
                "rawText": "TITLE: People of the Book - Sound Finishing",
                "warnings": [],
                "fieldCandidates": [
                    {
                        "fieldPath": "client.name",
                        "occurrenceIndex": 0,
                        "rawValue": "LSPW Project Ltd",
                        "normalizedText": "LSPW Project Ltd",
                        "confidenceScore": 0.97,
                        "pageNumber": 1,
                        "sourceSnippet": "CLIENT: LSPW Project Ltd",
                        "sourceBounds": {"page": 1, "line": 3},
                    },
                    {
                        "fieldPath": "project.title",
                        "occurrenceIndex": 0,
                        "rawValue": "People of the Book",
                        "normalizedText": "People of the Book",
                        "confidenceScore": 0.84,
                        "pageNumber": 1,
                        "sourceSnippet": "People of the Book:",
                        "sourceBounds": {"page": 1, "line": 8},
                    },
                    {
                        "fieldPath": "quote.title",
                        "occurrenceIndex": 0,
                        "rawValue": "People of the Book - Sound Finishing",
                        "normalizedText": "People of the Book - Sound Finishing",
                        "confidenceScore": 0.98,
                        "pageNumber": 1,
                        "sourceSnippet": "TITLE: People of the Book - Sound Finishing",
                        "sourceBounds": {"page": 1, "line": 2},
                    },
                    {
                        "fieldPath": "quote.quote_number",
                        "occurrenceIndex": 0,
                        "rawValue": "6076",
                        "normalizedText": "6076",
                        "confidenceScore": 0.99,
                        "pageNumber": 1,
                        "sourceSnippet": "QUOTE ID: 6076",
                        "sourceBounds": {"page": 1, "line": 7},
                    },
                    {
                        "fieldPath": "quote.date",
                        "occurrenceIndex": 0,
                        "rawValue": "2026-02-13",
                        "normalizedDate": "2026-02-13",
                        "confidenceScore": 0.97,
                        "pageNumber": 1,
                        "sourceSnippet": "DATE: 13th February 2026",
                        "sourceBounds": {"page": 1, "line": 1},
                    },
                    {
                        "fieldPath": "quote.currency_code",
                        "occurrenceIndex": 0,
                        "rawValue": "GBP",
                        "normalizedText": "GBP",
                        "confidenceScore": 0.96,
                        "pageNumber": 2,
                        "sourceSnippet": "GRAND TOTAL: 255,080.00 GBP",
                        "sourceBounds": {"page": 2, "line": 20},
                    },
                    {
                        "fieldPath": "totals.subtotal",
                        "occurrenceIndex": 0,
                        "rawValue": "255080.00",
                        "normalizedAmount": 255080.0,
                        "confidenceScore": 0.89,
                        "pageNumber": 2,
                        "sourceSnippet": "GRAND TOTAL: 255,080.00 GBP",
                        "sourceBounds": {"page": 2, "line": 20},
                    },
                    {
                        "fieldPath": "totals.tax",
                        "occurrenceIndex": 0,
                        "rawValue": "0.00",
                        "normalizedAmount": 0.0,
                        "confidenceScore": 0.84,
                        "pageNumber": 2,
                        "sourceSnippet": "GRAND TOTAL: 255,080.00 GBP",
                        "sourceBounds": {"page": 2, "line": 20},
                    },
                    {
                        "fieldPath": "totals.total",
                        "occurrenceIndex": 0,
                        "rawValue": "255080.00",
                        "normalizedAmount": 255080.0,
                        "confidenceScore": 0.97,
                        "pageNumber": 2,
                        "sourceSnippet": "GRAND TOTAL: 255,080.00 GBP",
                        "sourceBounds": {"page": 2, "line": 20},
                    },
                ],
                "lineItemCandidates": [
                    {
                        "sortOrder": 1,
                        "sectionLabel": "Sound Mix",
                        "lineType": "service",
                        "description": "Final Mix",
                        "quantity": 120.0,
                        "unit": "hour",
                        "rate": 470.0,
                        "amount": 56400.0,
                        "confidenceScore": 0.93,
                        "pageNumber": 2,
                        "sourceSnippet": "Final Mix 1 120 470.00 / Hour 56,400.00",
                        "sourceBounds": {"page": 2, "line": 10},
                    }
                ],
            },
        ),
        200,
    )

    assert worker_result["selectedTargetMode"] == "new_version"
    assert worker_result["selectedProjectId"] == project["id"]
    assert worker_result["selectedQuoteId"] == quote["id"]
    assert any(
        suggestion["entityId"] == quote["id"]
        and suggestion["isSelected"]
        and "Quote ID matches an existing quote." in suggestion["reasons"]
        for suggestion in worker_result["matchSuggestions"]
    )
