from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.core.config import get_settings


@dataclass(frozen=True)
class QueuedJob:
    id: str
    queue_name: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


class PostgresJobQueue:
    def __init__(self) -> None:
        self.settings = get_settings()

    def reserve_next_job(self, queue_names: list[str]) -> QueuedJob | None:
        if not queue_names:
            return None

        statement = """
        WITH next_job AS (
            SELECT id
            FROM background_jobs
            WHERE status = 'queued'
              AND queue_name = ANY(%(queue_names)s)
              AND available_at <= NOW()
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE background_jobs
        SET status = 'running',
            attempts = attempts + 1,
            locked_at = NOW(),
            locked_by = %(worker_name)s,
            updated_at = NOW()
        WHERE id IN (SELECT id FROM next_job)
        RETURNING id, queue_name, payload_json, attempts, max_attempts
        """
        with psycopg.connect(self.settings.database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    statement,
                    {"queue_names": queue_names, "worker_name": self.settings.worker_name},
                )
                row = cursor.fetchone()
                connection.commit()

        if row is None:
            return None

        return QueuedJob(
            id=row["id"],
            queue_name=row["queue_name"],
            payload=dict(row["payload_json"]),
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
        )

    def mark_succeeded(self, job_id: str) -> None:
        self._update_status(job_id, "succeeded")

    def mark_failed(
        self,
        job: QueuedJob,
        error_message: str,
        *,
        retry_backoff_seconds: int,
    ) -> None:
        with psycopg.connect(self.settings.database_url) as connection:
            with connection.cursor() as cursor:
                if job.attempts < job.max_attempts:
                    next_available_at = datetime.now(UTC) + timedelta(seconds=retry_backoff_seconds)
                    cursor.execute(
                        """
                        UPDATE background_jobs
                        SET status = 'queued',
                            available_at = %(available_at)s,
                            failed_at = NULL,
                            completed_at = NULL,
                            last_error = %(error_message)s,
                            locked_at = NULL,
                            locked_by = NULL,
                            updated_at = NOW()
                        WHERE id = %(job_id)s
                        """,
                        {
                            "job_id": job.id,
                            "error_message": error_message,
                            "available_at": next_available_at,
                        },
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE background_jobs
                        SET status = 'failed',
                            failed_at = NOW(),
                            completed_at = NULL,
                            last_error = %(error_message)s,
                            locked_at = NULL,
                            locked_by = NULL,
                            updated_at = NOW()
                        WHERE id = %(job_id)s
                        """,
                        {"job_id": job.id, "error_message": error_message},
                    )
                connection.commit()

    def _update_status(self, job_id: str, status: str) -> None:
        if status == "succeeded":
            statement = """
                UPDATE background_jobs
                SET status = %(status)s,
                    completed_at = NOW(),
                    failed_at = NULL,
                    locked_at = NULL,
                    locked_by = NULL,
                    updated_at = NOW()
                WHERE id = %(job_id)s
                """
        else:
            statement = """
                UPDATE background_jobs
                SET status = %(status)s,
                    locked_at = NULL,
                    locked_by = NULL,
                    updated_at = NOW()
                WHERE id = %(job_id)s
                """
        with psycopg.connect(self.settings.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, {"job_id": job_id, "status": status})
                connection.commit()


class DerivedWriteRepository:
    def __init__(self) -> None:
        self.settings = get_settings()

    def append_job_note(self, job_id: str, note: str) -> None:
        payload = json.dumps(
            {
                "jobId": job_id,
                "note": note,
                "recordedAt": datetime.now(UTC).isoformat(),
            }
        )
        with psycopg.connect(self.settings.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO audit_logs (
                        id,
                        entity_type,
                        entity_id,
                        action,
                        metadata,
                        created_at
                    )
                    VALUES (
                        md5(random()::text || clock_timestamp()::text),
                        'background_job',
                        %(job_id)s,
                        'worker.note',
                        %(payload)s::jsonb,
                        NOW()
                    )
                    """,
                    {"job_id": job_id, "payload": payload},
                )
                connection.commit()
