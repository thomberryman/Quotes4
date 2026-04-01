from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, desc, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.schemas import BaseSchema
from app.models import BackgroundJob
from app.models.base import generate_id
from app.models.enums import BackgroundJobStatus

ACTIVE_JOB_STATUSES = (BackgroundJobStatus.queued, BackgroundJobStatus.running)


@dataclass(frozen=True)
class JobListFilters:
    status: BackgroundJobStatus | None = None
    queue_name: str | None = None
    related_entity_type: str | None = None
    related_entity_id: str | None = None


class JobRecord(BaseSchema):
    id: str
    queue_name: str
    status: BackgroundJobStatus
    attempts: int
    max_attempts: int
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    payload: dict[str, object]
    available_at: datetime
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    last_error: str | None = None


class JobStatusCounts(BaseSchema):
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0


class FailingQueueSummary(BaseSchema):
    queue_name: str
    failed_count: int
    latest_failed_at: datetime | None = None


class JobListSummary(BaseSchema):
    total_count: int
    counts: JobStatusCounts
    recent_failed_count: int
    failing_queues: list[FailingQueueSummary]


class JobService:
    def enqueue(
        self,
        session: Session,
        *,
        queue_name: str,
        payload: dict[str, object],
        related_entity_type: str | None = None,
        related_entity_id: str | None = None,
        deduplication_key: str | None = None,
    ) -> JobRecord:
        if deduplication_key:
            existing = self._find_active_job_by_deduplication_key(session, deduplication_key)
            if existing is not None:
                return self._serialize(existing)

        now = datetime.now(UTC)
        job_id = generate_id()
        values = {
            "id": job_id,
            "queue_name": queue_name,
            "status": BackgroundJobStatus.queued,
            "deduplication_key": deduplication_key,
            "payload_json": payload,
            "related_entity_type": related_entity_type,
            "related_entity_id": related_entity_id,
            "attempts": 0,
            "max_attempts": 5,
            "available_at": now,
            "created_at": now,
            "updated_at": now,
        }

        try:
            with session.no_autoflush:
                if deduplication_key:
                    nested = session.connection().begin_nested()
                    try:
                        session.execute(insert(BackgroundJob).values(**values))
                    except IntegrityError:
                        nested.rollback()
                        existing = self._find_active_job_by_deduplication_key(
                            session, deduplication_key
                        )
                        if existing is not None:
                            return self._serialize(existing)
                        raise
                    else:
                        nested.commit()
                else:
                    session.execute(insert(BackgroundJob).values(**values))
        except IntegrityError:
            if deduplication_key is not None:
                existing = self._find_active_job_by_deduplication_key(session, deduplication_key)
                if existing is not None:
                    return self._serialize(existing)
            raise

        job = session.get(BackgroundJob, job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' was not found after creation.")
        return self._serialize(job)

    def get(self, session: Session, job_id: str) -> JobRecord | None:
        job = session.get(BackgroundJob, job_id)
        return self._serialize(job) if job is not None else None

    def get_related_job(
        self,
        session: Session,
        job_id: str,
        *,
        related_entity_type: str,
        related_entity_id: str,
        queue_name: str | None = None,
    ) -> JobRecord | None:
        job = session.get(BackgroundJob, job_id)
        if job is None:
            return None
        if (
            job.related_entity_type != related_entity_type
            or job.related_entity_id != related_entity_id
        ):
            return None
        if queue_name is not None and job.queue_name != queue_name:
            return None
        return self._serialize(job)

    def list(
        self,
        session: Session,
        *,
        filters: JobListFilters | None = None,
        limit: int = 100,
    ) -> list[JobRecord]:
        statement = (
            self._apply_filters(select(BackgroundJob), filters)
            .order_by(desc(BackgroundJob.created_at))
            .limit(limit)
        )
        jobs = list(session.scalars(statement))
        return [self._serialize(job) for job in jobs]

    def summarize(
        self,
        session: Session,
        *,
        filters: JobListFilters | None = None,
    ) -> JobListSummary:
        status_counts = JobStatusCounts()
        status_rows = session.execute(
            self._apply_filters(
                select(BackgroundJob.status, func.count(BackgroundJob.id)),
                filters,
            ).group_by(BackgroundJob.status)
        ).all()
        total_count = 0
        for status, count in status_rows:
            total_count += int(count)
            if status == BackgroundJobStatus.queued:
                status_counts.queued = int(count)
            elif status == BackgroundJobStatus.running:
                status_counts.running = int(count)
            elif status == BackgroundJobStatus.succeeded:
                status_counts.succeeded = int(count)
            elif status == BackgroundJobStatus.failed:
                status_counts.failed = int(count)

        recent_failure_threshold = datetime.now(UTC) - timedelta(hours=24)
        recent_failed_count = session.scalar(
            self._apply_filters(
                select(func.count(BackgroundJob.id)).where(
                    BackgroundJob.status == BackgroundJobStatus.failed,
                    BackgroundJob.failed_at.is_not(None),
                    BackgroundJob.failed_at >= recent_failure_threshold,
                ),
                filters,
            )
        )

        failing_queue_rows = session.execute(
            self._apply_filters(
                select(
                    BackgroundJob.queue_name,
                    func.count(BackgroundJob.id),
                    func.max(BackgroundJob.failed_at),
                ).where(BackgroundJob.status == BackgroundJobStatus.failed),
                filters,
            )
            .group_by(BackgroundJob.queue_name)
            .order_by(desc(func.count(BackgroundJob.id)), desc(func.max(BackgroundJob.failed_at)))
            .limit(5)
        ).all()

        return JobListSummary(
            total_count=total_count,
            counts=status_counts,
            recent_failed_count=int(recent_failed_count or 0),
            failing_queues=[
                FailingQueueSummary(
                    queue_name=str(queue_name),
                    failed_count=int(failed_count),
                    latest_failed_at=latest_failed_at,
                )
                for queue_name, failed_count, latest_failed_at in failing_queue_rows
            ],
        )

    def mark_running(self, session: Session, job_id: str) -> JobRecord:
        job = self._get_job_entity(session, job_id)
        job.status = BackgroundJobStatus.running
        job.last_error = None
        session.flush()
        return self._serialize(job)

    def mark_succeeded(self, session: Session, job_id: str) -> JobRecord:
        job = self._get_job_entity(session, job_id)
        job.status = BackgroundJobStatus.succeeded
        job.completed_at = datetime.now(UTC)
        job.failed_at = None
        job.last_error = None
        job.locked_at = None
        job.locked_by = None
        session.flush()
        return self._serialize(job)

    def mark_failed(
        self,
        session: Session,
        job_id: str,
        *,
        last_error: str | None = None,
    ) -> JobRecord:
        job = self._get_job_entity(session, job_id)
        job.status = BackgroundJobStatus.failed
        job.failed_at = datetime.now(UTC)
        job.completed_at = None
        job.last_error = last_error
        job.locked_at = None
        job.locked_by = None
        session.flush()
        return self._serialize(job)

    def build_deduplication_key(
        self,
        *,
        queue_name: str,
        related_entity_type: str | None,
        related_entity_id: str | None,
    ) -> str | None:
        if related_entity_type is None or related_entity_id is None:
            return None
        return f"{queue_name}:{related_entity_type}:{related_entity_id}"

    def _serialize(self, job: BackgroundJob) -> JobRecord:
        return JobRecord(
            id=job.id,
            queue_name=job.queue_name,
            status=job.status,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            related_entity_type=job.related_entity_type,
            related_entity_id=job.related_entity_id,
            payload=job.payload_json,
            available_at=job.available_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
            failed_at=job.failed_at,
            last_error=job.last_error,
        )

    def _get_job_entity(self, session: Session, job_id: str) -> BackgroundJob:
        job = session.get(BackgroundJob, job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' was not found.")
        return job

    def _find_active_job_by_deduplication_key(
        self,
        session: Session,
        deduplication_key: str,
    ) -> BackgroundJob | None:
        statement = (
            select(BackgroundJob)
            .where(
                BackgroundJob.deduplication_key == deduplication_key,
                BackgroundJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(desc(BackgroundJob.created_at))
            .limit(1)
        )
        return session.scalar(statement)

    def _apply_filters(
        self,
        statement: Select[Any],
        filters: JobListFilters | None,
    ) -> Select[Any]:
        if filters is None:
            return statement
        if filters.status is not None:
            statement = statement.where(BackgroundJob.status == filters.status)
        if filters.queue_name is not None:
            statement = statement.where(BackgroundJob.queue_name == filters.queue_name)
        if filters.related_entity_type is not None:
            statement = statement.where(
                BackgroundJob.related_entity_type == filters.related_entity_type
            )
        if filters.related_entity_id is not None:
            statement = statement.where(
                BackgroundJob.related_entity_id == filters.related_entity_id
            )
        return statement


job_service = JobService()
