from __future__ import annotations

from datetime import UTC, datetime


def coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def same_timestamp(left: datetime, right: datetime) -> bool:
    return coerce_utc(left) == coerce_utc(right)
