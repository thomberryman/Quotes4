from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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
from app.models.enums import QuoteLineItemType, QuoteVersionStatus

if TYPE_CHECKING:
    from app.models.comparables import ProjectBenchmarkSummary
    from app.models.files import QuoteVersionFile
    from app.models.forecasts import ForecastLine, ForecastVersion
    from app.models.predictions import PredictionRun
    from app.models.projects import Project
    from app.models.reference import Discipline


class Quote(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "quotes"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    current_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quote_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    project: Mapped[Project] = relationship(back_populates="quotes")
    versions: Mapped[list[QuoteVersion]] = relationship(
        back_populates="quote",
        foreign_keys="QuoteVersion.quote_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["quote_versions.quote_id", "quote_versions.id"],
            name="fk_quotes_current_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_quotes_project_id_updated_at", "project_id", "updated_at"),
        Index("ix_quotes_id_current_version_id", "id", "current_version_id", unique=True),
    )


class QuoteVersion(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "quote_versions"

    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id", ondelete="CASCADE"))
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("quote_versions.id", ondelete="SET NULL"), nullable=True
    )
    version_number: Mapped[int] = mapped_column()
    status: Mapped[QuoteVersionStatus] = mapped_column(
        SqlEnum(QuoteVersionStatus, name="quote_version_status", native_enum=False, length=32),
        default=QuoteVersionStatus.draft,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3))
    valid_until: Mapped[date | None] = mapped_column(Date(), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    issued_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    client_facing_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source_document_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    source_version_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pricing_context_json: Mapped[dict[str, object] | None] = mapped_column(
        "pricing_context", JsonObjectType, nullable=True
    )
    subtotal_amount: Mapped[float] = mapped_column(Numeric(14, 2))
    tax_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2))

    quote: Mapped[Quote] = relationship(back_populates="versions", foreign_keys=[quote_id])
    parent_version: Mapped[QuoteVersion | None] = relationship(
        remote_side="QuoteVersion.id", back_populates="child_versions"
    )
    child_versions: Mapped[list[QuoteVersion]] = relationship(back_populates="parent_version")
    sections: Mapped[list[QuoteSection]] = relationship(
        back_populates="quote_version", cascade="all, delete-orphan"
    )
    files: Mapped[list[QuoteVersionFile]] = relationship(back_populates="quote_version")
    forecast_versions: Mapped[list[ForecastVersion]] = relationship(
        back_populates="source_quote_version"
    )
    benchmark_summaries: Mapped[list[ProjectBenchmarkSummary]] = relationship(
        back_populates="source_quote_version"
    )
    prediction_runs: Mapped[list[PredictionRun]] = relationship(
        foreign_keys="PredictionRun.quote_version_id",
        overlaps="quote_version",
    )

    __table_args__ = (
        Index("ix_quote_versions_status_issued_at", "status", "issued_at"),
        Index("ix_quote_versions_quote_version_number", "quote_id", "version_number", unique=True),
        Index("ix_quote_versions_quote_id_id", "quote_id", "id", unique=True),
    )


class QuoteSection(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "quote_sections"

    quote_version_id: Mapped[str] = mapped_column(
        ForeignKey("quote_versions.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column()
    subtotal_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    quote_version: Mapped[QuoteVersion] = relationship(back_populates="sections")
    line_items: Mapped[list[QuoteLineItem]] = relationship(
        back_populates="quote_section", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "ix_quote_sections_version_sort_order",
            "quote_version_id",
            "sort_order",
            unique=True,
        ),
    )


class QuoteLineItem(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "quote_line_items"

    quote_section_id: Mapped[str] = mapped_column(
        ForeignKey("quote_sections.id", ondelete="CASCADE")
    )
    sort_order: Mapped[int] = mapped_column()
    line_type: Mapped[QuoteLineItemType] = mapped_column(
        SqlEnum(QuoteLineItemType, name="quote_line_item_type", native_enum=False, length=32),
        default=QuoteLineItemType.service,
    )
    discipline_id: Mapped[str | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="SET NULL"), nullable=True
    )
    subcategory_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revenue_category_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text())
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=1)
    unit: Mapped[str] = mapped_column(String(50))
    rate: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)

    quote_section: Mapped[QuoteSection] = relationship(back_populates="line_items")
    discipline: Mapped[Discipline | None] = relationship(back_populates="quote_line_items")
    forecast_lines: Mapped[list[ForecastLine]] = relationship(
        back_populates="source_quote_line_item"
    )

    __table_args__ = (
        Index(
            "ix_quote_line_items_quote_section_sort_order",
            "quote_section_id",
            "sort_order",
            unique=True,
        ),
        Index("ix_quote_line_items_discipline_id", "discipline_id"),
    )
