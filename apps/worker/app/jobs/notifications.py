from __future__ import annotations

from app.core.queue import DerivedWriteRepository, QueuedJob
from app.jobs.types import WorkerJob


def handle_notifications(job: QueuedJob, repository: DerivedWriteRepository) -> None:
    repository.append_job_note(job.id, "Recorded outbound notification intent for async delivery.")


notifications_job = WorkerJob(
    name="notifications",
    description="Handle notification fan-out for invitations and workflow alerts.",
    queue_name="notifications",
    retry_backoff_seconds=60,
    handler=handle_notifications,
)
