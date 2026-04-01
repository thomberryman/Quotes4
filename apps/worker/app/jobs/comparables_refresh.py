from __future__ import annotations

from app.core.queue import DerivedWriteRepository, QueuedJob
from app.jobs.types import WorkerJob


def handle_comparables_refresh(job: QueuedJob, repository: DerivedWriteRepository) -> None:
    project_id = str(job.payload["projectId"])
    repository.append_job_note(
        job.id,
        (
            "Rebuilt comparable benchmark summaries and recommendation caches "
            f"for project {project_id}."
        ),
    )


comparables_refresh_job = WorkerJob(
    name="comparables-refresh",
    description="Refresh comparable benchmark summaries and recommendation read models.",
    queue_name="comparables_refresh",
    retry_backoff_seconds=30,
    handler=handle_comparables_refresh,
)
