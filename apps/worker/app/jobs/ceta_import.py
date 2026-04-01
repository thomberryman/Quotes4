from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.queue import DerivedWriteRepository, QueuedJob
from app.integrations.ceta_parser import CetaParseError, CetaParseResult, ceta_parser
from app.jobs.types import WorkerJob


def _optional_payload_string(raw_value: object | None) -> str | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    return value or None


def _required_payload_string(job: QueuedJob, key: str) -> str:
    value = _optional_payload_string(job.payload.get(key))
    if value is None:
        raise ValueError(f"ceta_import job '{job.id}' is missing required payload field '{key}'.")
    return value


def _worker_result_url(batch_id: str) -> str:
    settings = get_settings()
    base_path = settings.api_base_path
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    return (
        f"{settings.api_base_url.rstrip('/')}"
        f"{base_path}/actuals-imports/batches/{batch_id}/worker-result"
    )


def _post_worker_result(batch_id: str, payload: dict[str, Any]) -> None:
    settings = get_settings()
    with httpx.Client(timeout=settings.api_timeout_seconds) as client:
        response = client.post(
            _worker_result_url(batch_id),
            json=payload,
            headers={"X-Worker-Token": settings.worker_callback_token},
        )
    response.raise_for_status()


def _build_success_payload(job: QueuedJob, result: CetaParseResult) -> dict[str, Any]:
    return {
        "jobId": job.id,
        "status": "in_review",
        "parserName": result.parser_name,
        "parserVersion": result.parser_version,
        "parserProfile": result.parser_profile,
        "sourceSystem": result.source_system,
        "coverageStart": result.coverage_start.isoformat() if result.coverage_start else None,
        "coverageEnd": result.coverage_end.isoformat() if result.coverage_end else None,
        "batchIssues": [
            {
                "severity": issue.severity,
                "issueCode": issue.issue_code,
                "fieldName": issue.field_name,
                "message": issue.message,
                "details": issue.details,
            }
            for issue in result.batch_issues
        ],
        "rows": [
            {
                "rowNumber": row.row_number,
                "sourceRowUid": row.source_row_uid,
                "rowHash": row.row_hash,
                "businessKeyHash": row.business_key_hash,
                "duplicateGroupKey": row.duplicate_group_key,
                "externalProjectCode": row.external_project_code,
                "normalizedProjectCode": row.normalized_project_code,
                "workDate": row.work_date.isoformat() if row.work_date else None,
                "postingDate": row.posting_date.isoformat() if row.posting_date else None,
                "sourceDisciplineCode": row.source_discipline_code,
                "description": row.description,
                "normalizedDescription": row.normalized_description,
                "vendorName": row.vendor_name,
                "normalizedVendorName": row.normalized_vendor_name,
                "amount": row.amount,
                "currencyCode": row.currency_code,
                "financialType": row.financial_type,
                "rawPayload": row.raw_payload,
                "issues": [
                    {
                        "severity": issue.severity,
                        "issueCode": issue.issue_code,
                        "fieldName": issue.field_name,
                        "message": issue.message,
                        "details": issue.details,
                    }
                    for issue in row.issues
                ],
            }
            for row in result.rows
        ],
    }


def handle_ceta_import(job: QueuedJob, repository: DerivedWriteRepository) -> None:
    batch_id = _required_payload_string(job, "batchId")
    uploaded_file_id = _required_payload_string(job, "uploadedFileId")
    object_key = _required_payload_string(job, "objectKey")
    parser_profile_hint = _optional_payload_string(job.payload.get("parserProfileHint"))
    try:
        result = ceta_parser.parse(object_key=object_key, parser_profile=parser_profile_hint)
    except CetaParseError as exc:
        _post_worker_result(
            batch_id,
            {
                "jobId": job.id,
                "status": "failed",
                "failureCode": exc.code,
                "failureMessage": str(exc),
            },
        )
        repository.append_job_note(
            job.id,
            (
                "Failed CETA import parse for file "
                f"{uploaded_file_id} on batch {batch_id}: {exc.code}."
            ),
        )
        return

    _post_worker_result(batch_id, _build_success_payload(job, result))
    repository.append_job_note(
        job.id,
        (
            "Parsed CETA import file "
            f"{uploaded_file_id} for batch {batch_id} and posted authoritative worker results."
        ),
    )


ceta_import_job = WorkerJob(
    name="ceta-import",
    description="Normalize CETA actuals and write traceable staging records.",
    queue_name="ceta_import",
    retry_backoff_seconds=30,
    handler=handle_ceta_import,
)
