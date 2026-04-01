from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.datetimes import same_timestamp
from app.core.errors import ApiProblemException
from app.core.normalization import build_full_name, normalize_email, normalize_name
from app.models import Company, CompanyClassification, Contact, Discipline
from app.models.enums import CompanyClassificationType
from app.modules.audit.service import audit_service
from app.modules.clients.schemas import (
    ContactCreateRequest,
    ContactRead,
    ContactUpdateRequest,
    CounterpartyCreateRequest,
    CounterpartyRead,
    CounterpartyUpdateRequest,
    DisciplineCreateRequest,
    DisciplineRead,
    DisciplineUpdateRequest,
)


class ClientsService:
    def list_counterparties(self, session: Session) -> list[CounterpartyRead]:
        companies = list(session.scalars(select(Company).order_by(Company.name)))
        return [self._serialize_company(session, company) for company in companies]

    def list_clients(self, session: Session) -> list[CounterpartyRead]:
        companies = list(
            session.scalars(
                select(Company)
                .join(CompanyClassification, CompanyClassification.company_id == Company.id)
                .where(CompanyClassification.classification == CompanyClassificationType.client)
                .order_by(Company.name)
            )
        )
        return [self._serialize_company(session, company) for company in companies]

    def get_counterparty(self, session: Session, company_id: str) -> CounterpartyRead:
        company = session.get(Company, company_id)
        if company is None:
            raise ApiProblemException(
                404,
                f"Counterparty '{company_id}' was not found.",
                "Counterparty Not Found",
            )
        return self._serialize_company(session, company)

    def create_counterparty(
        self,
        session: Session,
        payload: CounterpartyCreateRequest,
        *,
        actor_id: str,
    ) -> CounterpartyRead:
        normalized_name = normalize_name(payload.name)
        existing = session.scalar(
            select(Company).where(Company.normalized_name == normalized_name)
        )
        if existing is not None:
            raise ApiProblemException(
                409,
                "A counterparty with that name already exists.",
                "Counterparty Exists",
            )

        company = Company(
            name=payload.name,
            legal_name=payload.legal_name,
            normalized_name=normalized_name,
            website_url=payload.website_url,
            default_currency_code=payload.default_currency_code,
            notes=payload.notes,
            is_active=payload.is_active,
        )
        session.add(company)
        session.flush()
        self._replace_classifications(session, company.id, payload.classifications)
        audit_service.record(
            session,
            action="counterparty.created",
            entity_type="company",
            entity_id=company.id,
            actor_id=actor_id,
            summary=f"Created counterparty {company.name}.",
            after={"classifications": [item.value for item in payload.classifications]},
        )
        return self._serialize_company(session, company)

    def update_counterparty(
        self,
        session: Session,
        company_id: str,
        payload: CounterpartyUpdateRequest,
        *,
        actor_id: str,
    ) -> CounterpartyRead:
        company = session.get(Company, company_id)
        if company is None:
            raise ApiProblemException(
                404,
                f"Counterparty '{company_id}' was not found.",
                "Counterparty Not Found",
            )
        self._assert_current(company.updated_at, payload.expected_updated_at)
        before = self._snapshot_company(session, company)
        if payload.name is not None:
            company.name = payload.name
            company.normalized_name = normalize_name(payload.name)
        if payload.legal_name is not None:
            company.legal_name = payload.legal_name
        if payload.website_url is not None:
            company.website_url = payload.website_url
        if payload.default_currency_code is not None:
            company.default_currency_code = payload.default_currency_code
        if payload.notes is not None:
            company.notes = payload.notes
        if payload.is_active is not None:
            company.is_active = payload.is_active
        if payload.classifications is not None:
            self._replace_classifications(session, company.id, payload.classifications)
        session.flush()
        audit_service.record(
            session,
            action="counterparty.updated",
            entity_type="company",
            entity_id=company.id,
            actor_id=actor_id,
            summary=f"Updated counterparty {company.name}.",
            before=before,
            after=self._snapshot_company(session, company),
        )
        return self._serialize_company(session, company)

    def list_contacts(self, session: Session) -> list[ContactRead]:
        contacts = list(
            session.scalars(select(Contact).order_by(Contact.last_name, Contact.first_name))
        )
        return [self._serialize_contact(contact) for contact in contacts]

    def get_contact(self, session: Session, contact_id: str) -> ContactRead:
        contact = session.get(Contact, contact_id)
        if contact is None:
            raise ApiProblemException(
                404,
                f"Contact '{contact_id}' was not found.",
                "Contact Not Found",
            )
        return self._serialize_contact(contact)

    def create_contact(
        self,
        session: Session,
        payload: ContactCreateRequest,
        *,
        actor_id: str,
    ) -> ContactRead:
        contact = Contact(
            first_name=payload.first_name,
            last_name=payload.last_name,
            full_name=build_full_name(payload.first_name, payload.last_name),
            email=str(payload.email) if payload.email else None,
            normalized_email=normalize_email(str(payload.email)) if payload.email else None,
            phone=payload.phone,
            mobile=payload.mobile,
            notes=payload.notes,
            is_active=payload.is_active,
        )
        session.add(contact)
        session.flush()
        audit_service.record(
            session,
            action="contact.created",
            entity_type="contact",
            entity_id=contact.id,
            actor_id=actor_id,
            summary=f"Created contact {contact.full_name}.",
        )
        return self._serialize_contact(contact)

    def update_contact(
        self,
        session: Session,
        contact_id: str,
        payload: ContactUpdateRequest,
        *,
        actor_id: str,
    ) -> ContactRead:
        contact = session.get(Contact, contact_id)
        if contact is None:
            raise ApiProblemException(
                404,
                f"Contact '{contact_id}' was not found.",
                "Contact Not Found",
            )
        self._assert_current(contact.updated_at, payload.expected_updated_at)
        before = self._snapshot_contact(contact)
        if payload.first_name is not None:
            contact.first_name = payload.first_name
        if payload.last_name is not None:
            contact.last_name = payload.last_name
        if payload.first_name is not None or payload.last_name is not None:
            contact.full_name = build_full_name(contact.first_name, contact.last_name)
        if payload.email is not None:
            contact.email = str(payload.email)
            contact.normalized_email = normalize_email(str(payload.email))
        if payload.phone is not None:
            contact.phone = payload.phone
        if payload.mobile is not None:
            contact.mobile = payload.mobile
        if payload.notes is not None:
            contact.notes = payload.notes
        if payload.is_active is not None:
            contact.is_active = payload.is_active
        session.flush()
        audit_service.record(
            session,
            action="contact.updated",
            entity_type="contact",
            entity_id=contact.id,
            actor_id=actor_id,
            summary=f"Updated contact {contact.full_name}.",
            before=before,
            after=self._snapshot_contact(contact),
        )
        return self._serialize_contact(contact)

    def list_disciplines(self, session: Session) -> list[DisciplineRead]:
        disciplines = list(
            session.scalars(select(Discipline).order_by(Discipline.sort_order, Discipline.name))
        )
        return [self._serialize_discipline(discipline) for discipline in disciplines]

    def get_discipline(self, session: Session, discipline_id: str) -> DisciplineRead:
        discipline = session.get(Discipline, discipline_id)
        if discipline is None:
            raise ApiProblemException(
                404,
                f"Discipline '{discipline_id}' was not found.",
                "Discipline Not Found",
            )
        return self._serialize_discipline(discipline)

    def create_discipline(
        self,
        session: Session,
        payload: DisciplineCreateRequest,
        *,
        actor_id: str,
    ) -> DisciplineRead:
        existing = session.scalar(select(Discipline).where(Discipline.code == payload.code))
        if existing is not None:
            raise ApiProblemException(
                409,
                "A discipline with that code already exists.",
                "Discipline Exists",
            )
        discipline = Discipline(
            code=payload.code,
            name=payload.name,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        session.add(discipline)
        session.flush()
        audit_service.record(
            session,
            action="discipline.created",
            entity_type="discipline",
            entity_id=discipline.id,
            actor_id=actor_id,
            summary=f"Created discipline {discipline.code}.",
        )
        return self._serialize_discipline(discipline)

    def update_discipline(
        self,
        session: Session,
        discipline_id: str,
        payload: DisciplineUpdateRequest,
        *,
        actor_id: str,
    ) -> DisciplineRead:
        discipline = session.get(Discipline, discipline_id)
        if discipline is None:
            raise ApiProblemException(
                404,
                f"Discipline '{discipline_id}' was not found.",
                "Discipline Not Found",
            )
        self._assert_current(discipline.updated_at, payload.expected_updated_at)
        before = self._snapshot_discipline(discipline)
        if payload.code is not None:
            discipline.code = payload.code
        if payload.name is not None:
            discipline.name = payload.name
        if payload.sort_order is not None:
            discipline.sort_order = payload.sort_order
        if payload.is_active is not None:
            discipline.is_active = payload.is_active
        session.flush()
        audit_service.record(
            session,
            action="discipline.updated",
            entity_type="discipline",
            entity_id=discipline.id,
            actor_id=actor_id,
            summary=f"Updated discipline {discipline.code}.",
            before=before,
            after=self._snapshot_discipline(discipline),
        )
        return self._serialize_discipline(discipline)

    def _replace_classifications(
        self,
        session: Session,
        company_id: str,
        classifications: list[CompanyClassificationType],
    ) -> None:
        session.execute(
            delete(CompanyClassification).where(CompanyClassification.company_id == company_id)
        )
        for classification in classifications:
            session.add(
                CompanyClassification(
                    company_id=company_id,
                    classification=classification,
                    created_at=date.today(),
                )
            )
        session.flush()

    def _serialize_company(self, session: Session, company: Company) -> CounterpartyRead:
        classifications = list(
            session.scalars(
                select(CompanyClassification.classification)
                .where(CompanyClassification.company_id == company.id)
                .order_by(CompanyClassification.classification)
            )
        )
        return CounterpartyRead(
            id=company.id,
            name=company.name,
            legal_name=company.legal_name,
            website_url=company.website_url,
            default_currency_code=company.default_currency_code,
            notes=company.notes,
            is_active=company.is_active,
            classifications=classifications,
            created_at=company.created_at,
            updated_at=company.updated_at,
        )

    def _serialize_contact(self, contact: Contact) -> ContactRead:
        return ContactRead(
            id=contact.id,
            first_name=contact.first_name,
            last_name=contact.last_name,
            full_name=contact.full_name,
            email=contact.email,
            phone=contact.phone,
            mobile=contact.mobile,
            notes=contact.notes,
            is_active=contact.is_active,
            created_at=contact.created_at,
            updated_at=contact.updated_at,
        )

    def _serialize_discipline(self, discipline: Discipline) -> DisciplineRead:
        return DisciplineRead(
            id=discipline.id,
            code=discipline.code,
            name=discipline.name,
            sort_order=discipline.sort_order,
            is_active=discipline.is_active,
            created_at=discipline.created_at,
            updated_at=discipline.updated_at,
        )

    def _snapshot_company(self, session: Session, company: Company) -> dict[str, object]:
        return self._serialize_company(session, company).model_dump(mode="json")

    def _snapshot_contact(self, contact: Contact) -> dict[str, object]:
        return self._serialize_contact(contact).model_dump(mode="json")

    def _snapshot_discipline(self, discipline: Discipline) -> dict[str, object]:
        return self._serialize_discipline(discipline).model_dump(mode="json")

    def _assert_current(self, current: datetime, expected: datetime) -> None:
        if not same_timestamp(current, expected):
            raise ApiProblemException(
                409,
                "The record was modified by another request. Reload and retry.",
                "Stale Update",
            )


clients_service = ClientsService()
