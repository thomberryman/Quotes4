from __future__ import annotations

import logging
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.queue import DerivedWriteRepository, PostgresJobQueue
from app.jobs.registry import REGISTERED_JOBS, jobs_by_queue_name

configure_logging()
logger = logging.getLogger(__name__)


def run_once() -> bool:
    queue = PostgresJobQueue()
    repository = DerivedWriteRepository()
    registry = jobs_by_queue_name()
    job = queue.reserve_next_job(list(registry))
    if job is None:
        logger.info("worker_idle")
        return False

    handler = registry[job.queue_name]
    logger.info(
        "worker_job_started",
        extra={"job_id": job.id, "queue_name": job.queue_name, "job_name": handler.name},
    )
    try:
        handler.handler(job, repository)
    except Exception as exc:
        logger.exception(
            "worker_job_failed",
            extra={"job_id": job.id, "queue_name": job.queue_name},
        )
        queue.mark_failed(
            job,
            str(exc),
            retry_backoff_seconds=handler.retry_backoff_seconds,
        )
        return True

    queue.mark_succeeded(job.id)
    logger.info("worker_job_succeeded", extra={"job_id": job.id, "queue_name": job.queue_name})
    return True


def bootstrap() -> None:
    settings = get_settings()
    logger.info("worker_starting", extra={"worker_name": settings.worker_name})

    for job in REGISTERED_JOBS:
        logger.info(
            "worker_job_registered",
            extra={"queue_name": job.queue_name, "job_name": job.name},
        )

    if not settings.run_forever:
        run_once()
        return

    while True:
        ran_job = run_once()
        if not ran_job:
            time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    bootstrap()
