from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from typing import Any

from app.modules.comparables.service import _float, _round, _weighted_percentile


def to_cents(amount: float) -> int:
    return round(amount * 100)


def from_cents(amount_in_cents: int) -> float:
    return amount_in_cents / 100


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def month_date(month: str) -> date:
    year_text, month_text = month.split("-", maxsplit=1)
    return date(int(year_text), int(month_text), 1)


def first_day_next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def last_day_of_month(value: date) -> date:
    return first_day_next_month(value) - timedelta(days=1)


def diff_days_inclusive(start_date: date, end_date: date) -> int:
    return (end_date - start_date).days + 1


def month_starts_between(start_date: date, end_date: date) -> list[date]:
    current = date(start_date.year, start_date.month, 1)
    months: list[date] = []
    while current <= end_date:
        months.append(current)
        current = first_day_next_month(current)
    return months


def confidence_label(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def weighted_band(values: list[dict[str, float | str]]) -> dict[str, Any] | None:
    if len(values) < 3:
        return None
    if len(values) < 5:
        sorted_values = sorted(values, key=lambda item: float(item["value"]))
        return {
            "low": _round(float(sorted_values[0]["value"])),
            "median": _weighted_percentile(values, 0.5),
            "high": _round(float(sorted_values[-1]["value"])),
            "sampleSize": len(values),
            "comparableProjectIds": [str(value["projectId"]) for value in values],
            "methodology": "min_median_max",
        }
    return {
        "low": _weighted_percentile(values, 0.25),
        "median": _weighted_percentile(values, 0.5),
        "high": _weighted_percentile(values, 0.75),
        "sampleSize": len(values),
        "comparableProjectIds": [str(value["projectId"]) for value in values],
        "methodology": "weighted_percentiles",
    }


def normalize_share_bands(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for key in ("lowSharePct", "medianSharePct", "highSharePct"):
        total = sum(float(row[key]) for row in rows)
        if total <= 0:
            continue
        normalized_total = 0.0
        for row in rows:
            row[key] = _round((float(row[key]) / total) * 100)
            normalized_total += float(row[key])
        delta = _round(100 - normalized_total)
        if abs(delta) >= 0.01 and rows:
            rows[-1][key] = _round(float(rows[-1][key]) + delta)
    return rows


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def classify_budget_band(amount: float | None) -> str | None:
    if amount is None or amount <= 0:
        return None
    if amount < 50000:
        return "lt_50k"
    if amount < 100000:
        return "50k_100k"
    if amount < 250000:
        return "100k_250k"
    return "250k_plus"


def month_count(start_date: date | None, end_date: date | None, fallback_weeks: int | None = None) -> int | None:
    if start_date is not None and end_date is not None and end_date >= start_date:
        return len(month_starts_between(start_date, end_date))
    if fallback_weeks is not None and fallback_weeks > 0:
        return max(1, ceil(fallback_weeks / 4))
    return None


def amount_or_none(value: Any) -> float | None:
    amount = _float(value)
    if amount is None:
        return None
    return float(amount)
