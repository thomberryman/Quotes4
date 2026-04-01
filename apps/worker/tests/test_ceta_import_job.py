from __future__ import annotations

from app.core.queue import QueuedJob
from app.integrations.ceta_parser import CetaParseResult, ceta_parser
from app.jobs import ceta_import as ceta_import_module


class NoteRepository:
    def __init__(self) -> None:
        self.notes: list[tuple[str, str]] = []

    def append_job_note(self, job_id: str, note: str) -> None:
        self.notes.append((job_id, note))


def _job(payload: dict[str, object]) -> QueuedJob:
    return QueuedJob(
        id="job-ceta-123",
        queue_name="ceta_import",
        payload=payload,
        attempts=1,
        max_attempts=5,
    )


def test_ceta_import_job_posts_review_result(monkeypatch) -> None:
    posted: dict[str, object] = {}

    def fake_post(batch_id: str, payload: dict[str, object]) -> None:
        posted["batch_id"] = batch_id
        posted["payload"] = payload

    monkeypatch.setattr(ceta_import_module, "_post_worker_result", fake_post)
    repository = NoteRepository()

    ceta_import_module.handle_ceta_import(
        _job(
            {
                "batchId": "batch-abc",
                "uploadedFileId": "file-123",
                "objectKey": "actuals/batch-abc/generic_snapshot.csv",
            }
        ),
        repository,
    )

    assert posted["batch_id"] == "batch-abc"
    payload = posted["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "in_review"
    assert payload["parserProfile"] == "generic-ledger"
    assert len(payload["rows"]) == 3
    assert payload["rows"][0]["financialType"] == "cost"
    assert repository.notes


def test_ceta_import_job_posts_failed_result(monkeypatch) -> None:
    posted: dict[str, object] = {}

    def fake_post(batch_id: str, payload: dict[str, object]) -> None:
        posted["batch_id"] = batch_id
        posted["payload"] = payload

    monkeypatch.setattr(ceta_import_module, "_post_worker_result", fake_post)
    repository = NoteRepository()

    ceta_import_module.handle_ceta_import(
        _job(
            {
                "batchId": "batch-failed",
                "uploadedFileId": "file-999",
                "objectKey": "actuals/batch-failed/fail_case.csv",
            }
        ),
        repository,
    )

    assert posted["batch_id"] == "batch-failed"
    payload = posted["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "failed"
    assert payload["failureCode"] == "unsupported_ceta_export"
    assert repository.notes


def test_ceta_parser_supports_multiple_known_profiles() -> None:
    vendor_result: CetaParseResult = ceta_parser.parse(
        object_key="actuals/vendor_summary/may_export.csv"
    )
    revenue_result: CetaParseResult = ceta_parser.parse(
        object_key="actuals/revenue_mixed/june_export.csv"
    )

    assert vendor_result.parser_profile == "vendor-summary"
    assert vendor_result.rows[1].duplicate_group_key is not None
    assert revenue_result.parser_profile == "revenue-mixed"
    assert revenue_result.rows[1].issues[0].issue_code == "missing_project_code"
