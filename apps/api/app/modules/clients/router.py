from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import CurrentSubject, require_permissions
from app.core.db import get_db_session
from app.modules.clients.schemas import (
    ContactCreateRequest,
    ContactListResponse,
    ContactRead,
    ContactUpdateRequest,
    CounterpartyCreateRequest,
    CounterpartyListResponse,
    CounterpartyRead,
    CounterpartyUpdateRequest,
    DisciplineCreateRequest,
    DisciplineListResponse,
    DisciplineRead,
    DisciplineUpdateRequest,
)
from app.modules.clients.service import clients_service

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db_session)]
CounterpartyReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("counterparties.read")),
]
CounterpartyWriteSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("counterparties.write")),
]
ContactsReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("contacts.read")),
]
ContactsWriteSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("contacts.write")),
]
DisciplinesReadSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("disciplines.read")),
]
DisciplinesWriteSubject = Annotated[
    CurrentSubject,
    Depends(require_permissions("disciplines.write")),
]


@router.get("/clients", response_model=CounterpartyListResponse)
def list_clients(
    session: DbSession,
    _subject: CounterpartyReadSubject,
) -> CounterpartyListResponse:
    return CounterpartyListResponse(items=clients_service.list_clients(session))


@router.get("/counterparties", response_model=CounterpartyListResponse)
def list_counterparties(
    session: DbSession,
    _subject: CounterpartyReadSubject,
) -> CounterpartyListResponse:
    return CounterpartyListResponse(items=clients_service.list_counterparties(session))


@router.post("/counterparties", response_model=CounterpartyRead, status_code=201)
def create_counterparty(
    payload: CounterpartyCreateRequest,
    session: DbSession,
    subject: CounterpartyWriteSubject,
) -> CounterpartyRead:
    company = clients_service.create_counterparty(session, payload, actor_id=subject.user.id)
    session.commit()
    return company


@router.get("/counterparties/{company_id}", response_model=CounterpartyRead)
def get_counterparty(
    company_id: str,
    session: DbSession,
    _subject: CounterpartyReadSubject,
) -> CounterpartyRead:
    return clients_service.get_counterparty(session, company_id)


@router.patch("/counterparties/{company_id}", response_model=CounterpartyRead)
def update_counterparty(
    company_id: str,
    payload: CounterpartyUpdateRequest,
    session: DbSession,
    subject: CounterpartyWriteSubject,
) -> CounterpartyRead:
    company = clients_service.update_counterparty(
        session,
        company_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return company


@router.get("/contacts", response_model=ContactListResponse)
def list_contacts(
    session: DbSession,
    _subject: ContactsReadSubject,
) -> ContactListResponse:
    return ContactListResponse(items=clients_service.list_contacts(session))


@router.post("/contacts", response_model=ContactRead, status_code=201)
def create_contact(
    payload: ContactCreateRequest,
    session: DbSession,
    subject: ContactsWriteSubject,
) -> ContactRead:
    contact = clients_service.create_contact(session, payload, actor_id=subject.user.id)
    session.commit()
    return contact


@router.get("/contacts/{contact_id}", response_model=ContactRead)
def get_contact(
    contact_id: str,
    session: DbSession,
    _subject: ContactsReadSubject,
) -> ContactRead:
    return clients_service.get_contact(session, contact_id)


@router.patch("/contacts/{contact_id}", response_model=ContactRead)
def update_contact(
    contact_id: str,
    payload: ContactUpdateRequest,
    session: DbSession,
    subject: ContactsWriteSubject,
) -> ContactRead:
    contact = clients_service.update_contact(session, contact_id, payload, actor_id=subject.user.id)
    session.commit()
    return contact


@router.get("/disciplines", response_model=DisciplineListResponse)
def list_disciplines(
    session: DbSession,
    _subject: DisciplinesReadSubject,
) -> DisciplineListResponse:
    return DisciplineListResponse(items=clients_service.list_disciplines(session))


@router.post("/disciplines", response_model=DisciplineRead, status_code=201)
def create_discipline(
    payload: DisciplineCreateRequest,
    session: DbSession,
    subject: DisciplinesWriteSubject,
) -> DisciplineRead:
    discipline = clients_service.create_discipline(session, payload, actor_id=subject.user.id)
    session.commit()
    return discipline


@router.get("/disciplines/{discipline_id}", response_model=DisciplineRead)
def get_discipline(
    discipline_id: str,
    session: DbSession,
    _subject: DisciplinesReadSubject,
) -> DisciplineRead:
    return clients_service.get_discipline(session, discipline_id)


@router.patch("/disciplines/{discipline_id}", response_model=DisciplineRead)
def update_discipline(
    discipline_id: str,
    payload: DisciplineUpdateRequest,
    session: DbSession,
    subject: DisciplinesWriteSubject,
) -> DisciplineRead:
    discipline = clients_service.update_discipline(
        session,
        discipline_id,
        payload,
        actor_id=subject.user.id,
    )
    session.commit()
    return discipline
