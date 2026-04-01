from __future__ import annotations

from app.jobs.ceta_import import ceta_import_job
from app.jobs.comparables_refresh import comparables_refresh_job
from app.jobs.dashboard_refresh import dashboard_refresh_job
from app.jobs.forecast_recalc import forecast_recalc_job
from app.jobs.notifications import notifications_job
from app.jobs.pdf_parse import pdf_parse_job
from app.jobs.types import WorkerJob

REGISTERED_JOBS: tuple[WorkerJob, ...] = (
    pdf_parse_job,
    ceta_import_job,
    forecast_recalc_job,
    comparables_refresh_job,
    dashboard_refresh_job,
    notifications_job,
)


def jobs_by_queue_name() -> dict[str, WorkerJob]:
    return {job.queue_name: job for job in REGISTERED_JOBS}
