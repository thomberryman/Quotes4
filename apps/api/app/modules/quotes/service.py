from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.datetimes import same_timestamp
from app.core.errors import ApiProblemException
from app.models import (
    Discipline,
    Project,
    Quote,
    QuoteLineItem,
    QuoteSection,
    QuoteVersion,
    QuoteVersionFile,
)
from app.models.enums import QuoteVersionStatus
from app.modules.audit.service import audit_service
from app.modules.quotes.schemas import (
    QuoteCreateRequest,
    QuoteLineItemRead,
    QuoteRead,
    QuoteSectionRead,
    QuoteSectionWrite,
    QuoteSummary,
    QuoteUpdateRequest,
    QuoteVersionCreateRequest,
    QuoteVersionRead,
    QuoteVersionSummary,
    QuoteVersionUpdateRequest,
)


@dataclass(frozen=True)
class QuoteApprovalLineItem:
    sort_order: int
    section_label: str
    line_type: str
    description: str
    quantity: float
    unit: str
    rate: float
    amount: float


@dataclass(frozen=True)
class QuoteApprovalPayload:
    project_id: str
    target_mode: str
    target_quote_id: str | None
    title: str | None
    quote_number: str | None
    currency_code: str
    source_document_date: date | None
    source_version_label: str | None
    source_job_number: str | None
    subtotal_amount: float
    tax_amount: float
    total_amount: float
    source_uploaded_file_id: str
    source_pdf_extraction_run_id: str
    assumptions: list[str]
    exclusions: list[str]
    notes: list[str]
    line_items: list[QuoteApprovalLineItem]


@dataclass(frozen=True)
class QuoteApprovalResult:
    quote: QuoteRead
    version: QuoteVersionRead


def _to_cents(amount: float) -> int:
    return round(amount * 100)


class QuotesService:
    def list_quotes(
        self,
        session: Session,
        *,
        project_id: str | None = None,
    ) -> list[QuoteSummary]:
        statement = select(Quote).order_by(desc(Quote.updated_at))
        if project_id is not None:
            statement = statement.where(Quote.project_id == project_id)
        quotes = list(session.scalars(statement))
        return [self._serialize_quote_summary(session, quote) for quote in quotes]

    def get_quote(self, session: Session, quote_id: str) -> QuoteRead:
        quote = self._get_quote_entity(session, quote_id)
        return self._serialize_quote(session, quote)

    def create_quote(
        self,
        session: Session,
        payload: QuoteCreateRequest,
        *,
        actor_id: str,
    ) -> QuoteRead:
        if session.get(Project, payload.project_id) is None:
            raise ApiProblemException(
                422,
                f"Project '{payload.project_id}' was not found.",
                "Invalid Project",
            )
        quote = Quote(
            project_id=payload.project_id,
            quote_number=payload.quote_number,
            title=payload.title,
        )
        session.add(quote)
        session.flush()
        audit_service.record(
            session,
            action="quote.created",
            entity_type="quote",
            entity_id=quote.id,
            actor_id=actor_id,
            project_id=quote.project_id,
            summary=f"Created quote {quote.id}.",
        )
        return self._serialize_quote(session, quote)

    def update_quote(
        self,
        session: Session,
        quote_id: str,
        payload: QuoteUpdateRequest,
        *,
        actor_id: str,
    ) -> QuoteRead:
        quote = self._get_quote_entity(session, quote_id)
        self._assert_current(quote.updated_at, payload.expected_updated_at, "quote")
        before = self._serialize_quote(session, quote).model_dump(mode="json")
        for field in ("quote_number", "title"):
            if field in payload.model_fields_set:
                setattr(quote, field, getattr(payload, field))
        if "current_version_id" in payload.model_fields_set:
            if payload.current_version_id is not None:
                version = self._get_quote_version_entity(session, payload.current_version_id)
                if version.quote_id != quote.id:
                    raise ApiProblemException(
                        422,
                        "Current version must belong to the quote.",
                        "Invalid Quote Version",
                    )
            quote.current_version_id = payload.current_version_id
        session.flush()
        audit_service.record(
            session,
            action="quote.updated",
            entity_type="quote",
            entity_id=quote.id,
            actor_id=actor_id,
            project_id=quote.project_id,
            summary=f"Updated quote {quote.id}.",
            before=before,
            after=self._serialize_quote(session, quote).model_dump(mode="json"),
        )
        return self._serialize_quote(session, quote)

    def list_versions(self, session: Session, quote_id: str) -> list[QuoteVersionSummary]:
        self._get_quote_entity(session, quote_id)
        versions = list(
            session.scalars(
                select(QuoteVersion)
                .where(QuoteVersion.quote_id == quote_id)
                .order_by(desc(QuoteVersion.version_number))
            )
        )
        return [self._serialize_version_summary(version) for version in versions]

    def get_version(self, session: Session, version_id: str) -> QuoteVersionRead:
        version = self._get_quote_version_entity(session, version_id)
        return self._serialize_version(session, version)

    def create_version(
        self,
        session: Session,
        quote_id: str,
        payload: QuoteVersionCreateRequest,
        *,
        actor_id: str,
    ) -> QuoteVersionRead:
        quote = self._get_quote_entity(session, quote_id)
        base_version = None
        if payload.base_version_id is not None:
            base_version = self._get_quote_version_entity(session, payload.base_version_id)
            if base_version.quote_id != quote.id:
                raise ApiProblemException(
                    422,
                    "Base version must belong to the quote.",
                    "Invalid Quote Version",
                )
        section_payloads = payload.sections or self._clone_sections_payload(session, base_version)
        self._validate_version_financials(
            session,
            subtotal_amount=payload.subtotal_amount,
            tax_amount=payload.tax_amount,
            total_amount=payload.total_amount,
            sections=section_payloads,
        )

        next_version_number = session.scalar(
            select(QuoteVersion.version_number)
            .where(QuoteVersion.quote_id == quote.id)
            .order_by(desc(QuoteVersion.version_number))
            .limit(1)
        )
        version = QuoteVersion(
            quote_id=quote.id,
            parent_version_id=base_version.id if base_version is not None else None,
            version_number=(next_version_number or 0) + 1,
            status=QuoteVersionStatus.draft,
            title=payload.title,
            currency_code=payload.currency_code,
            valid_until=payload.valid_until,
            created_by_id=actor_id,
            client_facing_notes=payload.client_facing_notes,
            internal_notes=payload.internal_notes,
            source_document_date=payload.source_document_date,
            source_version_label=payload.source_version_label,
            pricing_context_json=payload.pricing_context,
            subtotal_amount=payload.subtotal_amount,
            tax_amount=payload.tax_amount,
            total_amount=payload.total_amount,
        )
        session.add(version)
        session.flush()
        self._replace_sections(session, version, section_payloads)
        quote.current_version_id = version.id
        session.flush()
        audit_service.record(
            session,
            action="quote.version.created",
            entity_type="quote_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=quote.project_id,
            summary=f"Created quote version v{version.version_number} for {quote.id}.",
        )
        return self._serialize_version(session, version)

    def create_from_ingestion(
        self,
        session: Session,
        payload: QuoteApprovalPayload,
        *,
        actor_id: str,
    ) -> QuoteApprovalResult:
        sections = self._build_ingestion_sections(payload.line_items)
        internal_notes = self._build_ingestion_internal_notes(payload)

        if payload.target_mode == "new_version":
            if payload.target_quote_id is None:
                raise ApiProblemException(
                    422,
                    "A target quote is required to create a new quote version.",
                    "Invalid Ingestion Approval",
                )
            quote = self._get_quote_entity(session, payload.target_quote_id)
            base_version_id = quote.current_version_id
        else:
            created_quote = self.create_quote(
                session,
                QuoteCreateRequest(
                    project_id=payload.project_id,
                    quote_number=payload.quote_number,
                    title=payload.title,
                ),
                actor_id=actor_id,
            )
            quote = self._get_quote_entity(session, created_quote.id)
            base_version_id = None

        if payload.quote_number and not quote.quote_number:
            quote.quote_number = payload.quote_number

        version = self.create_version(
            session,
            quote.id,
            QuoteVersionCreateRequest(
                base_version_id=base_version_id,
                title=payload.title,
                currency_code=payload.currency_code,
                source_document_date=payload.source_document_date,
                source_version_label=payload.source_version_label,
                subtotal_amount=payload.subtotal_amount,
                tax_amount=payload.tax_amount,
                total_amount=payload.total_amount,
                internal_notes=internal_notes,
                sections=sections,
            ),
            actor_id=actor_id,
        )

        existing_file_link = session.scalar(
            select(QuoteVersionFile).where(
                QuoteVersionFile.quote_version_id == version.id,
                QuoteVersionFile.uploaded_file_id == payload.source_uploaded_file_id,
            )
        )
        if existing_file_link is None:
            session.add(
                QuoteVersionFile(
                    quote_version_id=version.id,
                    uploaded_file_id=payload.source_uploaded_file_id,
                    label="Approved source PDF",
                    created_at=datetime.now(UTC),
                )
            )
            session.flush()

        return QuoteApprovalResult(
            quote=self._serialize_quote(session, quote),
            version=self._serialize_version(
                session,
                self._get_quote_version_entity(session, version.id),
            ),
        )

    def update_version(
        self,
        session: Session,
        version_id: str,
        payload: QuoteVersionUpdateRequest,
        *,
        actor_id: str,
    ) -> QuoteVersionRead:
        version = self._get_quote_version_entity(session, version_id)
        if version.status != QuoteVersionStatus.draft:
            raise ApiProblemException(
                409,
                "Only draft versions can be updated.",
                "Immutable Quote Version",
            )
        self._assert_current(version.updated_at, payload.expected_updated_at, "quote version")
        before = self._serialize_version(session, version).model_dump(mode="json")
        effective_sections = (
            payload.sections
            if payload.sections is not None
            else self._section_payloads_for_version(session, version)
        )
        effective_subtotal_amount = (
            payload.subtotal_amount
            if "subtotal_amount" in payload.model_fields_set
            else float(version.subtotal_amount)
        )
        effective_tax_amount = (
            payload.tax_amount
            if "tax_amount" in payload.model_fields_set
            else float(version.tax_amount)
        )
        effective_total_amount = (
            payload.total_amount
            if "total_amount" in payload.model_fields_set
            else float(version.total_amount)
        )
        self._validate_version_financials(
            session,
            subtotal_amount=effective_subtotal_amount,
            tax_amount=effective_tax_amount,
            total_amount=effective_total_amount,
            sections=effective_sections,
        )
        for field in (
            "title",
            "currency_code",
            "valid_until",
            "client_facing_notes",
            "internal_notes",
            "source_document_date",
            "source_version_label",
            "pricing_context",
            "subtotal_amount",
            "tax_amount",
            "total_amount",
        ):
            if field in payload.model_fields_set:
                if field == "pricing_context":
                    version.pricing_context_json = payload.pricing_context
                else:
                    setattr(version, field, getattr(payload, field))
        if payload.sections is not None:
            self._replace_sections(session, version, payload.sections)
        session.flush()
        audit_service.record(
            session,
            action="quote.version.updated",
            entity_type="quote_version",
            entity_id=version.id,
            actor_id=actor_id,
            summary=f"Updated quote version v{version.version_number}.",
            before=before,
            after=self._serialize_version(session, version).model_dump(mode="json"),
        )
        return self._serialize_version(session, version)

    def issue_version(
        self,
        session: Session,
        version_id: str,
        *,
        actor_id: str,
    ) -> QuoteVersionRead:
        version = self._get_quote_version_entity(session, version_id)
        if version.status != QuoteVersionStatus.draft:
            raise ApiProblemException(
                409,
                "Only draft versions can be issued.",
                "Invalid Quote Version",
            )
        quote = self._get_quote_entity(session, version.quote_id)
        issued_at = datetime.now(UTC)
        siblings = list(
            session.scalars(select(QuoteVersion).where(QuoteVersion.quote_id == quote.id))
        )
        for sibling in siblings:
            if sibling.id != version.id and sibling.status == QuoteVersionStatus.issued:
                sibling.status = QuoteVersionStatus.superseded
        version.status = QuoteVersionStatus.issued
        version.issued_at = issued_at
        version.issued_by_id = actor_id
        quote.current_version_id = version.id
        session.flush()
        audit_service.record(
            session,
            action="quote.version.issued",
            entity_type="quote_version",
            entity_id=version.id,
            actor_id=actor_id,
            project_id=quote.project_id,
            summary=f"Issued quote version v{version.version_number}.",
        )
        from app.modules.forecasts.service import forecast_service

        forecast_service.recalculate_project(session, quote.project_id, actor_id=actor_id)
        return self._serialize_version(session, version)

    def _replace_sections(
        self,
        session: Session,
        version: QuoteVersion,
        sections: list[QuoteSectionWrite],
    ) -> None:
        self._validate_sections(session, sections)
        session.execute(delete(QuoteSection).where(QuoteSection.quote_version_id == version.id))
        session.flush()
        for section_payload in sections:
            section = QuoteSection(
                quote_version_id=version.id,
                name=section_payload.name,
                sort_order=section_payload.sort_order,
                subtotal_amount=section_payload.subtotal_amount,
            )
            session.add(section)
            session.flush()
            for line_payload in section_payload.line_items:
                session.add(
                    QuoteLineItem(
                        quote_section_id=section.id,
                        sort_order=line_payload.sort_order,
                        line_type=line_payload.line_type,
                        discipline_id=line_payload.discipline_id,
                        subcategory_key=line_payload.subcategory_key,
                        revenue_category_key=line_payload.revenue_category_key,
                        description=line_payload.description,
                        quantity=line_payload.quantity,
                        unit=line_payload.unit,
                        rate=line_payload.rate,
                        amount=line_payload.amount,
                        notes=line_payload.notes,
                    )
                )
        session.flush()

    def _clone_sections_payload(
        self, session: Session, base_version: QuoteVersion | None
    ) -> list[QuoteSectionWrite]:
        if base_version is None:
            return []
        return self._section_payloads_for_version(session, base_version)

    def _section_payloads_for_version(
        self, session: Session, version: QuoteVersion
    ) -> list[QuoteSectionWrite]:
        base_sections = list(
            session.scalars(
                select(QuoteSection).where(QuoteSection.quote_version_id == version.id)
                .order_by(QuoteSection.sort_order)
            )
        )
        payloads: list[QuoteSectionWrite] = []
        for base_section in base_sections:
            base_line_items = list(
                session.scalars(
                    select(QuoteLineItem)
                    .where(QuoteLineItem.quote_section_id == base_section.id)
                    .order_by(QuoteLineItem.sort_order)
                )
            )
            payloads.append(
                QuoteSectionWrite(
                    name=base_section.name,
                    sort_order=base_section.sort_order,
                    subtotal_amount=float(base_section.subtotal_amount),
                    line_items=[
                        {
                            "sort_order": item.sort_order,
                            "line_type": item.line_type,
                            "discipline_id": item.discipline_id,
                            "subcategory_key": item.subcategory_key,
                            "revenue_category_key": item.revenue_category_key,
                            "description": item.description,
                            "quantity": float(item.quantity),
                            "unit": item.unit,
                            "rate": float(item.rate),
                            "amount": float(item.amount),
                            "notes": item.notes,
                        }
                        for item in base_line_items
                    ],
                )
            )
        return payloads

    def _build_ingestion_sections(
        self, line_items: list[QuoteApprovalLineItem]
    ) -> list[QuoteSectionWrite]:
        grouped: OrderedDict[str, list[QuoteApprovalLineItem]] = OrderedDict()
        for line_item in sorted(line_items, key=lambda item: item.sort_order):
            section_label = line_item.section_label or "General"
            grouped.setdefault(section_label, []).append(line_item)

        sections: list[QuoteSectionWrite] = []
        for sort_order, (section_label, items) in enumerate(grouped.items(), start=1):
            sections.append(
                QuoteSectionWrite(
                    name=section_label,
                    sort_order=sort_order,
                    subtotal_amount=round(sum(item.amount for item in items), 2),
                    line_items=[
                        {
                            "sort_order": item.sort_order,
                            "line_type": item.line_type,
                            "description": item.description,
                            "quantity": item.quantity,
                            "unit": item.unit,
                            "rate": item.rate,
                            "amount": item.amount,
                        }
                        for item in items
                    ],
                )
            )
        return sections

    def _build_ingestion_internal_notes(self, payload: QuoteApprovalPayload) -> str:
        lines = [
            f"Created from PDF extraction run {payload.source_pdf_extraction_run_id}.",
            f"Source uploaded file {payload.source_uploaded_file_id}.",
        ]
        if payload.quote_number:
            lines.append(f"Source quote ID: {payload.quote_number}.")
        if payload.source_job_number:
            lines.append(f"Source job number: {payload.source_job_number}.")
        if payload.assumptions:
            lines.append("Assumptions:")
            lines.extend(f"- {value}" for value in payload.assumptions)
        if payload.exclusions:
            lines.append("Exclusions:")
            lines.extend(f"- {value}" for value in payload.exclusions)
        if payload.notes:
            lines.append("Reviewer Notes:")
            lines.extend(f"- {value}" for value in payload.notes)
        return "\n".join(lines)

    def _serialize_quote_summary(self, session: Session, quote: Quote) -> QuoteSummary:
        current_status = None
        if quote.current_version_id is not None:
            current_version = session.get(QuoteVersion, quote.current_version_id)
            current_status = current_version.status if current_version is not None else None
        return QuoteSummary(
            id=quote.id,
            project_id=quote.project_id,
            quote_number=quote.quote_number,
            title=quote.title,
            current_version_id=quote.current_version_id,
            current_version_status=current_status,
            updated_at=quote.updated_at,
        )

    def _serialize_quote(self, session: Session, quote: Quote) -> QuoteRead:
        versions = list(
            session.scalars(
                select(QuoteVersion)
                .where(QuoteVersion.quote_id == quote.id)
                .order_by(desc(QuoteVersion.version_number))
            )
        )
        summary = self._serialize_quote_summary(session, quote)
        return QuoteRead(
            **summary.model_dump(),
            created_at=quote.created_at,
            versions=[self._serialize_version_summary(version) for version in versions],
        )

    def _serialize_version(self, session: Session, version: QuoteVersion) -> QuoteVersionRead:
        sections = list(
            session.scalars(
                select(QuoteSection)
                .where(QuoteSection.quote_version_id == version.id)
                .order_by(QuoteSection.sort_order)
            )
        )
        return QuoteVersionRead(
            **self._serialize_version_summary(version).model_dump(),
            accepted_at=version.accepted_at,
            rejected_at=version.rejected_at,
            client_facing_notes=version.client_facing_notes,
            internal_notes=version.internal_notes,
            source_document_date=version.source_document_date,
            source_version_label=version.source_version_label,
            pricing_context=version.pricing_context_json,
            sections=[self._serialize_section(session, section) for section in sections],
        )

    def _serialize_version_summary(self, version: QuoteVersion) -> QuoteVersionSummary:
        return QuoteVersionSummary(
            id=version.id,
            quote_id=version.quote_id,
            parent_version_id=version.parent_version_id,
            version_number=version.version_number,
            status=version.status,
            title=version.title,
            currency_code=version.currency_code,
            valid_until=version.valid_until,
            issued_at=version.issued_at,
            subtotal_amount=float(version.subtotal_amount),
            tax_amount=float(version.tax_amount),
            total_amount=float(version.total_amount),
            created_at=version.created_at,
            updated_at=version.updated_at,
        )

    def _serialize_section(self, session: Session, section: QuoteSection) -> QuoteSectionRead:
        line_items = list(
            session.scalars(
                select(QuoteLineItem)
                .where(QuoteLineItem.quote_section_id == section.id)
                .order_by(QuoteLineItem.sort_order)
            )
        )
        return QuoteSectionRead(
            id=section.id,
            name=section.name,
            sort_order=section.sort_order,
            subtotal_amount=float(section.subtotal_amount),
            line_items=[
                QuoteLineItemRead(
                    id=item.id,
                    sort_order=item.sort_order,
                    line_type=item.line_type,
                    discipline_id=item.discipline_id,
                    subcategory_key=item.subcategory_key,
                    revenue_category_key=item.revenue_category_key,
                    description=item.description,
                    quantity=float(item.quantity),
                    unit=item.unit,
                    rate=float(item.rate),
                    amount=float(item.amount),
                    notes=item.notes,
                )
                for item in line_items
            ],
        )

    def _validate_sections(self, session: Session, sections: list[QuoteSectionWrite]) -> None:
        for section in sections:
            for line_item in section.line_items:
                if (
                    line_item.discipline_id is not None
                    and session.get(Discipline, line_item.discipline_id) is None
                ):
                    raise ApiProblemException(
                        422,
                        f"Discipline '{line_item.discipline_id}' was not found.",
                        "Invalid Quote Section",
                    )

    def _validate_version_financials(
        self,
        session: Session,
        *,
        subtotal_amount: float,
        tax_amount: float,
        total_amount: float,
        sections: list[QuoteSectionWrite],
    ) -> None:
        self._validate_sections(session, sections)

        computed_subtotal_amount = 0
        for section in sections:
            section_line_total = sum(
                _to_cents(line_item.amount) for line_item in section.line_items
            )
            if section_line_total != _to_cents(section.subtotal_amount):
                raise ApiProblemException(
                    422,
                    f"Section subtotal for '{section.name}' must equal the sum of its line items.",
                    "Invalid Quote Totals",
                )
            computed_subtotal_amount += section_line_total

        if computed_subtotal_amount != _to_cents(subtotal_amount):
            raise ApiProblemException(
                422,
                "Quote subtotal must equal the sum of section subtotals.",
                "Invalid Quote Totals",
            )

        if _to_cents(subtotal_amount) + _to_cents(tax_amount) != _to_cents(total_amount):
            raise ApiProblemException(
                422,
                "Quote total must equal subtotal plus tax.",
                "Invalid Quote Totals",
            )

    def _get_quote_entity(self, session: Session, quote_id: str) -> Quote:
        quote = session.get(Quote, quote_id)
        if quote is None:
            raise ApiProblemException(404, f"Quote '{quote_id}' was not found.", "Quote Not Found")
        return quote

    def _get_quote_version_entity(self, session: Session, version_id: str) -> QuoteVersion:
        version = session.get(QuoteVersion, version_id)
        if version is None:
            raise ApiProblemException(
                404,
                f"Quote version '{version_id}' was not found.",
                "Quote Version Not Found",
            )
        return version

    def _assert_current(self, current: datetime, expected: datetime, entity_label: str) -> None:
        if not same_timestamp(current, expected):
            raise ApiProblemException(
                409,
                f"The {entity_label} was modified by another request. Reload and retry.",
                "Stale Update",
            )


quotes_service = QuotesService()
