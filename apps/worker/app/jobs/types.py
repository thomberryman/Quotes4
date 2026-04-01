from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.core.queue import DerivedWriteRepository, QueuedJob

JobHandler = Callable[[QueuedJob, DerivedWriteRepository], None]


@dataclass(frozen=True)
class WorkerJob:
    name: str
    description: str
    queue_name: str
    retry_backoff_seconds: int
    handler: JobHandler
