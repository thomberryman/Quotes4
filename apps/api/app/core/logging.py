from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app.core.request_context import get_request_id


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["requestId"] = request_id

        if hasattr(record, "user_id"):
            payload["userId"] = record.user_id
        if hasattr(record, "job_id"):
            payload["jobId"] = record.job_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if any(isinstance(handler.formatter, JsonLogFormatter) for handler in root_logger.handlers):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)
