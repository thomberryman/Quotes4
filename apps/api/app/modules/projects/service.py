from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.datetimes import same_timestamp
from app.core.errors import ApiProblemException
from app.models import (
    Company,
    Contact,
    ContactRole,
    Discipline,
    LossReason,
    Project,
    ProjectBenchmarkDisciplineSummary,
    ProjectBenchmarkSummary,
    ProjectContact,
    ProjectDiscipline,
    ProjectMetadata,
    ProjectOutcome,
    ProjectParty,
    ProjectScheduleRange,
    User,
)
from app.models.enums import ProjectOutcomeType, ProjectStatus
from app.modules.audit.service import audit_service
from app.modules.comparables.benchmark_summary import build_benchmark_summary
from app.modules.projects.schemas import (
    ProjectActualsVsQuoteRead,
    ProjectContactRead,
    ProjectContactsReplaceRequest,
    ProjectCreateRequest,
    ProjectDisciplineRead,
    ProjectDisciplinesReplaceRequest,
    ProjectMetadataPutRequest,
    ProjectMetadataRead,
    ProjectOutcomeCreateRequest,
    ProjectOutcomeRead,
    ProjectPartiesReplaceRequest,
    ProjectPartyRead,
    ProjectRead,
    ProjectScheduleRangeRead,
    ProjectScheduleRangesReplaceRequest,
    ProjectSummary,
    ProjectUpdateRequest,
)


class ProjectsService:
    def list_projects(self, session: Session) -> list[ProjectSummary]:
        projects = list(session.scalars(select(Project).order_by(Project.updated_at.desc())))
        return [self._serialize_summary(session, project) for project in projects]

    def get_project(self, session: Session, project_id: str) -> ProjectRead:
        project = session.get(Project, project_id)
        if project is None:
            raise ApiProblemException(
                404,
                f"Project '{project_id}' was not found.",
                "Project Not Found",
            )
        return self._serialize_project(session, project)

    def get_project_actuals_vs_quote(
        self,
        session: Session,
        project_id: str,
    ) -> ProjectActualsVsQuoteRead:
        result = session.execute(
            select(Project)
            .options(
                selectinload(Project.benchmark_summary)
                .selectinload(ProjectBenchmarkSummary.discipline_summaries)
                .selectinload(ProjectBenchmarkDisciplineSummary.discipline)
            )
            .where(Project.id == project_id)
        )
        project = result.scalars().unique().one_or_none()
        if project is None:
            raise ApiProblemException(
                404,
                f"Project '{project_id}' was not found.",
                "Project Not Found",
            )
        return ProjectActualsVsQuoteRead(
            project_id=project.id,
            project_name=project.name,
            benchmark_summary=build_benchmark_summary(project.benchmark_summary),
        )

    def create_project(
        self,
        session: Session,
        payload: ProjectCreateRequest,
        *,
        actor_id: str,
    ) -> ProjectRead:
        self._ensure_project_code_available(session, payload.code)
        self._validate_project_dates(payload.start_date, payload.end_date)
        self._require_user(session, payload.bid_owner_user_id)
        project = Project(
            code=payload.code,
            name=payload.name,
            status=payload.status,
            pipeline_stage_key=payload.pipeline_stage_key,
            bid_owner_user_id=payload.bid_owner_user_id,
            strategic_account_flag=payload.strategic_account_flag,
            description=payload.description,
            quote_currency_code=payload.quote_currency_code,
            start_date=payload.start_date,
            end_date=payload.end_date,
            bid_due_date=payload.bid_due_date,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        session.add(project)
        session.flush()
        audit_service.record(
            session,
            action="project.created",
            entity_type="project",
            entity_id=project.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Created project {project.name}.",
            after=self._serialize_project(session, project).model_dump(mode="json"),
        )
        return self._serialize_project(session, project)

    def update_project(
        self,
        session: Session,
        project_id: str,
        payload: ProjectUpdateRequest,
        *,
        actor_id: str,
    ) -> ProjectRead:
        project = self._get_project_entity(session, project_id)
        self._assert_current(project.updated_at, payload.expected_updated_at)
        before = self._serialize_project(session, project).model_dump(mode="json")
        next_start_date = (
            payload.start_date
            if "start_date" in payload.model_fields_set
            else project.start_date
        )
        next_end_date = (
            payload.end_date if "end_date" in payload.model_fields_set else project.end_date
        )
        self._validate_project_dates(next_start_date, next_end_date)
        if "code" in payload.model_fields_set:
            self._ensure_project_code_available(session, payload.code, project.id)
            project.code = payload.code
        if "bid_owner_user_id" in payload.model_fields_set:
            self._require_user(session, payload.bid_owner_user_id)
        for field in (
            "name",
            "status",
            "pipeline_stage_key",
            "bid_owner_user_id",
            "strategic_account_flag",
            "description",
            "quote_currency_code",
            "start_date",
            "end_date",
            "bid_due_date",
            "bid_submitted_at",
            "awarded_at",
            "lost_at",
            "active_at",
            "completed_at",
            "archived_at",
        ):
            if field in payload.model_fields_set:
                setattr(project, field, getattr(payload, field))
        project.updated_by_id = actor_id
        session.flush()
        audit_service.record(
            session,
            action="project.updated",
            entity_type="project",
            entity_id=project.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Updated project {project.name}.",
            before=before,
            after=self._serialize_project(session, project).model_dump(mode="json"),
        )
        return self._serialize_project(session, project)

    def put_metadata(
        self,
        session: Session,
        project_id: str,
        payload: ProjectMetadataPutRequest,
        *,
        actor_id: str,
    ) -> ProjectRead:
        project = self._get_project_entity(session, project_id)
        self._assert_current(project.updated_at, payload.expected_updated_at)
        metadata_record = session.scalar(
            select(ProjectMetadata).where(ProjectMetadata.project_id == project.id)
        )
        if metadata_record is None:
            metadata_record = ProjectMetadata(project_id=project.id)
            session.add(metadata_record)
            session.flush()
        for field in (
            "content_type",
            "content_subtype",
            "genre",
            "format_type",
            "project_format_key",
            "runtime_minutes",
            "duration_weeks",
            "episode_count",
            "territory",
            "language",
            "budget_target",
        ):
            if field in payload.model_fields_set:
                setattr(metadata_record, field, getattr(payload, field))
        if "metadata" in payload.model_fields_set:
            metadata_record.metadata_json = payload.metadata
        self._touch_project(project, actor_id)
        session.flush()
        audit_service.record(
            session,
            action="project.metadata.put",
            entity_type="project",
            entity_id=project.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Replaced metadata for {project.name}.",
        )
        return self._serialize_project(session, project)

    def replace_parties(
        self,
        session: Session,
        project_id: str,
        payload: ProjectPartiesReplaceRequest,
        *,
        actor_id: str,
    ) -> ProjectRead:
        project = self._get_project_entity(session, project_id)
        self._assert_current(project.updated_at, payload.expected_updated_at)
        self._validate_party_items(session, payload.items)
        session.execute(delete(ProjectParty).where(ProjectParty.project_id == project.id))
        for item in payload.items:
            session.add(
                ProjectParty(
                    project_id=project.id,
                    company_id=item.company_id,
                    role=item.role,
                    is_primary=item.is_primary,
                    notes=item.notes,
                )
            )
        self._touch_project(project, actor_id)
        session.flush()
        audit_service.record(
            session,
            action="project.parties.replaced",
            entity_type="project",
            entity_id=project.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Replaced project parties for {project.name}.",
        )
        return self._serialize_project(session, project)

    def replace_contacts(
        self,
        session: Session,
        project_id: str,
        payload: ProjectContactsReplaceRequest,
        *,
        actor_id: str,
    ) -> ProjectRead:
        project = self._get_project_entity(session, project_id)
        self._assert_current(project.updated_at, payload.expected_updated_at)
        self._validate_contact_items(session, payload.items)
        session.execute(delete(ProjectContact).where(ProjectContact.project_id == project.id))
        for item in payload.items:
            session.add(
                ProjectContact(
                    project_id=project.id,
                    contact_id=item.contact_id,
                    company_id=item.company_id,
                    contact_role_id=item.contact_role_id,
                    job_title=item.job_title,
                    is_primary=item.is_primary,
                    notes=item.notes,
                )
            )
        self._touch_project(project, actor_id)
        session.flush()
        audit_service.record(
            session,
            action="project.contacts.replaced",
            entity_type="project",
            entity_id=project.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Replaced project contacts for {project.name}.",
        )
        return self._serialize_project(session, project)

    def replace_disciplines(
        self,
        session: Session,
        project_id: str,
        payload: ProjectDisciplinesReplaceRequest,
        *,
        actor_id: str,
    ) -> ProjectRead:
        project = self._get_project_entity(session, project_id)
        self._assert_current(project.updated_at, payload.expected_updated_at)
        self._validate_discipline_items(session, payload.items)
        session.execute(delete(ProjectDiscipline).where(ProjectDiscipline.project_id == project.id))
        now = datetime.now(UTC)
        for item in payload.items:
            session.add(
                ProjectDiscipline(
                    project_id=project.id,
                    discipline_id=item.discipline_id,
                    is_primary=item.is_primary,
                    created_at=now,
                )
            )
        self._touch_project(project, actor_id)
        session.flush()
        audit_service.record(
            session,
            action="project.disciplines.replaced",
            entity_type="project",
            entity_id=project.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Replaced project disciplines for {project.name}.",
        )
        return self._serialize_project(session, project)

    def replace_schedule_ranges(
        self,
        session: Session,
        project_id: str,
        payload: ProjectScheduleRangesReplaceRequest,
        *,
        actor_id: str,
    ) -> ProjectRead:
        project = self._get_project_entity(session, project_id)
        self._assert_current(project.updated_at, payload.expected_updated_at)
        self._validate_schedule_range_items(session, payload.items)
        session.execute(
            delete(ProjectScheduleRange).where(ProjectScheduleRange.project_id == project.id)
        )
        for item in payload.items:
            session.add(
                ProjectScheduleRange(
                    project_id=project.id,
                    discipline_id=item.discipline_id,
                    label=item.label,
                    start_date=item.start_date,
                    end_date=item.end_date,
                    allocation_percent=item.allocation_percent,
                    notes=item.notes,
                )
            )
        self._touch_project(project, actor_id)
        session.flush()
        audit_service.record(
            session,
            action="project.schedule_ranges.replaced",
            entity_type="project",
            entity_id=project.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Replaced project schedule ranges for {project.name}.",
        )
        return self._serialize_project(session, project)

    def add_outcome(
        self,
        session: Session,
        project_id: str,
        payload: ProjectOutcomeCreateRequest,
        *,
        actor_id: str,
    ) -> ProjectRead:
        project = self._get_project_entity(session, project_id)
        if payload.competitor_company_id is not None:
            self._require_company(session, payload.competitor_company_id)
        if (
            payload.loss_reason_id is not None
            and session.get(LossReason, payload.loss_reason_id) is None
        ):
            raise ApiProblemException(
                422,
                f"Loss reason '{payload.loss_reason_id}' was not found.",
                "Invalid Loss Reason",
            )
        outcome = ProjectOutcome(
            project_id=project.id,
            outcome_type=payload.outcome_type,
            effective_at=payload.effective_at,
            competitor_company_id=payload.competitor_company_id,
            loss_reason_id=payload.loss_reason_id,
            notes=payload.notes,
            recorded_by_id=actor_id,
            created_at=datetime.now(UTC),
        )
        session.add(outcome)
        self._apply_outcome_to_project(
            project,
            payload.outcome_type,
            payload.effective_at,
            actor_id,
        )
        session.flush()
        audit_service.record(
            session,
            action="project.outcome.created",
            entity_type="project",
            entity_id=project.id,
            actor_id=actor_id,
            project_id=project.id,
            summary=f"Recorded {payload.outcome_type.value} outcome for {project.name}.",
            after={"outcomeType": payload.outcome_type.value},
        )
        return self._serialize_project(session, project)

    def _serialize_summary(self, session: Session, project: Project) -> ProjectSummary:
        primary_client_name = session.scalar(
            select(Company.name)
            .join(ProjectParty, ProjectParty.company_id == Company.id)
            .where(
                ProjectParty.project_id == project.id,
                ProjectParty.role == "client",
                ProjectParty.is_primary.is_(True),
            )
        )
        return ProjectSummary(
            id=project.id,
            code=project.code,
            name=project.name,
            status=project.status,
            pipeline_stage_key=project.pipeline_stage_key,
            primary_client_name=primary_client_name,
            quote_currency_code=project.quote_currency_code,
            updated_at=project.updated_at,
        )

    def _serialize_project(self, session: Session, project: Project) -> ProjectRead:
        metadata_record = session.scalar(
            select(ProjectMetadata).where(ProjectMetadata.project_id == project.id)
        )
        parties = list(
            session.execute(
                select(ProjectParty, Company.name)
                .join(Company, Company.id == ProjectParty.company_id)
                .where(ProjectParty.project_id == project.id)
                .order_by(ProjectParty.role, ProjectParty.is_primary.desc(), Company.name)
            )
        )
        contacts = list(
            session.execute(
                select(ProjectContact, Contact.full_name, Company.name, ContactRole.label)
                .join(Contact, Contact.id == ProjectContact.contact_id)
                .outerjoin(Company, Company.id == ProjectContact.company_id)
                .outerjoin(ContactRole, ContactRole.id == ProjectContact.contact_role_id)
                .where(ProjectContact.project_id == project.id)
                .order_by(ProjectContact.is_primary.desc(), Contact.full_name)
            )
        )
        disciplines = list(
            session.execute(
                select(ProjectDiscipline, Discipline.code, Discipline.name)
                .join(Discipline, Discipline.id == ProjectDiscipline.discipline_id)
                .where(ProjectDiscipline.project_id == project.id)
                .order_by(
                    ProjectDiscipline.is_primary.desc(),
                    Discipline.sort_order,
                    Discipline.name,
                )
            )
        )
        schedule_ranges = list(
            session.execute(
                select(ProjectScheduleRange, Discipline.name)
                .outerjoin(Discipline, Discipline.id == ProjectScheduleRange.discipline_id)
                .where(ProjectScheduleRange.project_id == project.id)
                .order_by(ProjectScheduleRange.start_date, ProjectScheduleRange.label)
            )
        )
        outcomes = list(
            session.execute(
                select(ProjectOutcome, Company.name)
                .outerjoin(Company, Company.id == ProjectOutcome.competitor_company_id)
                .where(ProjectOutcome.project_id == project.id)
                .order_by(ProjectOutcome.effective_at.desc())
            )
        )
        return ProjectRead(
            id=project.id,
            code=project.code,
            name=project.name,
            status=project.status,
            pipeline_stage_key=project.pipeline_stage_key,
            bid_owner_user_id=project.bid_owner_user_id,
            strategic_account_flag=project.strategic_account_flag,
            description=project.description,
            quote_currency_code=project.quote_currency_code,
            start_date=project.start_date,
            end_date=project.end_date,
            bid_due_date=project.bid_due_date,
            bid_submitted_at=project.bid_submitted_at,
            awarded_at=project.awarded_at,
            lost_at=project.lost_at,
            active_at=project.active_at,
            completed_at=project.completed_at,
            archived_at=project.archived_at,
            created_at=project.created_at,
            updated_at=project.updated_at,
            metadata=(
                ProjectMetadataRead(
                    content_type=metadata_record.content_type,
                    content_subtype=metadata_record.content_subtype,
                    genre=metadata_record.genre,
                    format_type=metadata_record.format_type,
                    project_format_key=metadata_record.project_format_key,
                    runtime_minutes=metadata_record.runtime_minutes,
                    duration_weeks=metadata_record.duration_weeks,
                    episode_count=metadata_record.episode_count,
                    territory=metadata_record.territory,
                    language=metadata_record.language,
                    budget_target=float(metadata_record.budget_target)
                    if metadata_record and metadata_record.budget_target is not None
                    else None,
                    metadata=metadata_record.metadata_json,
                )
                if metadata_record is not None
                else None
            ),
            parties=[
                ProjectPartyRead(
                    id=party.id,
                    company_id=party.company_id,
                    company_name=company_name,
                    role=party.role,
                    is_primary=party.is_primary,
                    notes=party.notes,
                )
                for party, company_name in parties
            ],
            contacts=[
                ProjectContactRead(
                    id=project_contact.id,
                    contact_id=project_contact.contact_id,
                    contact_name=contact_name,
                    company_id=project_contact.company_id,
                    company_name=company_name,
                    contact_role_id=project_contact.contact_role_id,
                    contact_role_label=contact_role_label,
                    job_title=project_contact.job_title,
                    is_primary=project_contact.is_primary,
                    notes=project_contact.notes,
                )
                for project_contact, contact_name, company_name, contact_role_label in contacts
            ],
            disciplines=[
                ProjectDisciplineRead(
                    id=project_discipline.id,
                    discipline_id=project_discipline.discipline_id,
                    discipline_code=discipline_code,
                    discipline_name=discipline_name,
                    is_primary=project_discipline.is_primary,
                )
                for project_discipline, discipline_code, discipline_name in disciplines
            ],
            schedule_ranges=[
                ProjectScheduleRangeRead(
                    id=schedule_range.id,
                    discipline_id=schedule_range.discipline_id,
                    discipline_name=discipline_name,
                    label=schedule_range.label,
                    start_date=schedule_range.start_date,
                    end_date=schedule_range.end_date,
                    allocation_percent=float(schedule_range.allocation_percent)
                    if schedule_range.allocation_percent is not None
                    else None,
                    notes=schedule_range.notes,
                )
                for schedule_range, discipline_name in schedule_ranges
            ],
            outcomes=[
                ProjectOutcomeRead(
                    id=outcome.id,
                    outcome_type=outcome.outcome_type,
                    effective_at=outcome.effective_at,
                    competitor_company_id=outcome.competitor_company_id,
                    competitor_company_name=competitor_company_name,
                    loss_reason_id=outcome.loss_reason_id,
                    notes=outcome.notes,
                    recorded_by_id=outcome.recorded_by_id,
                    created_at=outcome.created_at,
                )
                for outcome, competitor_company_name in outcomes
            ],
        )

    def _get_project_entity(self, session: Session, project_id: str) -> Project:
        project = session.get(Project, project_id)
        if project is None:
            raise ApiProblemException(
                404,
                f"Project '{project_id}' was not found.",
                "Project Not Found",
            )
        return project

    def _ensure_project_code_available(
        self,
        session: Session,
        code: str | None,
        current_project_id: str | None = None,
    ) -> None:
        if code is None:
            return
        existing = session.scalar(select(Project).where(Project.code == code))
        if existing is not None and existing.id != current_project_id:
            raise ApiProblemException(
                409,
                "A project with that code already exists.",
                "Project Exists",
            )

    def _touch_project(self, project: Project, actor_id: str) -> None:
        project.updated_by_id = actor_id
        project.updated_at = datetime.now(UTC)

    def _require_user(self, session: Session, user_id: str | None) -> None:
        if user_id is None:
            return
        if session.get(User, user_id) is None:
            raise ApiProblemException(
                422,
                f"User '{user_id}' was not found.",
                "Invalid Project User",
            )

    def _validate_party_items(self, session: Session, items) -> None:
        primary_roles: set[str] = set()
        for item in items:
            self._require_company(session, item.company_id)
            if item.is_primary:
                role_key = item.role.value
                if role_key in primary_roles:
                    raise ApiProblemException(
                        422,
                        f"Only one primary company is allowed for role '{role_key}'.",
                        "Invalid Project Parties",
                    )
                primary_roles.add(role_key)

    def _validate_contact_items(self, session: Session, items) -> None:
        for item in items:
            if session.get(Contact, item.contact_id) is None:
                raise ApiProblemException(
                    422,
                    f"Contact '{item.contact_id}' was not found.",
                    "Invalid Project Contacts",
                )
            if item.company_id is not None:
                self._require_company(session, item.company_id)
            if (
                item.contact_role_id is not None
                and session.get(ContactRole, item.contact_role_id) is None
            ):
                raise ApiProblemException(
                    422,
                    f"Contact role '{item.contact_role_id}' was not found.",
                    "Invalid Project Contacts",
                )

    def _validate_discipline_items(self, session: Session, items) -> None:
        seen_primary = False
        for item in items:
            if session.get(Discipline, item.discipline_id) is None:
                raise ApiProblemException(
                    422,
                    f"Discipline '{item.discipline_id}' was not found.",
                    "Invalid Project Disciplines",
                )
            if item.is_primary:
                if seen_primary:
                    raise ApiProblemException(
                        422,
                        "Only one primary discipline is allowed.",
                        "Invalid Project Disciplines",
                    )
                seen_primary = True

    def _validate_schedule_range_items(self, session: Session, items) -> None:
        for item in items:
            if (
                item.discipline_id is not None
                and session.get(Discipline, item.discipline_id) is None
            ):
                raise ApiProblemException(
                    422,
                    f"Discipline '{item.discipline_id}' was not found.",
                    "Invalid Project Schedule Ranges",
                )
            if item.end_date < item.start_date:
                raise ApiProblemException(
                    422,
                    "Schedule range end date cannot be earlier than start date.",
                    "Invalid Project Schedule Ranges",
                )

    def _validate_project_dates(
        self,
        start_date: date | None,
        end_date: date | None,
    ) -> None:
        if start_date is not None and end_date is not None and end_date < start_date:
            raise ApiProblemException(
                422,
                "Project end date cannot be earlier than start date.",
                "Invalid Project Dates",
            )

    def _require_company(self, session: Session, company_id: str) -> Company:
        company = session.get(Company, company_id)
        if company is None:
            raise ApiProblemException(
                422,
                f"Company '{company_id}' was not found.",
                "Invalid Company",
            )
        return company

    def _apply_outcome_to_project(
        self,
        project: Project,
        outcome_type: ProjectOutcomeType,
        effective_at: datetime,
        actor_id: str,
    ) -> None:
        self._touch_project(project, actor_id)
        if outcome_type == ProjectOutcomeType.awarded:
            project.status = ProjectStatus.awarded
            project.awarded_at = effective_at
        elif outcome_type == ProjectOutcomeType.lost:
            project.status = ProjectStatus.lost
            project.lost_at = effective_at
        else:
            project.status = ProjectStatus.bid
            project.bid_submitted_at = effective_at

    def _assert_current(self, current: datetime, expected: datetime) -> None:
        if not same_timestamp(current, expected):
            raise ApiProblemException(
                409,
                "The project was modified by another request. Reload and retry.",
                "Stale Update",
            )


projects_service = ProjectsService()
