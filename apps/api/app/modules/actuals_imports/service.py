from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ApiProblemException
from app.models import (
    ActualMappingDecision,
    ActualMappingRule,
    CetaImport,
    CetaImportRow,
    CetaImportRowCandidate,
    CetaImportRowIssue,
    Discipline,
    Forecast,
    ForecastVersion,
    MappedActual,
    Project,
    ProjectExternalReference,
    Quote,
    QuoteVersion,
    ReferenceDataValue,
    ReferenceTermAlias,
    UploadedFile,
)
from app.models.enums import (
    ActualMappingApprovalAction,
    ActualMappingDecisionStatus,
    BackgroundJobStatus,
    CetaImportCandidateDimension,
    CetaImportCoverageMode,
    CetaImportIssueSeverity,
    CetaImportStatus,
    CetaRowFinancialType,
    CetaRowStatus,
    MappedActualChangeType,
    UploadedFileCategory,
    UploadedFileStatus,
)
from app.modules.actuals_imports.schemas import (
    ActualsImportBatchDetailRead,
    ActualsImportBatchListResponse,
    ActualsImportBatchSummaryRead,
    ActualsImportCandidateRead,
    ActualsImportDecisionRead,
    ActualsImportIssueRead,
    ActualsImportReviewBucketRead,
    ActualsImportRowListResponse,
    ActualsImportRowRead,
    ActualsImportVarianceMonthRead,
    ActualsImportVarianceProjectRead,
    ApproveActualsImportBatchRequest,
    ApproveActualsImportBatchResponse,
    CreateActualsImportBatchRequest,
    RejectActualsImportBatchRequest,
    RejectActualsImportBatchResponse,
    SnapshotWithdrawalCandidateRead,
    UpdateActualsImportRowDecisionRequest,
    WorkerActualsImportResultRequest,
)
from app.modules.audit.service import audit_service
from app.modules.files.service import files_service
from app.modules.jobs.service import job_service

REVIEW_QUEUE_LABELS = {
    "blocking": "Blocking",
    "ambiguous": "Ambiguous",
    "repeat_match": "Repeat Match",
    "changed_repeat": "Changed Repeat",
    "ready": "Ready",
    "rejected": "Rejected",
}

ROW_LOAD_OPTIONS = (
    selectinload(CetaImport.rows).selectinload(CetaImportRow.issues),
    selectinload(CetaImport.rows).selectinload(CetaImportRow.candidates),
    selectinload(CetaImport.rows).selectinload(CetaImportRow.mapping_decisions),
    selectinload(CetaImport.rows).selectinload(CetaImportRow.suggested_project),
    selectinload(CetaImport.rows).selectinload(CetaImportRow.suggested_discipline),
    selectinload(CetaImport.issues),
    selectinload(CetaImport.project),
    selectinload(CetaImport.uploaded_file),
)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().lower().split())
    return normalized or None


def _month_key(value) -> str | None:
    if value is None:
        return None
    return f"{value.year:04d}-{value.month:02d}"


def _to_float(value: object | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _hash_payload(value: dict[str, object]) -> str:
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


class ActualsImportService:
    def create_batch(
        self,
        session: Session,
        payload: CreateActualsImportBatchRequest,
        *,
        actor_id: str,
    ) -> ActualsImportBatchDetailRead:
        uploaded_file = session.get(UploadedFile, payload.uploaded_file_id)
        if uploaded_file is None:
            raise ApiProblemException(
                404,
                f"File '{payload.uploaded_file_id}' was not found.",
                "File Not Found",
            )
        if uploaded_file.status != UploadedFileStatus.uploaded:
            raise ApiProblemException(
                409,
                "Finalize the upload before creating an actuals import batch.",
                "Upload Not Finalized",
            )
        if uploaded_file.file_category != UploadedFileCategory.ceta_export:
            raise ApiProblemException(
                422,
                "Actuals import batches require an uploaded CETA export.",
                "Invalid File Category",
            )
        if payload.project_id is not None and session.get(Project, payload.project_id) is None:
            raise ApiProblemException(
                422,
                f"Project '{payload.project_id}' was not found.",
                "Invalid Project",
            )

        batch = CetaImport(
            project_id=payload.project_id,
            uploaded_file_id=payload.uploaded_file_id,
            source_system=payload.source_system,
            source_export_id=payload.source_export_id,
            source_exported_at=payload.source_exported_at,
            coverage_mode=payload.coverage_mode,
            coverage_start=payload.coverage_start,
            coverage_end=payload.coverage_end,
            parser_profile_hint=payload.parser_profile_hint,
            status=CetaImportStatus.uploaded,
            parse_summary_json={"rowCount": 0, "issueCount": 0, "candidateCount": 0},
            review_summary_json={"approvedCount": 0, "rejectedCount": 0},
            notes=payload.notes,
            uploaded_by_id=actor_id,
            uploaded_at=datetime.now(UTC),
        )
        session.add(batch)
        session.flush()
        audit_service.record(
            session,
            action="actuals_import.batch.created",
            entity_type="ceta_import",
            entity_id=batch.id,
            actor_id=actor_id,
            project_id=batch.project_id,
            summary=f"Created CETA import batch {batch.id}.",
            after={
                "coverageMode": batch.coverage_mode.value,
                "uploadedFileId": batch.uploaded_file_id,
            },
        )
        session.refresh(batch)
        return self.get_batch(session, batch.id)

    def list_batches(self, session: Session) -> ActualsImportBatchListResponse:
        batches = list(
            session.scalars(
                select(CetaImport)
                .options(*ROW_LOAD_OPTIONS)
                .order_by(CetaImport.uploaded_at.desc())
            )
        )
        return ActualsImportBatchListResponse(
            items=[self._serialize_batch_summary(session, batch) for batch in batches]
        )

    def get_batch(self, session: Session, batch_id: str) -> ActualsImportBatchDetailRead:
        batch = self._get_batch(session, batch_id)
        return self._serialize_batch_detail(session, batch)

    def list_rows(
        self,
        session: Session,
        batch_id: str,
        *,
        review_queue: str | None = None,
    ) -> ActualsImportRowListResponse:
        batch = self._get_batch(session, batch_id)
        items = [
            self._serialize_row(row)
            for row in sorted(batch.rows, key=lambda item: item.row_number)
            if review_queue is None or self._review_queue(row) == review_queue
        ]
        return ActualsImportRowListResponse(items=items)

    def build_process_job(
        self,
        session: Session,
        batch_id: str,
    ):
        batch = self._get_batch(session, batch_id)
        if batch.status not in {CetaImportStatus.uploaded, CetaImportStatus.failed}:
            raise ApiProblemException(
                409,
                "Only uploaded or failed batches can be processed.",
                "Batch Not Processable",
            )
        uploaded_file = batch.uploaded_file
        job = job_service.enqueue(
            session,
            queue_name="ceta_import",
            payload={
                "batchId": batch.id,
                "uploadedFileId": batch.uploaded_file_id,
                "objectKey": uploaded_file.storage_key,
                "parserProfileHint": batch.parser_profile_hint,
                "coverageMode": batch.coverage_mode.value,
            },
            related_entity_type="ceta_import",
            related_entity_id=batch.id,
            deduplication_key=job_service.build_deduplication_key(
                queue_name="ceta_import",
                related_entity_type="ceta_import",
                related_entity_id=batch.id,
            ),
        )
        audit_service.record(
            session,
            action="actuals_import.batch.process_requested",
            entity_type="ceta_import",
            entity_id=batch.id,
            project_id=batch.project_id,
            summary=f"Queued CETA import batch {batch.id} for parsing.",
            metadata={"jobId": job.id},
        )
        return job

    def apply_worker_result(
        self,
        session: Session,
        batch_id: str,
        payload: WorkerActualsImportResultRequest,
    ) -> ActualsImportBatchDetailRead:
        batch = self._get_batch(session, batch_id)
        if batch.status not in {CetaImportStatus.uploaded, CetaImportStatus.failed}:
            raise ApiProblemException(
                409,
                "Only uploaded or failed batches can accept worker results.",
                "Worker Result Rejected",
            )
        job = job_service.get_related_job(
            session,
            payload.job_id,
            related_entity_type="ceta_import",
            related_entity_id=batch.id,
            queue_name="ceta_import",
        )
        if job is None:
            raise ApiProblemException(
                409,
                "Worker result did not match the batch's queued job.",
                "Worker Result Rejected",
            )
        if job.status not in {BackgroundJobStatus.queued, BackgroundJobStatus.running}:
            raise ApiProblemException(
                409,
                "Worker result was received for a job that is no longer active.",
                "Worker Result Rejected",
            )
        if batch.rows:
            raise ApiProblemException(
                409,
                "This batch already has staged rows.",
                "Worker Result Rejected",
            )
        if payload.status == "failed":
            batch.status = CetaImportStatus.failed
            batch.parse_summary_json = {
                "rowCount": 0,
                "issueCount": 1,
                "candidateCount": 0,
                "failureCode": payload.failure_code,
            }
            session.add(
                CetaImportRowIssue(
                    ceta_import_id=batch.id,
                    severity=CetaImportIssueSeverity.fatal,
                    issue_code=payload.failure_code or "parse_failed",
                    message=payload.failure_message or "The CETA parser failed.",
                    details_json={"jobId": payload.job_id},
                )
            )
            audit_service.record(
                session,
                action="actuals_import.batch.failed",
                entity_type="ceta_import",
                entity_id=batch.id,
                project_id=batch.project_id,
                summary=f"CETA import batch {batch.id} failed during worker parsing.",
                metadata={"jobId": payload.job_id, "failureCode": payload.failure_code},
            )
            job_service.mark_failed(
                session,
                payload.job_id,
                last_error=payload.failure_message or payload.failure_code,
            )
            session.flush()
            return self._serialize_batch_detail(session, batch)

        batch.parser_profile_detected = payload.parser_profile
        batch.source_system = payload.source_system or batch.source_system
        batch.coverage_start = payload.coverage_start or batch.coverage_start
        batch.coverage_end = payload.coverage_end or batch.coverage_end

        for issue in payload.batch_issues:
            session.add(
                CetaImportRowIssue(
                    ceta_import_id=batch.id,
                    severity=issue.severity,
                    issue_code=issue.issue_code,
                    field_name=issue.field_name,
                    message=issue.message,
                    details_json=issue.details,
                )
            )

        for row_payload in sorted(payload.rows, key=lambda item: item.row_number):
            row = CetaImportRow(
                ceta_import_id=batch.id,
                row_number=row_payload.row_number,
                source_row_uid=row_payload.source_row_uid,
                row_hash=row_payload.row_hash,
                business_key_hash=row_payload.business_key_hash,
                duplicate_group_key=row_payload.duplicate_group_key,
                external_project_code=row_payload.external_project_code,
                normalized_project_code=row_payload.normalized_project_code,
                work_date=row_payload.work_date,
                posting_date=row_payload.posting_date,
                source_discipline_code=row_payload.source_discipline_code,
                description=row_payload.description,
                normalized_description=row_payload.normalized_description,
                vendor_name=row_payload.vendor_name,
                normalized_vendor_name=row_payload.normalized_vendor_name,
                amount=row_payload.amount,
                currency_code=row_payload.currency_code,
                financial_type=row_payload.financial_type,
                status=CetaRowStatus.unmatched,
                raw_payload_json=row_payload.raw_payload,
            )
            session.add(row)
            session.flush()
            for issue in row_payload.issues:
                session.add(
                    CetaImportRowIssue(
                        ceta_import_id=batch.id,
                        ceta_import_row_id=row.id,
                        severity=issue.severity,
                        issue_code=issue.issue_code,
                        field_name=issue.field_name,
                        message=issue.message,
                        details_json=issue.details,
                    )
                )

        session.flush()
        session.refresh(batch)
        batch.status = CetaImportStatus.in_review
        batch.reviewed_at = datetime.now(UTC)
        self._refresh_batch_candidates(session, batch)
        batch.parse_summary_json = self._build_parse_summary(batch)
        batch.review_summary_json = self._build_review_summary(batch)
        audit_service.record(
            session,
            action="actuals_import.batch.parsed",
            entity_type="ceta_import",
            entity_id=batch.id,
            project_id=batch.project_id,
            summary=f"Parsed CETA import batch {batch.id} into staged rows.",
            metadata={"jobId": payload.job_id, "rowCount": len(batch.rows)},
        )
        job_service.mark_succeeded(session, payload.job_id)
        session.flush()
        return self._serialize_batch_detail(session, batch)

    def update_row_decision(
        self,
        session: Session,
        row_id: str,
        payload: UpdateActualsImportRowDecisionRequest,
        *,
        actor_id: str,
    ) -> ActualsImportRowRead:
        row = self._get_row(session, row_id)
        batch = row.ceta_import
        if batch.status != CetaImportStatus.in_review:
            raise ApiProblemException(
                409,
                "Only batches in review can accept row decisions.",
                "Batch Not Reviewable",
            )

        mapped_project_id = payload.mapped_project_id
        mapped_discipline_id = payload.mapped_discipline_id
        financial_type = payload.financial_type
        cost_category_key = payload.cost_category_key
        revenue_category_key = payload.revenue_category_key
        matched_existing_actual_id = (
            payload.matched_existing_actual_id or row.matched_current_actual_id
        )

        matched_existing_actual = None
        if matched_existing_actual_id is not None:
            matched_existing_actual = session.get(MappedActual, matched_existing_actual_id)
            if matched_existing_actual is None:
                raise ApiProblemException(
                    422,
                    f"Mapped actual '{matched_existing_actual_id}' was not found.",
                    "Invalid Actual Match",
                )
        if (
            payload.approval_action == ActualMappingApprovalAction.link_existing
            and matched_existing_actual is None
        ):
            raise ApiProblemException(
                422,
                "Linking an existing repeat requires a matched approved actual.",
                "Invalid Decision",
            )
        if payload.approval_action in {
            ActualMappingApprovalAction.post_new,
            ActualMappingApprovalAction.supersede_existing,
        }:
            if mapped_project_id is None and matched_existing_actual is not None:
                mapped_project_id = matched_existing_actual.project_id
            if financial_type is None:
                financial_type = row.financial_type
            if (
                payload.approval_action == ActualMappingApprovalAction.supersede_existing
                and matched_existing_actual is None
            ):
                raise ApiProblemException(
                    422,
                    "Superseding an existing actual requires a matched current actual.",
                    "Invalid Decision",
                )
            if mapped_project_id is None:
                raise ApiProblemException(
                    422,
                    "Posting an approved actual requires a mapped project.",
                    "Invalid Decision",
                )
            self._require_project(session, mapped_project_id)
        if mapped_discipline_id is not None:
            self._require_discipline(session, mapped_discipline_id)
        if financial_type == CetaRowFinancialType.cost and cost_category_key is None:
            raise ApiProblemException(
                422,
                "Cost rows require a cost category key before approval.",
                "Invalid Decision",
            )
        if financial_type == CetaRowFinancialType.revenue and revenue_category_key is None:
            raise ApiProblemException(
                422,
                "Revenue rows require a revenue category key before approval.",
                "Invalid Decision",
            )
        if cost_category_key is not None:
            self._require_reference_key(session, "actuals_mapping_category", cost_category_key)
        if revenue_category_key is not None:
            self._require_reference_key(session, "revenue_category", revenue_category_key)

        created_external_reference_id = None
        created_alias_id = None
        created_rule_id = None

        if (
            payload.save_project_external_reference
            and mapped_project_id
            and row.external_project_code
        ):
            external_reference = self._upsert_project_external_reference(
                session,
                project_id=mapped_project_id,
                source_system=batch.source_system or "ceta",
                external_value=row.external_project_code,
                actor_id=actor_id,
            )
            created_external_reference_id = external_reference.id
        if payload.save_category_alias:
            alias = self._create_alias_from_row(
                session,
                row,
                mapped_discipline_id=mapped_discipline_id,
                cost_category_key=cost_category_key,
                revenue_category_key=revenue_category_key,
                source_system=batch.source_system or "ceta",
                actor_id=actor_id,
            )
            created_alias_id = alias.id if alias is not None else None
        if payload.save_rule:
            rule = self._create_rule_from_row(
                session,
                row,
                rule_name=payload.rule_name,
                mapped_project_id=mapped_project_id,
                mapped_discipline_id=mapped_discipline_id,
                financial_type=financial_type,
                cost_category_key=cost_category_key,
                revenue_category_key=revenue_category_key,
                source_system=batch.source_system or "ceta",
                actor_id=actor_id,
            )
            created_rule_id = rule.id

        if (
            payload.approval_action == ActualMappingApprovalAction.link_existing
            and matched_existing_actual is not None
        ):
            mapped_project_id = mapped_project_id or matched_existing_actual.project_id
            mapped_discipline_id = mapped_discipline_id or matched_existing_actual.discipline_id
            financial_type = financial_type or matched_existing_actual.financial_type
            cost_category_key = cost_category_key or matched_existing_actual.cost_category_key
            revenue_category_key = (
                revenue_category_key or matched_existing_actual.revenue_category_key
            )

        decision = ActualMappingDecision(
            ceta_import_row_id=row.id,
            mapped_project_id=mapped_project_id,
            mapped_discipline_id=mapped_discipline_id,
            financial_type=financial_type,
            cost_category_key=cost_category_key,
            revenue_category_key=revenue_category_key,
            approval_action=payload.approval_action,
            decision_status=(
                ActualMappingDecisionStatus.rejected
                if payload.approval_action == ActualMappingApprovalAction.reject
                else ActualMappingDecisionStatus.approved
            ),
            mapping_method=payload.mapping_method,
            matched_existing_actual_id=matched_existing_actual_id,
            confidence_score=payload.confidence_score,
            reviewer_note=payload.reviewer_note,
            explanation_json=payload.explanation,
            created_rule_id=created_rule_id,
            created_alias_id=created_alias_id,
            created_external_reference_id=created_external_reference_id,
            mapped_by_id=actor_id,
        )
        session.add(decision)
        row.status = (
            CetaRowStatus.rejected
            if payload.approval_action == ActualMappingApprovalAction.reject
            else CetaRowStatus.mapped
        )
        row.matched_current_actual_id = matched_existing_actual_id
        batch.reviewed_by_id = actor_id
        batch.reviewed_at = datetime.now(UTC)
        session.flush()

        if (
            payload.save_project_external_reference
            or payload.save_category_alias
            or payload.save_rule
        ):
            self._refresh_batch_candidates(session, batch)

        batch.review_summary_json = self._build_review_summary(batch)
        audit_service.record(
            session,
            action="actuals_import.row.decision_saved",
            entity_type="ceta_import_row",
            entity_id=row.id,
            actor_id=actor_id,
            project_id=mapped_project_id or batch.project_id,
            summary=f"Saved review decision for CETA row {row.row_number}.",
            metadata={"batchId": batch.id, "approvalAction": payload.approval_action.value},
        )
        session.flush()
        return self._serialize_row(row)

    def approve_batch(
        self,
        session: Session,
        batch_id: str,
        payload: ApproveActualsImportBatchRequest,
        *,
        actor_id: str,
    ) -> ApproveActualsImportBatchResponse:
        batch = self._get_batch(session, batch_id)
        if batch.status != CetaImportStatus.in_review:
            raise ApiProblemException(
                409,
                "Only batches in review can be approved.",
                "Batch Not Reviewable",
            )

        decisions_by_row: dict[str, ActualMappingDecision] = {}
        unresolved_rows: list[CetaImportRow] = []
        for row in batch.rows:
            latest = self._latest_decision(row)
            if latest is None:
                unresolved_rows.append(row)
                continue
            if (
                self._has_blocking_issues(row)
                and latest.approval_action != ActualMappingApprovalAction.reject
            ):
                unresolved_rows.append(row)
                continue
            decisions_by_row[row.id] = latest
        if unresolved_rows:
            raise ApiProblemException(
                409,
                "Resolve all blocking rows and decisions before batch approval.",
                "Review Incomplete",
            )

        approved_actual_count = 0
        linked_repeat_count = 0
        superseded_actual_count = 0
        affected_project_ids: set[str] = set()

        for row in sorted(batch.rows, key=lambda item: item.row_number):
            decision = decisions_by_row[row.id]
            if decision.approval_action == ActualMappingApprovalAction.reject:
                row.status = CetaRowStatus.rejected
                continue
            if decision.approval_action == ActualMappingApprovalAction.link_existing:
                row.status = CetaRowStatus.approved
                linked_repeat_count += 1
                if decision.mapped_project_id:
                    affected_project_ids.add(decision.mapped_project_id)
                continue

            if decision.mapped_project_id is None or decision.financial_type is None:
                raise ApiProblemException(
                    409,
                    f"Row {row.row_number} is missing a final mapped project or financial type.",
                    "Review Incomplete",
                )

            previous_actual = None
            change_type = MappedActualChangeType.new
            if decision.approval_action == ActualMappingApprovalAction.supersede_existing:
                previous_actual = session.get(MappedActual, decision.matched_existing_actual_id)
                if previous_actual is None:
                    raise ApiProblemException(
                        409,
                        f"Row {row.row_number} is missing a valid current actual to supersede.",
                        "Review Incomplete",
                    )
                previous_actual.is_current = False
                change_type = MappedActualChangeType.corrected
                superseded_actual_count += 1

            mapped_actual = MappedActual(
                project_id=decision.mapped_project_id,
                discipline_id=decision.mapped_discipline_id,
                source_ceta_import_id=batch.id,
                source_ceta_import_row_id=row.id,
                mapping_decision_id=decision.id,
                work_date=row.work_date,
                posting_date=row.posting_date,
                description=row.description,
                vendor_name=row.vendor_name,
                amount=row.amount,
                currency_code=row.currency_code,
                financial_type=decision.financial_type,
                cost_category_key=decision.cost_category_key,
                revenue_category_key=decision.revenue_category_key,
                actual_business_key=row.business_key_hash,
                supersedes_mapped_actual_id=previous_actual.id
                if previous_actual is not None
                else None,
                is_current=True,
                change_type=change_type,
                mapped_by_id=actor_id,
                mapped_at=datetime.now(UTC),
            )
            session.add(mapped_actual)
            row.status = CetaRowStatus.approved
            approved_actual_count += 1
            affected_project_ids.add(decision.mapped_project_id)

        withdrawn_actual_count = 0
        if batch.coverage_mode == CetaImportCoverageMode.snapshot:
            allowed_withdrawals = {
                item.actual_id
                for item in self._build_snapshot_withdrawal_candidates(session, batch)
            }
            unexpected_withdrawals = sorted(
                set(payload.withdraw_actual_ids) - allowed_withdrawals
            )
            if unexpected_withdrawals:
                raise ApiProblemException(
                    422,
                    (
                        "Withdraw actual ids must come from the current batch's "
                        "snapshot withdrawal candidates."
                    ),
                    "Invalid Withdrawal Selection",
                )
            for actual_id in payload.withdraw_actual_ids:
                actual = session.get(MappedActual, actual_id)
                if actual is None or not actual.is_current:
                    continue
                actual.is_current = False
                actual.change_type = MappedActualChangeType.withdrawn
                withdrawn_actual_count += 1
                affected_project_ids.add(actual.project_id)

        batch.status = CetaImportStatus.approved
        batch.approved_by_id = actor_id
        batch.reviewed_by_id = actor_id
        batch.approved_at = datetime.now(UTC)
        batch.reviewed_at = batch.approved_at
        batch.review_summary_json = self._build_review_summary(batch)
        audit_service.record(
            session,
            action="actuals_import.batch.approved",
            entity_type="ceta_import",
            entity_id=batch.id,
            actor_id=actor_id,
            project_id=batch.project_id,
            summary=f"Approved CETA import batch {batch.id}.",
            metadata={
                "approvedActualCount": approved_actual_count,
                "linkedRepeatCount": linked_repeat_count,
                "withdrawnActualCount": withdrawn_actual_count,
            },
        )
        from app.modules.forecasts.service import forecast_service

        for project_id in sorted(affected_project_ids):
            forecast_service.recalculate_project(session, project_id, actor_id=actor_id)

        job_service.enqueue(
            session,
            queue_name="dashboard_refresh",
            payload={"batchId": batch.id},
            related_entity_type="ceta_import",
            related_entity_id=batch.id,
            deduplication_key=job_service.build_deduplication_key(
                queue_name="dashboard_refresh",
                related_entity_type="ceta_import",
                related_entity_id=batch.id,
            ),
        )
        for project_id in sorted(affected_project_ids):
            job_service.enqueue(
                session,
                queue_name="forecast_recalc",
                payload={"projectId": project_id},
                related_entity_type="project",
                related_entity_id=project_id,
                deduplication_key=job_service.build_deduplication_key(
                    queue_name="forecast_recalc",
                    related_entity_type="project",
                    related_entity_id=project_id,
                ),
            )

        return ApproveActualsImportBatchResponse(
            batch_id=batch.id,
            status=batch.status,
            approved_actual_count=approved_actual_count,
            linked_repeat_count=linked_repeat_count,
            superseded_actual_count=superseded_actual_count,
            withdrawn_actual_count=withdrawn_actual_count,
            affected_project_ids=sorted(affected_project_ids),
        )

    def reject_batch(
        self,
        session: Session,
        batch_id: str,
        payload: RejectActualsImportBatchRequest,
        *,
        actor_id: str,
    ) -> RejectActualsImportBatchResponse:
        batch = self._get_batch(session, batch_id)
        if batch.status not in {
            CetaImportStatus.uploaded,
            CetaImportStatus.in_review,
            CetaImportStatus.failed,
        }:
            raise ApiProblemException(
                409,
                "Only uploaded, in-review, or failed batches can be rejected.",
                "Batch Not Rejectable",
            )
        batch.status = CetaImportStatus.rejected
        batch.reviewed_by_id = actor_id
        batch.reviewed_at = datetime.now(UTC)
        batch.notes = payload.reason or batch.notes
        audit_service.record(
            session,
            action="actuals_import.batch.rejected",
            entity_type="ceta_import",
            entity_id=batch.id,
            actor_id=actor_id,
            project_id=batch.project_id,
            summary=f"Rejected CETA import batch {batch.id}.",
            metadata={"reason": payload.reason},
        )
        return RejectActualsImportBatchResponse(
            batch_id=batch.id,
            status=batch.status,
            reason=payload.reason,
        )

    def _get_batch(self, session: Session, batch_id: str) -> CetaImport:
        statement = select(CetaImport).options(*ROW_LOAD_OPTIONS).where(CetaImport.id == batch_id)
        batch = session.scalar(statement)
        if batch is None:
            raise ApiProblemException(
                404,
                f"Actuals import batch '{batch_id}' was not found.",
                "Batch Not Found",
            )
        return batch

    def _get_row(self, session: Session, row_id: str) -> CetaImportRow:
        statement = (
            select(CetaImportRow)
            .options(
                selectinload(CetaImportRow.issues),
                selectinload(CetaImportRow.candidates),
                selectinload(CetaImportRow.mapping_decisions),
                selectinload(CetaImportRow.suggested_project),
                selectinload(CetaImportRow.suggested_discipline),
                selectinload(CetaImportRow.ceta_import).selectinload(CetaImport.rows),
            )
            .where(CetaImportRow.id == row_id)
        )
        row = session.scalar(statement)
        if row is None:
            raise ApiProblemException(
                404,
                f"CETA import row '{row_id}' was not found.",
                "Row Not Found",
            )
        return row

    def _serialize_batch_summary(
        self,
        session: Session,
        batch: CetaImport,
    ) -> ActualsImportBatchSummaryRead:
        blocking_issue_count = sum(
            1
            for issue in batch.issues
            if issue.severity in {CetaImportIssueSeverity.blocking, CetaImportIssueSeverity.fatal}
        )
        blocking_issue_count += sum(
            1
            for row in batch.rows
            for issue in row.issues
            if issue.severity in {CetaImportIssueSeverity.blocking, CetaImportIssueSeverity.fatal}
        )
        return ActualsImportBatchSummaryRead(
            id=batch.id,
            status=batch.status,
            coverage_mode=batch.coverage_mode,
            project_id=batch.project_id,
            project_name=batch.project.name if batch.project is not None else None,
            uploaded_file_id=batch.uploaded_file_id,
            parser_profile_hint=batch.parser_profile_hint,
            parser_profile_detected=batch.parser_profile_detected,
            source_system=batch.source_system,
            source_export_id=batch.source_export_id,
            source_exported_at=batch.source_exported_at,
            coverage_start=batch.coverage_start,
            coverage_end=batch.coverage_end,
            row_count=len(batch.rows),
            blocking_issue_count=blocking_issue_count,
            parse_summary=batch.parse_summary_json or self._build_parse_summary(batch),
            review_summary=batch.review_summary_json or self._build_review_summary(batch),
            uploaded_at=batch.uploaded_at,
            reviewed_at=batch.reviewed_at,
            approved_at=batch.approved_at,
        )

    def _serialize_batch_detail(
        self, session: Session, batch: CetaImport
    ) -> ActualsImportBatchDetailRead:
        summary = self._serialize_batch_summary(session, batch)
        file_read = files_service.get(session, batch.uploaded_file_id)
        if file_read is None:
            raise ApiProblemException(
                404,
                f"File '{batch.uploaded_file_id}' was not found.",
                "File Not Found",
            )
        return ActualsImportBatchDetailRead(
            **summary.model_dump(),
            file=file_read,
            notes=batch.notes,
            review_buckets=self._build_review_buckets(batch.rows),
            batch_issues=[
                self._serialize_issue(issue)
                for issue in sorted(
                    batch.issues, key=lambda item: (item.severity.value, item.created_at)
                )
                if issue.ceta_import_row_id is None
            ],
            variance_projects=self._build_variance_projects(session, batch),
            variance_months=self._build_variance_months(session, batch),
            snapshot_withdrawal_candidates=self._build_snapshot_withdrawal_candidates(
                session, batch
            ),
        )

    def _serialize_row(self, row: CetaImportRow) -> ActualsImportRowRead:
        latest_decision = self._latest_decision(row)
        return ActualsImportRowRead(
            id=row.id,
            row_number=row.row_number,
            source_row_uid=row.source_row_uid,
            status=row.status,
            review_queue=self._review_queue(row),
            external_project_code=row.external_project_code,
            work_date=row.work_date,
            posting_date=row.posting_date,
            source_discipline_code=row.source_discipline_code,
            description=row.description,
            vendor_name=row.vendor_name,
            amount=_to_float(row.amount),
            currency_code=row.currency_code,
            financial_type=row.financial_type,
            row_hash=row.row_hash,
            business_key_hash=row.business_key_hash,
            duplicate_group_key=row.duplicate_group_key,
            suggested_project_id=row.suggested_project_id,
            suggested_project_name=row.suggested_project.name if row.suggested_project else None,
            suggested_discipline_id=row.suggested_discipline_id,
            suggested_discipline_name=row.suggested_discipline.name
            if row.suggested_discipline
            else None,
            suggested_cost_category_key=row.suggested_cost_category_key,
            suggested_revenue_category_key=row.suggested_revenue_category_key,
            matched_current_actual_id=row.matched_current_actual_id,
            issues=[
                self._serialize_issue(issue)
                for issue in sorted(row.issues, key=lambda item: item.created_at)
            ],
            candidates=[
                self._serialize_candidate(candidate)
                for candidate in sorted(
                    row.candidates,
                    key=lambda item: (
                        item.dimension.value,
                        item.sort_order,
                        -_to_float(item.score),
                    ),
                )
            ],
            latest_decision=self._serialize_decision(latest_decision) if latest_decision else None,
            raw_payload=row.raw_payload_json,
        )

    def _serialize_issue(self, issue: CetaImportRowIssue) -> ActualsImportIssueRead:
        return ActualsImportIssueRead(
            id=issue.id,
            severity=issue.severity,
            issue_code=issue.issue_code,
            field_name=issue.field_name,
            message=issue.message,
            details=issue.details_json,
            resolved_at=issue.resolved_at,
        )

    def _serialize_candidate(self, candidate: CetaImportRowCandidate) -> ActualsImportCandidateRead:
        return ActualsImportCandidateRead(
            id=candidate.id,
            dimension=candidate.dimension,
            target_type=candidate.target_type,
            target_key=candidate.target_key,
            target_label=candidate.target_label,
            candidate_source=candidate.candidate_source,
            score=_to_float(candidate.score),
            explanation=candidate.explanation,
            sort_order=candidate.sort_order,
            metadata=candidate.metadata_json,
        )

    def _serialize_decision(self, decision: ActualMappingDecision) -> ActualsImportDecisionRead:
        return ActualsImportDecisionRead(
            id=decision.id,
            mapped_project_id=decision.mapped_project_id,
            mapped_project_name=decision.mapped_project.name if decision.mapped_project else None,
            mapped_discipline_id=decision.mapped_discipline_id,
            mapped_discipline_name=decision.mapped_discipline.name
            if decision.mapped_discipline
            else None,
            financial_type=decision.financial_type,
            cost_category_key=decision.cost_category_key,
            revenue_category_key=decision.revenue_category_key,
            approval_action=decision.approval_action,
            mapping_method=decision.mapping_method,
            matched_existing_actual_id=decision.matched_existing_actual_id,
            confidence_score=_to_float(decision.confidence_score)
            if decision.confidence_score is not None
            else None,
            reviewer_note=decision.reviewer_note,
            explanation=decision.explanation_json,
            created_rule_id=decision.created_rule_id,
            created_alias_id=decision.created_alias_id,
            created_external_reference_id=decision.created_external_reference_id,
            created_at=decision.created_at,
        )

    def _latest_decision(self, row: CetaImportRow) -> ActualMappingDecision | None:
        if not row.mapping_decisions:
            return None
        return max(row.mapping_decisions, key=lambda item: (item.created_at, item.id))

    def _review_queue(self, row: CetaImportRow) -> str:
        latest = self._latest_decision(row)
        if latest is not None and latest.approval_action == ActualMappingApprovalAction.reject:
            return "rejected"
        if self._has_blocking_issues(row):
            return "blocking"
        if row.matched_current_actual_id is not None:
            if (
                latest is not None
                and latest.approval_action == ActualMappingApprovalAction.supersede_existing
            ):
                return "changed_repeat"
            if (
                latest is not None
                and latest.approval_action == ActualMappingApprovalAction.link_existing
            ):
                return "repeat_match"
            return "changed_repeat" if self._matched_actual_changed(row) else "repeat_match"
        if latest is not None and latest.approval_action in {
            ActualMappingApprovalAction.post_new,
            ActualMappingApprovalAction.supersede_existing,
            ActualMappingApprovalAction.link_existing,
        }:
            return "ready"
        if self._is_row_resolved_by_suggestion(row):
            return "ready"
        return "ambiguous"

    def _has_blocking_issues(self, row: CetaImportRow) -> bool:
        return any(
            issue.severity in {CetaImportIssueSeverity.blocking, CetaImportIssueSeverity.fatal}
            for issue in row.issues
        )

    def _matched_actual_changed(self, row: CetaImportRow) -> bool:
        actual = row.matched_current_actual
        if actual is None:
            return False
        return any(
            [
                _to_float(actual.amount) != _to_float(row.amount),
                (actual.description or "") != (row.description or ""),
                (actual.vendor_name or "") != (row.vendor_name or ""),
                actual.work_date != row.work_date,
            ]
        )

    def _is_row_resolved_by_suggestion(self, row: CetaImportRow) -> bool:
        if row.suggested_project_id is None:
            return False
        if row.financial_type == CetaRowFinancialType.cost:
            return row.suggested_cost_category_key is not None
        if row.financial_type == CetaRowFinancialType.revenue:
            return row.suggested_revenue_category_key is not None
        return False

    def _build_review_buckets(
        self, rows: list[CetaImportRow]
    ) -> list[ActualsImportReviewBucketRead]:
        counts = {key: 0 for key in REVIEW_QUEUE_LABELS}
        for row in rows:
            counts[self._review_queue(row)] += 1
        return [
            ActualsImportReviewBucketRead(key=key, label=label, count=counts[key])
            for key, label in REVIEW_QUEUE_LABELS.items()
        ]

    def _build_parse_summary(self, batch: CetaImport) -> dict[str, object]:
        issue_count = len(batch.issues) + sum(len(row.issues) for row in batch.rows)
        candidate_count = sum(len(row.candidates) for row in batch.rows)
        return {
            "rowCount": len(batch.rows),
            "issueCount": issue_count,
            "candidateCount": candidate_count,
            "blockingCount": sum(1 for row in batch.rows if self._review_queue(row) == "blocking"),
        }

    def _build_review_summary(self, batch: CetaImport) -> dict[str, object]:
        approved_rows = sum(1 for row in batch.rows if row.status == CetaRowStatus.approved)
        rejected_rows = sum(1 for row in batch.rows if row.status == CetaRowStatus.rejected)
        linked_rows = sum(
            1
            for row in batch.rows
            if (
                self._latest_decision(row)
                and self._latest_decision(row).approval_action
                == ActualMappingApprovalAction.link_existing
            )
        )
        return {
            "approvedCount": approved_rows,
            "rejectedCount": rejected_rows,
            "linkedRepeatCount": linked_rows,
        }

    def _resolved_project(self, row: CetaImportRow) -> tuple[str | None, str | None]:
        latest = self._latest_decision(row)
        if latest is not None and latest.mapped_project_id is not None:
            return (
                latest.mapped_project_id,
                latest.mapped_project.name if latest.mapped_project else None,
            )
        if row.suggested_project_id is not None:
            return (
                row.suggested_project_id,
                row.suggested_project.name if row.suggested_project else None,
            )
        if row.ceta_import.project_id is not None:
            return (
                row.ceta_import.project_id,
                row.ceta_import.project.name if row.ceta_import.project else None,
            )
        return None, None

    def _build_variance_projects(
        self,
        session: Session,
        batch: CetaImport,
    ) -> list[ActualsImportVarianceProjectRead]:
        project_totals: dict[str, dict[str, object]] = {}
        for row in batch.rows:
            project_id, project_name = self._resolved_project(row)
            if project_id is None or self._review_queue(row) == "rejected":
                continue
            bucket = project_totals.setdefault(
                project_id,
                {
                    "project_name": project_name or project_id,
                    "import_amount": 0.0,
                },
            )
            bucket["import_amount"] = float(bucket["import_amount"]) + _to_float(row.amount)

        if not project_totals:
            return []

        quote_totals = self._current_quote_totals(session, list(project_totals))
        forecast_totals = self._current_forecast_totals(session, list(project_totals))
        actual_totals = self._current_actual_totals(session, list(project_totals))

        items = []
        for project_id, values in sorted(project_totals.items()):
            import_amount = float(values["import_amount"])
            current_quote_amount = quote_totals.get(project_id)
            current_forecast_amount = forecast_totals.get(project_id)
            current_actual_amount = actual_totals.get(project_id, 0.0)
            items.append(
                ActualsImportVarianceProjectRead(
                    project_id=project_id,
                    project_name=str(values["project_name"]),
                    import_amount=import_amount,
                    current_quote_amount=current_quote_amount,
                    current_forecast_amount=current_forecast_amount,
                    current_actual_amount=current_actual_amount,
                    import_vs_quote_variance=(
                        import_amount - current_quote_amount
                        if current_quote_amount is not None
                        else None
                    ),
                    import_vs_forecast_variance=(
                        import_amount - current_forecast_amount
                        if current_forecast_amount is not None
                        else None
                    ),
                    import_vs_current_actual_variance=import_amount - current_actual_amount,
                )
            )
        return items

    def _build_variance_months(
        self,
        session: Session,
        batch: CetaImport,
    ) -> list[ActualsImportVarianceMonthRead]:
        project_ids = [item.project_id for item in self._build_variance_projects(session, batch)]
        if not project_ids:
            return []

        import_months: dict[str, float] = defaultdict(float)
        for row in batch.rows:
            if self._review_queue(row) == "rejected":
                continue
            project_id, _project_name = self._resolved_project(row)
            if project_id not in project_ids:
                continue
            month = _month_key(row.work_date or row.posting_date)
            if month is None:
                continue
            import_months[month] += _to_float(row.amount)

        actual_months: dict[str, float] = defaultdict(float)
        actuals = list(
            session.scalars(
                select(MappedActual).where(
                    MappedActual.project_id.in_(project_ids),
                    MappedActual.is_current.is_(True),
                )
            )
        )
        for actual in actuals:
            month = _month_key(actual.work_date or actual.posting_date)
            if month is None:
                continue
            actual_months[month] += _to_float(actual.amount)

        months = sorted(set(import_months) | set(actual_months))
        return [
            ActualsImportVarianceMonthRead(
                month=month,
                import_amount=import_months.get(month, 0.0),
                current_actual_amount=actual_months.get(month, 0.0),
            )
            for month in months
        ]

    def _build_snapshot_withdrawal_candidates(
        self,
        session: Session,
        batch: CetaImport,
    ) -> list[SnapshotWithdrawalCandidateRead]:
        if batch.coverage_mode != CetaImportCoverageMode.snapshot:
            return []
        project_ids = {
            project_id
            for row in batch.rows
            for project_id, _name in [self._resolved_project(row)]
            if project_id is not None
        }
        if batch.project_id is not None:
            project_ids.add(batch.project_id)
        if not project_ids:
            return []

        current_actuals = list(
            session.scalars(
                select(MappedActual).where(
                    MappedActual.project_id.in_(project_ids),
                    MappedActual.is_current.is_(True),
                )
            )
        )
        staged_keys = {row.business_key_hash for row in batch.rows}
        items: list[SnapshotWithdrawalCandidateRead] = []
        for actual in current_actuals:
            if actual.actual_business_key in staged_keys:
                continue
            comparison_date = actual.work_date or actual.posting_date
            if batch.coverage_start and comparison_date and comparison_date < batch.coverage_start:
                continue
            if batch.coverage_end and comparison_date and comparison_date > batch.coverage_end:
                continue
            project = session.get(Project, actual.project_id)
            items.append(
                SnapshotWithdrawalCandidateRead(
                    actual_id=actual.id,
                    project_id=actual.project_id,
                    project_name=project.name if project is not None else actual.project_id,
                    work_date=actual.work_date,
                    description=actual.description,
                    vendor_name=actual.vendor_name,
                    amount=_to_float(actual.amount),
                    currency_code=actual.currency_code,
                    financial_type=actual.financial_type,
                    actual_business_key=actual.actual_business_key,
                )
            )
        return sorted(
            items,
            key=lambda item: (
                item.project_name,
                item.work_date or datetime.min.date(),
                item.actual_id,
            ),
        )

    def _current_quote_totals(self, session: Session, project_ids: list[str]) -> dict[str, float]:
        rows = session.execute(
            select(Quote.project_id, QuoteVersion.total_amount)
            .join(QuoteVersion, QuoteVersion.id == Quote.current_version_id)
            .where(Quote.project_id.in_(project_ids))
        ).all()
        return {project_id: _to_float(total_amount) for project_id, total_amount in rows}

    def _current_forecast_totals(
        self, session: Session, project_ids: list[str]
    ) -> dict[str, float]:
        rows = session.execute(
            select(Forecast.project_id, ForecastVersion.total_amount)
            .join(ForecastVersion, ForecastVersion.id == Forecast.current_version_id)
            .where(Forecast.project_id.in_(project_ids))
        ).all()
        return {project_id: _to_float(total_amount) for project_id, total_amount in rows}

    def _current_actual_totals(self, session: Session, project_ids: list[str]) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        rows = list(
            session.scalars(
                select(MappedActual).where(
                    MappedActual.project_id.in_(project_ids),
                    MappedActual.is_current.is_(True),
                )
            )
        )
        for row in rows:
            totals[row.project_id] += _to_float(row.amount)
        return dict(totals)

    def _refresh_batch_candidates(self, session: Session, batch: CetaImport) -> None:
        alias_rows = list(
            session.scalars(
                select(ReferenceTermAlias).where(ReferenceTermAlias.is_active.is_(True))
            )
        )
        rules = list(
            session.scalars(select(ActualMappingRule).where(ActualMappingRule.is_active.is_(True)))
        )
        external_refs = list(
            session.scalars(
                select(ProjectExternalReference).where(ProjectExternalReference.is_active.is_(True))
            )
        )
        projects = list(session.scalars(select(Project)))
        disciplines = list(
            session.scalars(select(Discipline).where(Discipline.is_active.is_(True)))
        )
        actuals_by_key: dict[str, list[MappedActual]] = defaultdict(list)
        for actual in session.scalars(
            select(MappedActual).where(MappedActual.is_current.is_(True))
        ):
            actuals_by_key[actual.actual_business_key].append(actual)

        for row in batch.rows:
            for candidate in list(row.candidates):
                session.delete(candidate)
            row.suggested_project_id = None
            row.suggested_discipline_id = None
            row.suggested_cost_category_key = None
            row.suggested_revenue_category_key = None

            current_actuals = actuals_by_key.get(row.business_key_hash, [])
            if current_actuals:
                row.matched_current_actual_id = current_actuals[0].id

            seen_candidates: set[tuple[str, str, str]] = set()
            candidates: list[CetaImportRowCandidate] = []

            normalized_project_code = row.normalized_project_code or _normalize_text(
                row.external_project_code
            )
            normalized_description = row.normalized_description or _normalize_text(row.description)
            normalized_vendor_name = row.normalized_vendor_name or _normalize_text(row.vendor_name)
            normalized_source_discipline = _normalize_text(row.source_discipline_code)

            if batch.project_id is not None:
                project = batch.project or session.get(Project, batch.project_id)
                if project is not None:
                    candidates.append(
                        self._candidate(
                            row,
                            CetaImportCandidateDimension.project,
                            "project",
                            project.id,
                            project.name,
                            "batch_scope",
                            90.0,
                            "Batch was explicitly scoped to this project.",
                            seen_candidates,
                        )
                    )

            if normalized_project_code is not None:
                for external_ref in external_refs:
                    if external_ref.source_system not in {(batch.source_system or "ceta"), "ceta"}:
                        continue
                    if external_ref.normalized_external_value == normalized_project_code:
                        project = session.get(Project, external_ref.project_id)
                        if project is not None:
                            candidates.append(
                                self._candidate(
                                    row,
                                    CetaImportCandidateDimension.project,
                                    "project",
                                    project.id,
                                    project.name,
                                    "external_reference",
                                    99.0,
                                    f"Matched external reference '{external_ref.external_value}'.",
                                    seen_candidates,
                                )
                            )
                for project in projects:
                    if project.code and _normalize_text(project.code) == normalized_project_code:
                        candidates.append(
                            self._candidate(
                                row,
                                CetaImportCandidateDimension.project,
                                "project",
                                project.id,
                                project.name,
                                "project_code",
                                95.0,
                                f"Matched project code '{project.code}'.",
                                seen_candidates,
                            )
                        )

            if normalized_source_discipline is not None:
                for discipline in disciplines:
                    if _normalize_text(discipline.code) == normalized_source_discipline:
                        candidates.append(
                            self._candidate(
                                row,
                                CetaImportCandidateDimension.discipline,
                                "discipline",
                                discipline.id,
                                discipline.name,
                                "discipline_code",
                                95.0,
                                f"Matched discipline code '{row.source_discipline_code}'.",
                                seen_candidates,
                            )
                        )

            for alias in alias_rows:
                candidate_value = alias.normalized_alias_text
                if candidate_value is None:
                    continue
                source_field = alias.source_field_path or ""
                inputs = []
                if source_field == "source_discipline_code":
                    inputs = [normalized_source_discipline]
                elif source_field == "external_project_code":
                    inputs = [normalized_project_code]
                else:
                    inputs = [
                        normalized_description,
                        normalized_vendor_name,
                        normalized_source_discipline,
                        normalized_project_code,
                    ]
                if not any(value is not None and candidate_value in value for value in inputs):
                    continue
                score = _to_float(alias.confidence_hint) or 85.0
                if alias.category == "discipline":
                    discipline = next(
                        (item for item in disciplines if item.code == alias.canonical_key), None
                    )
                    if discipline is not None:
                        candidates.append(
                            self._candidate(
                                row,
                                CetaImportCandidateDimension.discipline,
                                "discipline",
                                discipline.id,
                                discipline.name,
                                "alias",
                                score,
                                (
                                    f"Alias '{alias.alias_text}' maps to discipline "
                                    f"'{discipline.name}'."
                                ),
                                seen_candidates,
                            )
                        )
                elif alias.category == "actuals_mapping_category":
                    candidates.append(
                        self._candidate(
                            row,
                            CetaImportCandidateDimension.cost_category,
                            "reference_data",
                            alias.canonical_key,
                            alias.canonical_key,
                            "alias",
                            score,
                            (
                                f"Alias '{alias.alias_text}' maps to cost category "
                                f"'{alias.canonical_key}'."
                            ),
                            seen_candidates,
                        )
                    )
                elif alias.category == "revenue_category":
                    candidates.append(
                        self._candidate(
                            row,
                            CetaImportCandidateDimension.revenue_category,
                            "reference_data",
                            alias.canonical_key,
                            alias.canonical_key,
                            "alias",
                            score,
                            (
                                f"Alias '{alias.alias_text}' maps to revenue category "
                                f"'{alias.canonical_key}'."
                            ),
                            seen_candidates,
                        )
                    )

            for rule in rules:
                if rule.source_system != (batch.source_system or "ceta"):
                    continue
                if (
                    rule.scope_project_id is not None
                    and batch.project_id is not None
                    and rule.scope_project_id != batch.project_id
                ):
                    continue
                if rule.external_project_code_pattern and (
                    normalized_project_code is None
                    or rule.external_project_code_pattern not in normalized_project_code
                ):
                    continue
                if rule.source_discipline_code_pattern and (
                    normalized_source_discipline is None
                    or rule.source_discipline_code_pattern not in normalized_source_discipline
                ):
                    continue
                if rule.vendor_pattern and (
                    normalized_vendor_name is None
                    or rule.vendor_pattern not in normalized_vendor_name
                ):
                    continue
                if rule.description_pattern and (
                    normalized_description is None
                    or rule.description_pattern not in normalized_description
                ):
                    continue
                if rule.target_project_id is not None:
                    project = session.get(Project, rule.target_project_id)
                    if project is not None:
                        candidates.append(
                            self._candidate(
                                row,
                                CetaImportCandidateDimension.project,
                                "project",
                                project.id,
                                project.name,
                                "rule",
                                98.0,
                                rule.explanation or f"Rule '{rule.rule_name}' matched this row.",
                                seen_candidates,
                            )
                        )
                if rule.target_discipline_id is not None:
                    discipline = session.get(Discipline, rule.target_discipline_id)
                    if discipline is not None:
                        candidates.append(
                            self._candidate(
                                row,
                                CetaImportCandidateDimension.discipline,
                                "discipline",
                                discipline.id,
                                discipline.name,
                                "rule",
                                98.0,
                                rule.explanation or f"Rule '{rule.rule_name}' matched this row.",
                                seen_candidates,
                            )
                        )
                if rule.cost_category_key is not None:
                    candidates.append(
                        self._candidate(
                            row,
                            CetaImportCandidateDimension.cost_category,
                            "reference_data",
                            rule.cost_category_key,
                            rule.cost_category_key,
                            "rule",
                            98.0,
                            rule.explanation or f"Rule '{rule.rule_name}' matched this row.",
                            seen_candidates,
                        )
                    )
                if rule.revenue_category_key is not None:
                    candidates.append(
                        self._candidate(
                            row,
                            CetaImportCandidateDimension.revenue_category,
                            "reference_data",
                            rule.revenue_category_key,
                            rule.revenue_category_key,
                            "rule",
                            98.0,
                            rule.explanation or f"Rule '{rule.rule_name}' matched this row.",
                            seen_candidates,
                        )
                    )

            for actual in current_actuals:
                project = session.get(Project, actual.project_id)
                if project is not None:
                    candidates.append(
                        self._candidate(
                            row,
                            CetaImportCandidateDimension.project,
                            "project",
                            project.id,
                            project.name,
                            "historical_match",
                            94.0,
                            "Matched the business key of an existing current actual.",
                            seen_candidates,
                        )
                    )
                if actual.discipline_id is not None:
                    discipline = session.get(Discipline, actual.discipline_id)
                    if discipline is not None:
                        candidates.append(
                            self._candidate(
                                row,
                                CetaImportCandidateDimension.discipline,
                                "discipline",
                                discipline.id,
                                discipline.name,
                                "historical_match",
                                92.0,
                                "Matched the discipline of an existing current actual.",
                                seen_candidates,
                            )
                        )
                if actual.cost_category_key is not None:
                    candidates.append(
                        self._candidate(
                            row,
                            CetaImportCandidateDimension.cost_category,
                            "reference_data",
                            actual.cost_category_key,
                            actual.cost_category_key,
                            "historical_match",
                            92.0,
                            "Matched the cost category of an existing current actual.",
                            seen_candidates,
                        )
                    )
                if actual.revenue_category_key is not None:
                    candidates.append(
                        self._candidate(
                            row,
                            CetaImportCandidateDimension.revenue_category,
                            "reference_data",
                            actual.revenue_category_key,
                            actual.revenue_category_key,
                            "historical_match",
                            92.0,
                            "Matched the revenue category of an existing current actual.",
                            seen_candidates,
                        )
                    )

            candidates.append(
                self._candidate(
                    row,
                    CetaImportCandidateDimension.financial_type,
                    "classification",
                    row.financial_type.value,
                    row.financial_type.value.replace("_", " "),
                    "parser",
                    88.0,
                    f"Parser classified the row as '{row.financial_type.value}'.",
                    seen_candidates,
                )
            )

            filtered_candidates = [candidate for candidate in candidates if candidate is not None]
            for index, candidate in enumerate(
                sorted(
                    filtered_candidates,
                    key=lambda item: (
                        item.dimension.value,
                        -_to_float(item.score),
                        item.target_key,
                    ),
                ),
                start=1,
            ):
                candidate.sort_order = index
                session.add(candidate)

            session.flush()
            session.refresh(row)
            self._sync_row_suggestions(row)

    def _candidate(
        self,
        row: CetaImportRow,
        dimension: CetaImportCandidateDimension,
        target_type: str,
        target_key: str,
        target_label: str,
        candidate_source: str,
        score: float,
        explanation: str,
        seen_candidates: set[tuple[str, str, str]],
    ) -> CetaImportRowCandidate | None:
        dedupe_key = (dimension.value, target_key, candidate_source)
        if dedupe_key in seen_candidates:
            return None
        seen_candidates.add(dedupe_key)
        return CetaImportRowCandidate(
            ceta_import_row_id=row.id,
            dimension=dimension,
            target_type=target_type,
            target_key=target_key,
            target_label=target_label,
            candidate_source=candidate_source,
            score=score,
            explanation=explanation,
            sort_order=0,
        )

    def _sync_row_suggestions(self, row: CetaImportRow) -> None:
        by_dimension: dict[str, list[CetaImportRowCandidate]] = defaultdict(list)
        for candidate in row.candidates:
            by_dimension[candidate.dimension.value].append(candidate)
        for values in by_dimension.values():
            values.sort(key=lambda item: (-_to_float(item.score), item.target_key))

        project_candidate = by_dimension.get(CetaImportCandidateDimension.project.value, [None])[0]
        discipline_candidate = by_dimension.get(
            CetaImportCandidateDimension.discipline.value, [None]
        )[0]
        cost_candidate = by_dimension.get(CetaImportCandidateDimension.cost_category.value, [None])[
            0
        ]
        revenue_candidate = by_dimension.get(
            CetaImportCandidateDimension.revenue_category.value, [None]
        )[0]

        row.suggested_project_id = (
            project_candidate.target_key
            if project_candidate and project_candidate.target_type == "project"
            else None
        )
        row.suggested_discipline_id = (
            discipline_candidate.target_key
            if discipline_candidate and discipline_candidate.target_type == "discipline"
            else None
        )
        row.suggested_cost_category_key = cost_candidate.target_key if cost_candidate else None
        row.suggested_revenue_category_key = (
            revenue_candidate.target_key if revenue_candidate else None
        )
        row.status = (
            CetaRowStatus.suggested
            if row.suggested_project_id is not None
            else CetaRowStatus.unmatched
        )

    def _require_project(self, session: Session, project_id: str) -> None:
        if session.get(Project, project_id) is None:
            raise ApiProblemException(
                422,
                f"Project '{project_id}' was not found.",
                "Invalid Project",
            )

    def _require_discipline(self, session: Session, discipline_id: str) -> None:
        if session.get(Discipline, discipline_id) is None:
            raise ApiProblemException(
                422,
                f"Discipline '{discipline_id}' was not found.",
                "Invalid Discipline",
            )

    def _require_reference_key(self, session: Session, category: str, key: str) -> None:
        value = session.scalar(
            select(ReferenceDataValue).where(
                ReferenceDataValue.category == category,
                ReferenceDataValue.key == key,
                ReferenceDataValue.is_active.is_(True),
            )
        )
        if value is None:
            raise ApiProblemException(
                422,
                f"Reference key '{key}' was not found in category '{category}'.",
                "Invalid Reference Data",
            )

    def _upsert_project_external_reference(
        self,
        session: Session,
        *,
        project_id: str,
        source_system: str,
        external_value: str,
        actor_id: str,
    ) -> ProjectExternalReference:
        normalized_external_value = _normalize_text(external_value)
        existing = session.scalar(
            select(ProjectExternalReference).where(
                ProjectExternalReference.project_id == project_id,
                ProjectExternalReference.source_system == source_system,
                ProjectExternalReference.normalized_external_value == normalized_external_value,
            )
        )
        if existing is not None:
            existing.is_active = True
            return existing
        record = ProjectExternalReference(
            project_id=project_id,
            source_system=source_system,
            external_value=external_value,
            normalized_external_value=normalized_external_value or external_value.lower(),
            label=external_value,
            is_active=True,
            created_by_id=actor_id,
        )
        session.add(record)
        session.flush()
        return record

    def _create_alias_from_row(
        self,
        session: Session,
        row: CetaImportRow,
        *,
        mapped_discipline_id: str | None,
        cost_category_key: str | None,
        revenue_category_key: str | None,
        source_system: str,
        actor_id: str,
    ) -> ReferenceTermAlias | None:
        category: str | None = None
        alias_text: str | None = None
        canonical_key: str | None = None
        source_field_path: str | None = None

        if mapped_discipline_id is not None and row.source_discipline_code:
            discipline = session.get(Discipline, mapped_discipline_id)
            if discipline is not None:
                category = "discipline"
                alias_text = row.source_discipline_code
                canonical_key = discipline.code
                source_field_path = "source_discipline_code"
        elif cost_category_key is not None:
            category = "actuals_mapping_category"
            alias_text = row.description or row.vendor_name
            canonical_key = cost_category_key
            source_field_path = "description"
        elif revenue_category_key is not None:
            category = "revenue_category"
            alias_text = row.description or row.vendor_name
            canonical_key = revenue_category_key
            source_field_path = "description"

        if category is None or alias_text is None or canonical_key is None:
            return None

        normalized_alias_text = _normalize_text(alias_text)
        existing = session.scalar(
            select(ReferenceTermAlias).where(
                ReferenceTermAlias.category == category,
                ReferenceTermAlias.source_system == source_system,
                ReferenceTermAlias.source_field_path == source_field_path,
                ReferenceTermAlias.normalized_alias_text == normalized_alias_text,
            )
        )
        if existing is not None:
            existing.canonical_key = canonical_key
            existing.is_active = True
            return existing
        alias = ReferenceTermAlias(
            category=category,
            alias_text=alias_text,
            normalized_alias_text=normalized_alias_text or alias_text.lower(),
            canonical_key=canonical_key,
            source_system=source_system,
            source_field_path=source_field_path,
            confidence_hint=95,
            is_active=True,
            created_by_id=actor_id,
        )
        session.add(alias)
        session.flush()
        return alias

    def _create_rule_from_row(
        self,
        session: Session,
        row: CetaImportRow,
        *,
        rule_name: str | None,
        mapped_project_id: str | None,
        mapped_discipline_id: str | None,
        financial_type: CetaRowFinancialType | None,
        cost_category_key: str | None,
        revenue_category_key: str | None,
        source_system: str,
        actor_id: str,
    ) -> ActualMappingRule:
        rule = ActualMappingRule(
            source_system=source_system,
            scope_project_id=row.ceta_import.project_id,
            rule_name=rule_name or f"Row {row.row_number} correction",
            financial_type=financial_type,
            vendor_pattern=_normalize_text(row.vendor_name),
            description_pattern=_normalize_text(row.description),
            external_project_code_pattern=_normalize_text(row.external_project_code),
            source_discipline_code_pattern=_normalize_text(row.source_discipline_code),
            target_project_id=mapped_project_id,
            target_discipline_id=mapped_discipline_id,
            cost_category_key=cost_category_key,
            revenue_category_key=revenue_category_key,
            explanation=f"Saved from review override on row {row.row_number}.",
            is_active=True,
            created_by_id=actor_id,
        )
        session.add(rule)
        session.flush()
        return rule


actuals_import_service = ActualsImportService()
