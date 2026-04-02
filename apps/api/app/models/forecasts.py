from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentifierMixin, JsonObjectType, TimestampMixin
from app.models.enums import ForecastAllocationMethod, ForecastVersionStatus, ProjectOutcomeType

if TYPE_CHECKING:
    from app.models.auth import User
    from app.models.projects import Project, ProjectScheduleRange
    from app.models.quotes import QuoteLineItem, QuoteVersion
    from app.models.reference import Discipline


class Forecast(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "forecasts"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    current_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    project: Mapped[Project] = relationship(back_populates="forecast")
    versions: Mapped[list[ForecastVersion]] = relationship(
        back_populates="forecast",
        foreign_keys="ForecastVersion.forecast_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["forecast_versions.forecast_id", "forecast_versions.id"],
            name="fk_forecasts_current_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_forecasts_id_current_version_id", "id", "current_version_id", unique=True),
    )


class ForecastVersion(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "forecast_versions"

    forecast_id: Mapped[str] = mapped_column(ForeignKey("forecasts.id", ondelete="CASCADE"))
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("forecast_versions.id", ondelete="SET NULL"), nullable=True
    )
    version_number: Mapped[int] = mapped_column()
    status: Mapped[ForecastVersionStatus] = mapped_column(
        SqlEnum(
            ForecastVersionStatus,
            name="forecast_version_status",
            native_enum=False,
            length=32,
        ),
        default=ForecastVersionStatus.draft,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    outcome_type_snapshot: Mapped[ProjectOutcomeType] = mapped_column(
        SqlEnum(
            ProjectOutcomeType,
            name="forecast_outcome_type_snapshot",
            native_enum=False,
            length=32,
        ),
        default=ProjectOutcomeType.bid,
    )
    probability_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=100)
    source_quote_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("quote_versions.id", ondelete="SET NULL"), nullable=True
    )
    revision_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    scenario_key: Mapped[str] = mapped_column(String(32), default="base")
    engine_source: Mapped[str] = mapped_column(String(100), default="unified_forecast_engine")
    prediction_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    prediction_scenario_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    data_sufficiency_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    fallback_tier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    explanation_summary_json: Mapped[dict[str, object] | None] = mapped_column(
        "explanation_summary",
        JsonObjectType,
        nullable=True,
    )
    change_summary_json: Mapped[dict[str, object] | None] = mapped_column(
        "change_summary",
        JsonObjectType,
        nullable=True,
    )
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    locked_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    forecast: Mapped[Forecast] = relationship(back_populates="versions", foreign_keys=[forecast_id])
    parent_version: Mapped[ForecastVersion | None] = relationship(
        remote_side="ForecastVersion.id", back_populates="child_versions"
    )
    child_versions: Mapped[list[ForecastVersion]] = relationship(back_populates="parent_version")
    source_quote_version: Mapped[QuoteVersion | None] = relationship(
        back_populates="forecast_versions"
    )
    lines: Mapped[list[ForecastLine]] = relationship(
        back_populates="forecast_version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_forecast_versions_status_created_at", "status", "created_at"),
        Index(
            "ix_forecast_versions_outcome_type_snapshot_created_at",
            "outcome_type_snapshot",
            "created_at",
        ),
        Index(
            "ix_forecast_versions_forecast_version_number",
            "forecast_id",
            "version_number",
            unique=True,
        ),
        Index("ix_forecast_versions_forecast_id_id", "forecast_id", "id", unique=True),
    )


class ForecastLine(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "forecast_lines"

    forecast_version_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_versions.id", ondelete="CASCADE")
    )
    sort_order: Mapped[int] = mapped_column()
    discipline_id: Mapped[str | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="SET NULL"), nullable=True
    )
    source_quote_line_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("quote_line_items.id", ondelete="SET NULL"), nullable=True
    )
    schedule_range_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_schedule_ranges.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(255))
    allocation_method: Mapped[ForecastAllocationMethod] = mapped_column(
        SqlEnum(
            ForecastAllocationMethod,
            name="forecast_allocation_method",
            native_enum=False,
            length=32,
        )
    )
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2))
    currency_code: Mapped[str] = mapped_column(String(3))
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    forecast_method_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allocation_profile_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sequencing_template_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sequencing_stage_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overlap_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    data_sufficiency_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    fallback_tier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actuals_to_date_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    remaining_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    forecast_inputs_json: Mapped[dict[str, object] | None] = mapped_column(
        "forecast_inputs",
        JsonObjectType,
        nullable=True,
    )
    explanation_json: Mapped[list[dict[str, object]] | None] = mapped_column(
        JsonObjectType,
        nullable=True,
    )

    forecast_version: Mapped[ForecastVersion] = relationship(back_populates="lines")
    discipline: Mapped[Discipline | None] = relationship(back_populates="forecast_lines")
    source_quote_line_item: Mapped[QuoteLineItem | None] = relationship(
        back_populates="forecast_lines"
    )
    schedule_range: Mapped[ProjectScheduleRange | None] = relationship(
        back_populates="forecast_lines"
    )
    allocations: Mapped[list[MonthlyForecastAllocation]] = relationship(
        back_populates="forecast_line", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_forecast_lines_discipline_id", "discipline_id"),
        Index(
            "ix_forecast_lines_forecast_version_sort_order",
            "forecast_version_id",
            "sort_order",
            unique=True,
        ),
    )


class MonthlyForecastAllocation(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "monthly_forecast_allocations"

    forecast_line_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_lines.id", ondelete="CASCADE")
    )
    month: Mapped[date] = mapped_column(Date())
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    low_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    high_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    actual_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    allocation_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_context_json: Mapped[dict[str, object] | None] = mapped_column(
        "source_context",
        JsonObjectType,
        nullable=True,
    )
    is_manual_override: Mapped[bool] = mapped_column(Boolean(), default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean(), default=False)
    manual_note: Mapped[str | None] = mapped_column(Text(), nullable=True)

    forecast_line: Mapped[ForecastLine] = relationship(back_populates="allocations")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="monthly_forecast_allocation_amount_non_negative"),
        Index(
            "ix_monthly_forecast_allocations_forecast_line_month",
            "forecast_line_id",
            "month",
            unique=True,
        ),
        Index("ix_monthly_forecast_allocations_month", "month"),
    )


class ForecastPhasingChange(IdentifierMixin, Base):
    __tablename__ = "forecast_phasing_changes"

    forecast_version_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_versions.id", ondelete="CASCADE")
    )
    forecast_line_id: Mapped[str | None] = mapped_column(
        ForeignKey("forecast_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    discipline_id: Mapped[str | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    row_mode: Mapped[str] = mapped_column(String(32))
    month: Mapped[date] = mapped_column(Date())
    before_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    after_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    before_locked: Mapped[bool] = mapped_column(Boolean(), default=False)
    after_locked: Mapped[bool] = mapped_column(Boolean(), default=False)
    source_method: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_forecast_phasing_changes_project_created_at",
            "project_id",
            "created_at",
        ),
        Index(
            "ix_forecast_phasing_changes_version_month",
            "forecast_version_id",
            "month",
        ),
        Index(
            "ix_forecast_phasing_changes_line_month",
            "forecast_line_id",
            "month",
        ),
    )


class ForecastPhasingDraft(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "forecast_phasing_drafts"

    forecast_version_id: Mapped[str] = mapped_column(
        ForeignKey("forecast_versions.id", ondelete="CASCADE")
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    discipline_id: Mapped[str | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    row_mode: Mapped[str] = mapped_column(String(32))
    row_key: Mapped[str] = mapped_column(String(96))
    save_mode: Mapped[str] = mapped_column(String(16), default="replace")
    current_state_json: Mapped[dict[str, object]] = mapped_column(
        "current_state",
        JsonObjectType,
        default=dict,
    )
    past_states_json: Mapped[list[dict[str, object]]] = mapped_column(
        "past_states",
        JsonObjectType,
        default=list,
    )
    future_states_json: Mapped[list[dict[str, object]]] = mapped_column(
        "future_states",
        JsonObjectType,
        default=list,
    )

    __table_args__ = (
        Index(
            "ix_forecast_phasing_drafts_project_updated_at",
            "project_id",
            "updated_at",
        ),
        Index(
            "ix_forecast_phasing_drafts_version_row_key",
            "forecast_version_id",
            "row_key",
            unique=True,
        ),
    )
