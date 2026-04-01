from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentifierMixin, JsonObjectType, TimestampMixin
from app.models.enums import BenchmarkActualsStatus, ComparableProjectLinkDisposition

if TYPE_CHECKING:
    from app.models.projects import Project
    from app.models.quotes import QuoteVersion
    from app.models.reference import Discipline


class ComparableProjectLink(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "comparable_project_links"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    comparable_project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    disposition: Mapped[ComparableProjectLinkDisposition] = mapped_column(
        SqlEnum(
            ComparableProjectLinkDisposition,
            name="comparable_project_link_disposition",
            native_enum=False,
            length=32,
        )
    )
    score: Mapped[float] = mapped_column(Numeric(5, 2))
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    scoring_model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reasons_json: Mapped[dict[str, object] | None] = mapped_column(
        "reasons", JsonObjectType, nullable=True
    )

    project: Mapped[Project] = relationship(
        back_populates="comparable_source_links",
        foreign_keys=[project_id],
    )
    comparable_project: Mapped[Project] = relationship(
        back_populates="comparable_target_links",
        foreign_keys=[comparable_project_id],
    )

    __table_args__ = (
        Index(
            "ix_comparable_project_links_project_disposition",
            "project_id",
            "disposition",
        ),
        Index(
            "ix_comparable_project_links_project_comparable",
            "project_id",
            "comparable_project_id",
            unique=True,
        ),
    )


class ProjectBenchmarkSummary(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "project_benchmark_summaries"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    source_quote_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("quote_versions.id", ondelete="SET NULL"), nullable=True
    )
    currency_code: Mapped[str] = mapped_column(String(3))
    quoted_amount: Mapped[float] = mapped_column(Numeric(14, 2))
    actual_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    quote_to_actual_variance_amount: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    quote_to_actual_variance_pct: Mapped[float | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    actuals_status: Mapped[BenchmarkActualsStatus] = mapped_column(
        SqlEnum(
            BenchmarkActualsStatus,
            name="benchmark_actuals_status",
            native_enum=False,
            length=32,
        ),
        default=BenchmarkActualsStatus.none,
    )
    actuals_as_of_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    project: Mapped[Project] = relationship(back_populates="benchmark_summary")
    source_quote_version: Mapped[QuoteVersion | None] = relationship(
        back_populates="benchmark_summaries"
    )
    discipline_summaries: Mapped[list[ProjectBenchmarkDisciplineSummary]] = relationship(
        back_populates="benchmark_summary",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_project_benchmark_summaries_actuals_status_generated_at",
            "actuals_status",
            "generated_at",
        ),
    )


class ProjectBenchmarkDisciplineSummary(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "project_benchmark_discipline_summaries"

    benchmark_summary_id: Mapped[str] = mapped_column(
        ForeignKey("project_benchmark_summaries.id", ondelete="CASCADE")
    )
    discipline_id: Mapped[str] = mapped_column(
        ForeignKey("disciplines.id", ondelete="RESTRICT")
    )
    quoted_amount: Mapped[float] = mapped_column(Numeric(14, 2))
    actual_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    quote_to_actual_variance_amount: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    quote_to_actual_variance_pct: Mapped[float | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    actuals_status: Mapped[BenchmarkActualsStatus] = mapped_column(
        SqlEnum(
            BenchmarkActualsStatus,
            name="benchmark_actuals_status",
            native_enum=False,
            length=32,
        ),
        default=BenchmarkActualsStatus.none,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )

    benchmark_summary: Mapped[ProjectBenchmarkSummary] = relationship(
        back_populates="discipline_summaries"
    )
    discipline: Mapped[Discipline] = relationship(back_populates="benchmark_summaries")

    __table_args__ = (
        Index(
            "ix_project_benchmark_discipline_summaries_benchmark_discipline",
            "benchmark_summary_id",
            "discipline_id",
            unique=True,
        ),
        Index(
            "ix_pbds_discipline_actuals_status",
            "discipline_id",
            "actuals_status",
        ),
    )
