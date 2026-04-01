from __future__ import annotations

from app.core.queue import QueuedJob
from app.jobs.forecast_recalc import handle_forecast_recalc


class NoteRepository:
    def __init__(self) -> None:
        self.notes: list[tuple[str, str]] = []

    def append_job_note(self, job_id: str, note: str) -> None:
        self.notes.append((job_id, note))


def test_forecast_recalc_job_appends_project_note() -> None:
    repository = NoteRepository()
    job = QueuedJob(
        id="job-forecast-1",
        queue_name="forecast_recalc",
        payload={"projectId": "project-123"},
        attempts=1,
        max_attempts=5,
    )

    handle_forecast_recalc(job, repository)

    assert repository.notes == [
        (
            "job-forecast-1",
            "Recalculated forecast snapshots for project project-123.",
        )
    ]
