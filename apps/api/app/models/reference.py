from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentifierMixin, JsonObjectType, TimestampMixin
from app.models.enums import CompanyClassificationType

if TYPE_CHECKING:
    from app.models.comparables import ProjectBenchmarkDisciplineSummary
    from app.models.forecasts import ForecastLine
    from app.models.projects import (
        ProjectContact,
        ProjectDiscipline,
        ProjectOutcome,
        ProjectParty,
        ProjectScheduleRange,
    )
    from app.models.quotes import QuoteLineItem


class ReferenceDataValue(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "reference_data_values"

    category: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer(), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JsonObjectType, nullable=True
    )

    __table_args__ = (
        Index(
            "ix_reference_data_values_category_active_sort_order",
            "category",
            "is_active",
            "sort_order",
        ),
        Index("ix_reference_data_values_category_key", "category", "key", unique=True),
    )


class Company(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255))
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)

    classifications: Mapped[list[CompanyClassification]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    company_contacts: Mapped[list[CompanyContact]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    project_parties: Mapped[list[ProjectParty]] = relationship(back_populates="company")
    project_contacts: Mapped[list[ProjectContact]] = relationship(back_populates="company")
    competitive_outcomes: Mapped[list[ProjectOutcome]] = relationship(
        back_populates="competitor_company", foreign_keys="ProjectOutcome.competitor_company_id"
    )


class CompanyClassification(IdentifierMixin, Base):
    __tablename__ = "company_classifications"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    classification: Mapped[CompanyClassificationType] = mapped_column(
        SqlEnum(
            CompanyClassificationType,
            name="company_classification_type",
            native_enum=False,
            length=32,
        )
    )
    created_at: Mapped[date] = mapped_column(Date())

    company: Mapped[Company] = relationship(back_populates="classifications")

    __table_args__ = (
        Index("ix_company_classifications_classification", "classification"),
        Index(
            "ix_company_classifications_company_classification",
            "company_id",
            "classification",
            unique=True,
        ),
    )


class Contact(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)

    company_links: Mapped[list[CompanyContact]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )
    project_links: Mapped[list[ProjectContact]] = relationship(back_populates="contact")

    __table_args__ = (Index("ix_contacts_last_name_first_name", "last_name", "first_name"),)


class ContactRole(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "contact_roles"

    key: Mapped[str] = mapped_column(String(100), unique=True)
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)

    company_uses: Mapped[list[CompanyContact]] = relationship(back_populates="contact_role")
    project_uses: Mapped[list[ProjectContact]] = relationship(back_populates="contact_role")


class CompanyContact(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "company_contacts"

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    contact_role_id: Mapped[str | None] = mapped_column(
        ForeignKey("contact_roles.id", ondelete="SET NULL"), nullable=True
    )
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean(), default=False)
    start_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date(), nullable=True)

    company: Mapped[Company] = relationship(back_populates="company_contacts")
    contact: Mapped[Contact] = relationship(back_populates="company_links")
    contact_role: Mapped[ContactRole | None] = relationship(back_populates="company_uses")

    __table_args__ = (
        Index("ix_company_contacts_company_id_is_primary", "company_id", "is_primary"),
        Index("ix_company_contacts_contact_id", "contact_id"),
        Index(
            "ix_company_contacts_company_contact_role",
            "company_id",
            "contact_id",
            "contact_role_id",
            unique=True,
        ),
    )


class Discipline(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "disciplines"

    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer(), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)

    project_links: Mapped[list[ProjectDiscipline]] = relationship(back_populates="discipline")
    schedule_ranges: Mapped[list[ProjectScheduleRange]] = relationship(
        back_populates="discipline"
    )
    quote_line_items: Mapped[list[QuoteLineItem]] = relationship(back_populates="discipline")
    forecast_lines: Mapped[list[ForecastLine]] = relationship(back_populates="discipline")
    benchmark_summaries: Mapped[list[ProjectBenchmarkDisciplineSummary]] = relationship(
        back_populates="discipline"
    )

    __table_args__ = (Index("ix_disciplines_sort_order_is_active", "sort_order", "is_active"),)


class LossReason(IdentifierMixin, TimestampMixin, Base):
    __tablename__ = "loss_reasons"

    code: Mapped[str] = mapped_column(String(100), unique=True)
    label: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)

    outcomes: Mapped[list[ProjectOutcome]] = relationship(back_populates="loss_reason")
