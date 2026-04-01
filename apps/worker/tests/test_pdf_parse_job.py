from __future__ import annotations

from datetime import date

from app.core.queue import QueuedJob
from app.integrations.pdf_parser import (
    CandidateField,
    CandidateLineItem,
    ParseWarning,
    PdfParseResult,
    QuotePdfParseError,
)
from app.jobs import pdf_parse as pdf_parse_module


class NoteRepository:
    def __init__(self) -> None:
        self.notes: list[tuple[str, str]] = []

    def append_job_note(self, job_id: str, note: str) -> None:
        self.notes.append((job_id, note))


def _job(payload: dict[str, object]) -> QueuedJob:
    return QueuedJob(
        id="job-123",
        queue_name="pdf_parse",
        payload=payload,
        attempts=1,
        max_attempts=5,
    )


def test_pdf_parse_job_posts_in_review_result(monkeypatch) -> None:
    posted: dict[str, object] = {}

    def fake_post(run_id: str, payload: dict[str, object]) -> None:
        posted["run_id"] = run_id
        posted["payload"] = payload

    def fake_parse(*, object_key: str, parser_profile: str | None = None) -> PdfParseResult:
        assert object_key == "quote_ingestion/red_room_main/sample.pdf"
        assert parser_profile == "generic-layout"
        return PdfParseResult(
            parser_name="generic-layout-parser",
            parser_version="2026.03.30",
            parser_profile="generic-layout",
            page_count=2,
            text_page_count=2,
            raw_text="Client: North Star Pictures",
            warnings=[
                ParseWarning(
                    code="ocr.low_confidence",
                    message="OCR fallback used.",
                    severity="warning",
                    blocking=False,
                )
            ],
            field_candidates=[
                CandidateField(
                    field_path="client.name",
                    occurrence_index=0,
                    raw_value="North Star Pictures",
                    normalized_text="North Star Pictures",
                    normalized_amount=None,
                    normalized_date=None,
                    confidence=0.93,
                    page_number=1,
                    source_snippet="Client: North Star Pictures",
                    source_bounds={"page": 1, "x": 10, "y": 10, "width": 100, "height": 20},
                ),
                CandidateField(
                    field_path="quote.date",
                    occurrence_index=0,
                    raw_value="2026-03-14",
                    normalized_text=None,
                    normalized_amount=None,
                    normalized_date=date(2026, 3, 14),
                    confidence=0.9,
                    page_number=1,
                    source_snippet="Date: 2026-03-14",
                    source_bounds={"page": 1, "x": 10, "y": 30, "width": 100, "height": 20},
                ),
            ],
            candidate_line_items=[
                CandidateLineItem(
                    section_name="Offline Edit",
                    description="Lead Editor",
                    quantity=5.0,
                    unit="day",
                    rate=850.0,
                    amount=4250.0,
                    confidence=0.88,
                    page_number=2,
                    source_snippet="Lead Editor 5 day @ 850.00 = 4250.00",
                    source_bounds={"page": 2, "x": 10, "y": 50, "width": 100, "height": 20},
                )
            ],
        )

    monkeypatch.setattr(pdf_parse_module, "_post_worker_result", fake_post)
    monkeypatch.setattr(pdf_parse_module.quote_pdf_parser, "parse", fake_parse)
    repository = NoteRepository()

    pdf_parse_module.handle_pdf_parse(
        _job(
            {
                "runId": "run-abc",
                "uploadedFileId": "file-123",
                "objectKey": "quote_ingestion/red_room_main/sample.pdf",
                "parserProfile": "generic-layout",
                "projectId": "project_red_room",
            }
        ),
        repository,
    )

    assert posted["run_id"] == "run-abc"
    payload = posted["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "in_review"
    assert payload["jobId"] == "job-123"
    assert payload["parserProfile"] == "generic-layout"
    assert payload["projectId"] == "project_red_room"
    assert payload["fieldCandidates"][0]["fieldPath"] == "client.name"
    assert payload["fieldCandidates"][1]["normalizedDate"] == "2026-03-14"
    assert payload["lineItemCandidates"][0]["sortOrder"] == 1
    assert repository.notes


def test_pdf_parse_job_posts_failed_result_for_parse_errors(monkeypatch) -> None:
    posted: dict[str, object] = {}

    def fake_post(run_id: str, payload: dict[str, object]) -> None:
        posted["run_id"] = run_id
        posted["payload"] = payload

    def fake_parse(*, object_key: str, parser_profile: str | None = None) -> PdfParseResult:
        raise QuotePdfParseError("unreadable_pdf", "Unable to parse PDF.")

    monkeypatch.setattr(pdf_parse_module, "_post_worker_result", fake_post)
    monkeypatch.setattr(pdf_parse_module.quote_pdf_parser, "parse", fake_parse)
    repository = NoteRepository()

    pdf_parse_module.handle_pdf_parse(
        _job(
            {
                "runId": "run-failed",
                "uploadedFileId": "file-999",
                "objectKey": "quote_ingestion/fail_case/quote_fail.pdf",
            }
        ),
        repository,
    )

    assert posted["run_id"] == "run-failed"
    payload = posted["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "failed"
    assert payload["failureCode"] == "unreadable_pdf"
    assert payload["jobId"] == "job-123"
    assert repository.notes


def test_pdf_parse_job_supports_legacy_batch_payload(monkeypatch) -> None:
    called = {"post_result": False}

    def fake_post(run_id: str, payload: dict[str, object]) -> None:
        called["post_result"] = True

    monkeypatch.setattr(pdf_parse_module, "_post_worker_result", fake_post)
    repository = NoteRepository()

    pdf_parse_module.handle_pdf_parse(
        _job({"batchId": "legacy-batch-1"}),
        repository,
    )

    assert called["post_result"] is False
    assert repository.notes
