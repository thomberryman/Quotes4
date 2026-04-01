from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.queue import DerivedWriteRepository, QueuedJob
from app.integrations.pdf_parser import PdfParseResult, QuotePdfParseError, quote_pdf_parser
from app.jobs.types import WorkerJob


def _optional_payload_string(raw_value: object | None) -> str | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    return value or None


def _required_payload_string(job: QueuedJob, key: str) -> str:
    value = _optional_payload_string(job.payload.get(key))
    if value is None:
        raise ValueError(f"pdf_parse job '{job.id}' is missing required payload field '{key}'.")
    return value


def _worker_result_url(run_id: str) -> str:
    settings = get_settings()
    base_path = settings.api_base_path
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    return (
        f"{settings.api_base_url.rstrip('/')}"
        f"{base_path}/quote-ingestion/runs/{run_id}/worker-result"
    )


def _post_worker_result(run_id: str, payload: dict[str, Any]) -> None:
    settings = get_settings()
    with httpx.Client(timeout=settings.api_timeout_seconds) as client:
        response = client.post(
            _worker_result_url(run_id),
            json=payload,
            headers={"X-Worker-Token": settings.worker_callback_token},
        )
    response.raise_for_status()


def _build_success_payload(
    *,
    job: QueuedJob,
    parse_profile_hint: str | None,
    project_id: str | None,
    result: PdfParseResult,
) -> dict[str, Any]:
    return {
        "jobId": job.id,
        "status": "in_review",
        "parserName": result.parser_name,
        "parserVersion": result.parser_version,
        "parserProfile": result.parser_profile or parse_profile_hint,
        "pageCount": result.page_count,
        "textPageCount": result.text_page_count,
        "rawText": result.raw_text,
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "severity": warning.severity,
                "blocking": warning.blocking,
            }
            for warning in result.warnings
        ],
        "fieldCandidates": [
            {
                "fieldPath": field.field_path,
                "occurrenceIndex": field.occurrence_index,
                "rawValue": field.raw_value,
                "normalizedText": field.normalized_text,
                "normalizedAmount": field.normalized_amount,
                "normalizedDate": (
                    field.normalized_date.isoformat() if field.normalized_date else None
                ),
                "confidenceScore": field.confidence,
                "pageNumber": field.page_number,
                "sourceSnippet": field.source_snippet,
                "sourceBounds": field.source_bounds,
            }
            for field in result.field_candidates
        ],
        "lineItemCandidates": [
            {
                "sortOrder": sort_order,
                "sectionLabel": line_item.section_name,
                "lineType": "service",
                "description": line_item.description,
                "quantity": line_item.quantity,
                "unit": line_item.unit,
                "rate": line_item.rate,
                "amount": line_item.amount,
                "currencyCode": None,
                "confidenceScore": line_item.confidence,
                "pageNumber": line_item.page_number,
                "sourceSnippet": line_item.source_snippet,
                "sourceBounds": line_item.source_bounds,
            }
            for sort_order, line_item in enumerate(result.candidate_line_items, start=1)
        ],
        "projectId": project_id,
    }


def handle_pdf_parse(job: QueuedJob, repository: DerivedWriteRepository) -> None:
    run_id = _optional_payload_string(job.payload.get("runId"))
    if run_id is None:
        batch_id = _optional_payload_string(job.payload.get("batchId"))
        if batch_id is not None:
            repository.append_job_note(
                job.id,
                f"Queued legacy quote PDF batch parse request for batch {batch_id}.",
            )
            return
        raise ValueError(
            f"pdf_parse job '{job.id}' does not include 'runId' or a supported 'batchId'."
        )

    uploaded_file_id = _required_payload_string(job, "uploadedFileId")
    object_key = _required_payload_string(job, "objectKey")
    parser_profile = _optional_payload_string(job.payload.get("parserProfile"))
    project_id = _optional_payload_string(job.payload.get("projectId"))
    try:
        result = quote_pdf_parser.parse(object_key=object_key, parser_profile=parser_profile)
    except QuotePdfParseError as exc:
        _post_worker_result(
            run_id,
            {
                "jobId": job.id,
                "status": "failed",
                "failureCode": exc.code,
                "failureMessage": str(exc),
                "projectId": project_id,
            },
        )
        repository.append_job_note(
            job.id,
            (
                "Failed quote PDF parse for file "
                f"{uploaded_file_id} on extraction run {run_id}: {exc.code}."
            ),
        )
        return

    _post_worker_result(
        run_id,
        _build_success_payload(
            job=job,
            parse_profile_hint=parser_profile,
            project_id=project_id,
            result=result,
        ),
    )
    repository.append_job_note(
        job.id,
        (
            "Parsed quote PDF file "
            f"{uploaded_file_id} for extraction run {run_id} and posted authoritative "
            "worker results."
        ),
    )


pdf_parse_job = WorkerJob(
    name="quote-pdf-parse",
    description="Extract quote PDF content into staging rows for human review.",
    queue_name="pdf_parse",
    retry_backoff_seconds=30,
    handler=handle_pdf_parse,
)
