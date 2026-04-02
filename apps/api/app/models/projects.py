from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentifierMixin, JsonObjectType, TimestampMixin
from app.models.enums import (
    ProjectOutcomeType,
    ProjectPartyRole,
    ProjectStatus,
    RevenueAllocationMethod,
)

if TYPE_CHECKING:
    from app.models.auth import User
    from app.models.audit import AuditLog
    from app.models.comparables import ComparableProjectLink, ProjectBenchmarkSummary
    from app.models.files import ProjectFile
    from app.models.forecasts import Forecast, ForecastLine
    from app.models.predictions import PredictionRun
    from app.models.quotes import Quote
    from app.models.reference import Company, Contact, ContactRole, Discipline, LossReason


class Project(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    code: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[ProjectStatus] = mapped_column(
        SqlEnum(ProjectStatus, name="project_status", native_enum=False, length=32),
        default=ProjectStatus.bid,
    )
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    quote_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    pipeline_stage_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bid_owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    strategic_account_flag: Mapped[bool] = mapped_column(Boolean(), default=False)
    start_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    bid_due_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    estimated_execution_start_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    estimated_execution_end_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    revenue_allocation_method: Mapped[RevenueAllocationMethod] = mapped_column(
        SqlEnum(
            RevenueAllocationMethod,
            name="revenue_allocation_method",
            native_enum=False,
            length=48,
        ),
        default=RevenueAllocationMethod.cadence_profile,
    )
    cadence_profile_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cadence_profile_data_json: Mapped[dict[str, object] | None] = mapped_column(
        "cadence_profile_data",
        JsonObjectType,
        nullable=True,
    )
    bid_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    awarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    metadata_record: Mapped[ProjectMetadata | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    parties: Mapped[list[ProjectParty]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    contacts: Mapped[list[ProjectContact]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    disciplines: Mapped[list[ProjectDiscipline]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    schedule_ranges: Mapped[list[ProjectScheduleRange]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    outcomes: Mapped[list[ProjectOutcome]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    quotes: Mapped[list[Quote]] = relationship(back_populates="project")
    files: Mapped[list[ProjectFile]] = relationship(back_populates="project")
    forecast: Mapped[Forecast | None] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    benchmark_summary: Mapped[ProjectBenchmarkSummary | None] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    bid_owner: Mapped[User | None] = relationship(foreign_keys=[bid_owner_user_id])
    comparable_source_links: Mapped[list[ComparableProjectLink]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="ComparableProjectLink.project_id",
    )
    comparable_target_links: Mapped[list[ComparableProjectLink]] = relationship(
        back_populates="comparable_project",
        foreign_keys="ComparableProjectLink.comparable_project_id",
    )
    prediction_runs: Mapped[list[PredictionRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="project")

    __table_args__ = (
        CheckConstraint(
            "estimated_execution_end_date IS NULL "
            "OR estimated_execution_start_date IS NULL "
            "OR estimated_execution_end_date >= estimated_execution_start_date",
            name="project_estimated_execution_dates",
        ),
        Index("ix_projects_status_updated_at", "status", "updated_at"),
        Index("ix_projects_created_at", "created_at"),
        Index(
            "ix_projects_estimated_execution_dates",
            "estimated_execution_start_date",
            "estimated_execution_end_date",
        ),
    )


class ProjectMetadata(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "project_metadata"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_subtype: Mapped[str | None] = mapped_column(String(100), nullable=True)
    genre: Mapped[str | None] = mapped_column(String(100), nullable=True)
    format_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    project_format_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    runtime_minutes: Mapped[int | None] = mapped_column(nullable=True)
    duration_weeks: Mapped[int | None] = mapped_column(nullable=True)
    episode_count: Mapped[int | None] = mapped_column(nullable=True)
    territory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    budget_target: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JsonObjectType, nullable=True
    )

    project: Mapped[Project] = relationship(back_populates="metadata_record")


class ProjectParty(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "project_parties"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"))
    role: Mapped[ProjectPartyRole] = mapped_column(
        SqlEnum(ProjectPartyRole, name="project_party_role", native_enum=False, length=32)
    )
    is_primary: Mapped[bool] = mapped_column(Boolean(), default=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    project: Mapped[Project] = relationship(back_populates="parties")
    company: Mapped[Company] = relationship(back_populates="project_parties")

    __table_args__ = (
        Index("ix_project_parties_project_role_primary", "project_id", "role", "is_primary"),
        Index("ix_project_parties_company_role", "company_id", "role"),
        Index(
            "ix_project_parties_project_company_role",
            "project_id",
            "company_id",
            "role",
            unique=True,
        ),
    )


class ProjectContact(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "project_contacts"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="RESTRICT"))
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    contact_role_id: Mapped[str | None] = mapped_column(
        ForeignKey("contact_roles.id", ondelete="SET NULL"), nullable=True
    )
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean(), default=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    project: Mapped[Project] = relationship(back_populates="contacts")
    contact: Mapped[Contact] = relationship(back_populates="project_links")
    company: Mapped[Company | None] = relationship(back_populates="project_contacts")
    contact_role: Mapped[ContactRole | None] = relationship(back_populates="project_uses")

    __table_args__ = (
        Index("ix_project_contacts_project_id_is_primary", "project_id", "is_primary"),
        Index("ix_project_contacts_contact_id", "contact_id"),
        Index("ix_project_contacts_company_id", "company_id"),
    )


class ProjectDiscipline(IdentifierMixin, Base):
    __tablename__ = "project_disciplines"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    discipline_id: Mapped[str] = mapped_column(
        ForeignKey("disciplines.id", ondelete="RESTRICT")
    )
    is_primary: Mapped[bool] = mapped_column(Boolean(), default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="disciplines")
    discipline: Mapped[Discipline] = relationship(back_populates="project_links")

    __table_args__ = (
        Index("ix_project_disciplines_project_id_is_primary", "project_id", "is_primary"),
        Index(
            "ix_project_disciplines_project_discipline",
            "project_id",
            "discipline_id",
            unique=True,
        ),
    )


class ProjectScheduleRange(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "project_schedule_ranges"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    discipline_id: Mapped[str | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date())
    end_date: Mapped[date] = mapped_column(Date())
    allocation_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    project: Mapped[Project] = relationship(back_populates="schedule_ranges")
    discipline: Mapped[Discipline | None] = relationship(back_populates="schedule_ranges")
    forecast_lines: Mapped[list[ForecastLine]] = relationship(back_populates="schedule_range")

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="project_schedule_range_dates"),
        Index(
            "ix_project_schedule_ranges_project_dates",
            "project_id",
            "start_date",
            "end_date",
        ),
        Index(
            "ix_project_schedule_ranges_discipline_start_date",
            "discipline_id",
            "start_date",
        ),
    )


class ProjectOutcome(IdentifierMixin, Base):
    __tablename__ = "project_outcomes"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    outcome_type: Mapped[ProjectOutcomeType] = mapped_column(
        SqlEnum(ProjectOutcomeType, name="project_outcome_type", native_enum=False, length=32)
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    competitor_company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    loss_reason_id: Mapped[str | None] = mapped_column(
        ForeignKey("loss_reasons.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    recorded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="outcomes")
    competitor_company: Mapped[Company | None] = relationship(
        back_populates="competitive_outcomes", foreign_keys=[competitor_company_id]
    )
    loss_reason: Mapped[LossReason | None] = relationship(back_populates="outcomes")

    __table_args__ = (
        Index("ix_project_outcomes_project_effective_at", "project_id", "effective_at"),
    )
