from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentifierMixin, JsonObjectType, TimestampMixin

if TYPE_CHECKING:
    from app.models.forecasts import ForecastVersion
    from app.models.projects import Project
    from app.models.quotes import QuoteVersion


class PredictionRun(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "prediction_runs"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    quote_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("quote_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    forecast_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("forecast_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_version: Mapped[str] = mapped_column(String(100))
    strategy_key: Mapped[str] = mapped_column(String(100))
    maturity_stage: Mapped[str] = mapped_column(String(50))
    primary_evidence_source: Mapped[str] = mapped_column(String(100))
    fallback_tier: Mapped[str] = mapped_column(String(100))
    feature_readiness_score: Mapped[float] = mapped_column(Numeric(5, 2))
    data_sufficiency_score: Mapped[float] = mapped_column(Numeric(5, 2))
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2))
    confidence_label: Mapped[str] = mapped_column(String(32))
    missing_critical_inputs_json: Mapped[list[str]] = mapped_column(
        "missing_critical_inputs",
        JsonObjectType,
        default=list,
    )
    request_context_json: Mapped[dict[str, object]] = mapped_column(
        "request_context",
        JsonObjectType,
        default=dict,
    )
    source_references_json: Mapped[list[dict[str, object]]] = mapped_column(
        "source_references",
        JsonObjectType,
        default=list,
    )
    feature_snapshot_json: Mapped[dict[str, object]] = mapped_column(
        "feature_snapshot",
        JsonObjectType,
        default=dict,
    )
    methodology_summary: Mapped[str] = mapped_column(Text())
    expected_scenario_key: Mapped[str] = mapped_column(String(32), default="base")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="prediction_runs")
    quote_version: Mapped[QuoteVersion | None] = relationship(
        foreign_keys=[quote_version_id],
        overlaps="prediction_runs",
    )
    forecast_version: Mapped[ForecastVersion | None] = relationship(foreign_keys=[forecast_version_id])
    module_outputs: Mapped[list[PredictionModuleOutput]] = relationship(
        back_populates="prediction_run",
        cascade="all, delete-orphan",
    )
    comparables: Mapped[list[PredictionRunComparable]] = relationship(
        back_populates="prediction_run",
        cascade="all, delete-orphan",
    )
    scenarios: Mapped[list[PredictionScenario]] = relationship(
        back_populates="prediction_run",
        cascade="all, delete-orphan",
    )
    overrides: Mapped[list[PredictionOverride]] = relationship(
        back_populates="prediction_run",
        cascade="all, delete-orphan",
    )
    evaluations: Mapped[list[PredictionEvaluation]] = relationship(
        back_populates="prediction_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_prediction_runs_project_generated_at", "project_id", "generated_at"),
        Index("ix_prediction_runs_project_expected_scenario", "project_id", "expected_scenario_key"),
    )


class PredictionModuleOutput(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "prediction_module_outputs"

    prediction_run_id: Mapped[str] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="CASCADE")
    )
    module_key: Mapped[str] = mapped_column(String(100))
    model_module: Mapped[str] = mapped_column(String(150))
    fallback_tier: Mapped[str] = mapped_column(String(100))
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2))
    data_sufficiency_score: Mapped[float] = mapped_column(Numeric(5, 2))
    confidence_label: Mapped[str] = mapped_column(String(32))
    output_json: Mapped[dict[str, object]] = mapped_column(JsonObjectType, default=dict)
    explanation_json: Mapped[list[dict[str, object]]] = mapped_column(
        JsonObjectType,
        default=list,
    )
    warning_codes_json: Mapped[list[str]] = mapped_column(JsonObjectType, default=list)

    prediction_run: Mapped[PredictionRun] = relationship(back_populates="module_outputs")

    __table_args__ = (
        Index(
            "ix_prediction_module_outputs_run_module",
            "prediction_run_id",
            "module_key",
            unique=True,
        ),
    )


class PredictionRunComparable(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "prediction_run_comparables"

    prediction_run_id: Mapped[str] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="CASCADE")
    )
    comparable_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    comparable_project_name: Mapped[str] = mapped_column(String(255))
    selection_state: Mapped[str] = mapped_column(String(32), default="auto")
    similarity_score: Mapped[float] = mapped_column(Numeric(5, 2))
    strength: Mapped[str] = mapped_column(String(32))
    is_primary: Mapped[bool] = mapped_column(Boolean(), default=False)
    sort_order: Mapped[int] = mapped_column()
    evidence_json: Mapped[list[dict[str, object]]] = mapped_column(JsonObjectType, default=list)

    prediction_run: Mapped[PredictionRun] = relationship(back_populates="comparables")

    __table_args__ = (
        Index(
            "ix_prediction_run_comparables_run_sort_order",
            "prediction_run_id",
            "sort_order",
            unique=True,
        ),
        Index(
            "ix_prediction_run_comparables_run_project",
            "prediction_run_id",
            "comparable_project_id",
        ),
    )


class PredictionScenario(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "prediction_scenarios"

    prediction_run_id: Mapped[str] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="CASCADE")
    )
    scenario_key: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(100))
    is_expected: Mapped[bool] = mapped_column(Boolean(), default=False)
    assumption_overrides_json: Mapped[dict[str, object]] = mapped_column(
        "assumption_overrides",
        JsonObjectType,
        default=dict,
    )
    output_json: Mapped[dict[str, object]] = mapped_column(JsonObjectType, default=dict)
    promoted_forecast_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("forecast_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    prediction_run: Mapped[PredictionRun] = relationship(back_populates="scenarios")
    promoted_forecast_version: Mapped[ForecastVersion | None] = relationship(
        foreign_keys=[promoted_forecast_version_id]
    )

    __table_args__ = (
        Index(
            "ix_prediction_scenarios_run_key",
            "prediction_run_id",
            "scenario_key",
            unique=True,
        ),
    )


class PredictionOverride(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "prediction_overrides"

    prediction_run_id: Mapped[str] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="CASCADE")
    )
    module_key: Mapped[str] = mapped_column(String(100))
    scenario_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32))
    override_value_json: Mapped[dict[str, object] | None] = mapped_column(
        JsonObjectType,
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    prediction_run: Mapped[PredictionRun] = relationship(back_populates="overrides")

    __table_args__ = (
        Index("ix_prediction_overrides_run_module", "prediction_run_id", "module_key"),
        Index("ix_prediction_overrides_run_target", "prediction_run_id", "target_key"),
    )


class PredictionEvaluation(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "prediction_evaluations"

    prediction_run_id: Mapped[str] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="CASCADE")
    )
    module_key: Mapped[str] = mapped_column(String(100))
    scenario_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metric_key: Mapped[str] = mapped_column(String(100))
    predicted_value_json: Mapped[dict[str, object] | None] = mapped_column(
        JsonObjectType,
        nullable=True,
    )
    actual_value_json: Mapped[dict[str, object] | None] = mapped_column(
        JsonObjectType,
        nullable=True,
    )
    error_value: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    calibration_bucket: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    outcome_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    prediction_run: Mapped[PredictionRun] = relationship(back_populates="evaluations")

    __table_args__ = (
        Index(
            "ix_prediction_evaluations_run_metric",
            "prediction_run_id",
            "metric_key",
        ),
    )
