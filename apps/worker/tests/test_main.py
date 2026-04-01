from __future__ import annotations

from app import main as worker_main
from app.core.queue import QueuedJob
from app.jobs.types import WorkerJob


class StubQueue:
    def __init__(self, job: QueuedJob | None) -> None:
        self.job = job
        self.failed: tuple[QueuedJob, str, int] | None = None
        self.succeeded_job_id: str | None = None

    def reserve_next_job(self, queue_names: list[str]) -> QueuedJob | None:
        return self.job

    def mark_failed(
        self,
        job: QueuedJob,
        error_message: str,
        *,
        retry_backoff_seconds: int,
    ) -> None:
        self.failed = (job, error_message, retry_backoff_seconds)

    def mark_succeeded(self, job_id: str) -> None:
        self.succeeded_job_id = job_id


class StubRepository:
    pass


def test_run_once_requeues_failed_jobs(monkeypatch) -> None:
    queued_job = QueuedJob(
        id="job-1",
        queue_name="forecast_recalc",
        payload={"projectId": "project-1"},
        attempts=1,
        max_attempts=3,
    )
    queue = StubQueue(queued_job)
    def fail_handler(_job: QueuedJob, _repository: StubRepository) -> None:
        raise RuntimeError("boom")

    handler = WorkerJob(
        name="forecast-recalc",
        description="Recalculate forecast data.",
        queue_name="forecast_recalc",
        retry_backoff_seconds=45,
        handler=fail_handler,
    )

    monkeypatch.setattr(worker_main, "PostgresJobQueue", lambda: queue)
    monkeypatch.setattr(worker_main, "DerivedWriteRepository", lambda: StubRepository())
    monkeypatch.setattr(worker_main, "jobs_by_queue_name", lambda: {"forecast_recalc": handler})

    assert worker_main.run_once() is True
    assert queue.failed is not None
    failed_job, error_message, retry_backoff_seconds = queue.failed
    assert failed_job.id == "job-1"
    assert error_message == "boom"
    assert retry_backoff_seconds == 45
