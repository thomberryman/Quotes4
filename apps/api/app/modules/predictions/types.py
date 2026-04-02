from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models import ForecastVersion, Project, ProjectScheduleRange, QuoteLineItem, QuoteVersion


@dataclass
class ActualsSummary:
    current_revenue_total: float = 0.0
    current_cost_total: float = 0.0
    monthly_revenue: dict[str, float] = field(default_factory=dict)
    monthly_costs: dict[str, float] = field(default_factory=dict)
    discipline_revenue: dict[str, float] = field(default_factory=dict)
    discipline_costs: dict[str, float] = field(default_factory=dict)
    third_party_cost_share_pct: float | None = None
    current_month_count: int = 0


@dataclass
class PredictionContext:
    project: Project
    target_snapshot: dict[str, Any]
    target_quote_version: QuoteVersion | None
    current_forecast_version: ForecastVersion | None
    comparable_items: list[dict[str, Any]]
    eligible_items: list[dict[str, Any]]
    projects_by_id: dict[str, Project]
    quote_line_items: list[QuoteLineItem]
    schedule_ranges: list[ProjectScheduleRange]
    actuals: ActualsSummary
    project_actuals_by_project_id: dict[str, ActualsSummary]
    request_context: dict[str, Any]


@dataclass
class PredictionModuleResult:
    module_key: str
    model_module: str
    fallback_tier: str
    confidence_score: float
    data_sufficiency_score: float
    confidence_label: str
    output: dict[str, Any]
    explanations: list[dict[str, Any]] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)
