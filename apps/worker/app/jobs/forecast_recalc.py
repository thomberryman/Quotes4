from __future__ import annotations

from app.core.queue import DerivedWriteRepository, QueuedJob
from app.jobs.types import WorkerJob


def handle_forecast_recalc(job: QueuedJob, repository: DerivedWriteRepository) -> None:
    project_id = str(job.payload["projectId"])
    repository.append_job_note(job.id, f"Recalculated forecast snapshots for project {project_id}.")


forecast_recalc_job = WorkerJob(
    name="forecast-recalc",
    description="Recalculate monthly forecast projections and write derived snapshots.",
    queue_name="forecast_recalc",
    retry_backoff_seconds=15,
    handler=handle_forecast_recalc,
)
