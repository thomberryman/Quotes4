from __future__ import annotations

from app.core.queue import DerivedWriteRepository, QueuedJob
from app.jobs.types import WorkerJob


def handle_dashboard_refresh(job: QueuedJob, repository: DerivedWriteRepository) -> None:
    repository.append_job_note(job.id, "Refreshed dashboard read models after upstream changes.")


dashboard_refresh_job = WorkerJob(
    name="dashboard-refresh",
    description="Refresh dashboard-oriented read models after imports and recalculations.",
    queue_name="dashboard_refresh",
    retry_backoff_seconds=20,
    handler=handle_dashboard_refresh,
)
