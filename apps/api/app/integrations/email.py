from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutboundEmail:
    to_address: str
    subject: str
    body: str


class Mailer:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send(self, message: OutboundEmail) -> None:
        logger.info(
            "sending_email",
            extra={
                "to_address": message.to_address,
                "subject": message.subject,
                "mailer_mode": self.settings.mailer_mode,
            },
        )


mailer = Mailer()
