from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.errors import ApiProblemException
from app.core.validation import validate_storage_object_key
from app.integrations.pdf_parser import quote_pdf_parser
from app.integrations.storage import object_storage_service
from app.models import (
    PdfExtractionFieldResult,
    PdfExtractionLineItemResult,
    PdfExtractionRun,
    UploadedFile,
)
from app.models.enums import (
    BackgroundJobStatus,
    PdfExtractionConfidenceFlag,
    PdfExtractionResultSource,
    PdfExtractionReviewStatus,
    PdfExtractionRunStatus,
    PdfExtractionTargetMode,
    QuoteLineItemType,
    UploadedFileCategory,
    UploadedFileStatus,
)
from app.modules.audit.service import audit_service
from app.modules.files.service import UploadedFileRead, files_service
from app.modules.jobs.service import job_service
from app.modules.projects.service import projects_service
from app.modules.quote_ingestion.schemas import (
    ApprovalBlocker,
    ApprovalPreview,
    ApproveQuoteIngestionRunRequest,
    ConfidenceSummary,
    CreateQuoteIngestionRunRequest,
    CreateQuoteIngestionUploadRequest,
    ExtractionWarning,
    FieldCandidate,
    FieldDecision,
    FieldDecisionInput,
    FinalizeQuoteIngestionUploadRequest,
    FinalizeQuoteIngestionUploadResponse,
    LineItemCandidate,
    LineItemDecision,
    LineItemDecisionInput,
    MatchSuggestion,
    QuoteApprovalResponse,
    QuoteIngestionFileSummary,
    QuoteIngestionRunDetail,
    QuoteIngestionRunListResponse,
    QuoteIngestionRunSummary,
    QuoteIngestionUploadIntentResponse,
    QuoteParsePreviewResponse,
    RejectQuoteIngestionRunRequest,
    RerunQuoteIngestionRunRequest,
    UpdateQuoteIngestionReviewRequest,
    WorkerParseResultRequest,
)
from app.modules.quotes.service import QuoteApprovalLineItem, QuoteApprovalPayload, quotes_service

REQUIRED_FIELD_PATHS = {
    "client.name",
    "quote.date",
    "quote.currency_code",
    "totals.total",
}


class QuoteIngestionService:
    def list_runs(self, session: Session) -> QuoteIngestionRunListResponse:
        runs = list(
            session.scalars(select(PdfExtractionRun).order_by(desc(PdfExtractionRun.updated_at)))
        )
        items = [self._to_summary(self._serialize_run(session, run)) for run in runs]
        return QuoteIngestionRunListResponse(items=items)

    def get_run(self, session: Session, run_id: str) -> QuoteIngestionRunDetail:
        run = self._get_run_entity(session, run_id)
        return self._serialize_run(session, run)

    def create_upload_intent(
        self,
        session: Session,
        payload: CreateQuoteIngestionUploadRequest,
        *,
        actor_id: str,
    ) -> QuoteIngestionUploadIntentResponse:
        if payload.content_type != "application/pdf":
            raise ApiProblemException(
                422,
                "Quote ingestion uploads must be submitted as application/pdf.",
                title="Invalid Ingestion Upload",
            )
        upload, upload_url, headers, expires_at = files_service.create_upload_intent(
            session,
            file_name=payload.file_name,
            content_type=payload.content_type,
            size_bytes=payload.size_bytes,
            checksum_sha256=payload.checksum_sha256,
            entity_type=None,
            entity_id=None,
            file_category=UploadedFileCategory.quote_pdf,
            actor_id=actor_id,
        )
        return QuoteIngestionUploadIntentResponse(
            file=self._file_summary(upload),
            bucket=object_storage_service.settings.s3_bucket,
            upload_url=upload_url,
            expires_at=expires_at,
            required_headers=headers,
        )

    def finalize_upload(
        self,
        session: Session,
        payload: FinalizeQuoteIngestionUploadRequest,
        *,
        actor_id: str,
    ) -> FinalizeQuoteIngestionUploadResponse:
        upload = files_service.finalize_upload(
            session,
            file_id=payload.file_id,
            object_key=payload.object_key,
            checksum_sha256=payload.checksum_sha256,
            actor_id=actor_id,
        )
        if upload.file_category != UploadedFileCategory.quote_pdf:
            raise ApiProblemException(
                409,
                "This upload was not registered as a quote PDF ingestion file.",
                title="Invalid Ingestion Upload",
            )
        return FinalizeQuoteIngestionUploadResponse(file=self._file_summary(upload))

    def create_run(
        self,
        session: Session,
        payload: CreateQuoteIngestionRunRequest,
        *,
        actor_id: str,
    ) -> QuoteIngestionRunDetail:
        uploaded_file = self._require_uploaded_file(session, payload.uploaded_file_id)
        if uploaded_file.file_category != UploadedFileCategory.quote_pdf:
            raise ApiProblemException(
                422,
                "Only files uploaded as quote PDFs can start PDF ingestion.",
                title="Invalid Ingestion File",
            )
        if uploaded_file.status != UploadedFileStatus.uploaded:
            raise ApiProblemException(
                409,
                "Finalize the file upload before starting quote ingestion.",
                title="Upload Not Finalized",
            )
        if payload.project_id is not None:
            self._require_project(session, payload.project_id)

        run = PdfExtractionRun(
            uploaded_file_id=uploaded_file.file_id,
            status=PdfExtractionRunStatus.queued,
            parser_profile=payload.parser_profile,
            selected_project_id=payload.project_id,
            queue_name="pdf_parse",
        )
        session.add(run)
        session.flush()

        job = job_service.enqueue(
            session,
            queue_name=run.queue_name,
            payload={
                "runId": run.id,
                "uploadedFileId": uploaded_file.file_id,
                "objectKey": uploaded_file.object_key,
                "parserProfile": payload.parser_profile,
                "projectId": payload.project_id,
            },
            related_entity_type="pdf_extraction_run",
            related_entity_id=run.id,
        )
        run.job_id = job.id
        session.flush()

        detail = self._serialize_run(session, run)
        audit_service.record(
            session,
            action="quote_ingestion.run.created",
            entity_type="pdf_extraction_run",
            entity_id=run.id,
            actor_id=actor_id,
            project_id=run.selected_project_id,
            summary=f"Created quote ingestion run {run.id} for {uploaded_file.file_name}.",
            after=detail.model_dump(mode="json"),
        )
        return detail

    def update_review(
        self,
        session: Session,
        run_id: str,
        payload: UpdateQuoteIngestionReviewRequest,
        *,
        actor_id: str,
    ) -> QuoteIngestionRunDetail:
        run = self._get_run_entity(session, run_id)
        if run.status != PdfExtractionRunStatus.in_review:
            raise ApiProblemException(
                409,
                "Only parsed runs in review can be updated.",
                title="Run Is Not Reviewable",
            )

        before = self._serialize_run(session, run)

        if payload.selected_project_id:
            self._require_project(session, payload.selected_project_id)
            run.selected_project_id = payload.selected_project_id
        if payload.selected_quote_id:
            quote = self._require_quote(session, payload.selected_quote_id)
            run.selected_project_id = quote.project_id
        if payload.selected_target_mode == "new_quote":
            run.selected_quote_id = None
        if payload.selected_quote_id:
            run.selected_quote_id = payload.selected_quote_id
        if payload.selected_target_mode:
            run.selected_target_mode = PdfExtractionTargetMode(payload.selected_target_mode)

        if "acknowledged_warning_codes" in payload.model_fields_set:
            run.acknowledged_warning_codes_json = sorted(set(payload.acknowledged_warning_codes))

        if payload.field_decisions:
            self._upsert_field_decisions(session, run, payload.field_decisions)
        if payload.line_item_decisions:
            self._upsert_line_item_decisions(session, run, payload.line_item_decisions)

        self._refresh_match_selection(run)
        session.flush()
        detail = self._serialize_run(session, run)
        audit_service.record(
            session,
            action="quote_ingestion.review.updated",
            entity_type="pdf_extraction_run",
            entity_id=run.id,
            actor_id=actor_id,
            project_id=run.selected_project_id,
            summary=f"Updated review state for quote ingestion run {run.id}.",
            before=before.model_dump(mode="json"),
            after=detail.model_dump(mode="json"),
        )
        return detail

    def approve_run(
        self,
        session: Session,
        run_id: str,
        payload: ApproveQuoteIngestionRunRequest,
        *,
        actor_id: str,
    ) -> QuoteApprovalResponse:
        run = self._get_run_entity(session, run_id)
        if run.status != PdfExtractionRunStatus.in_review:
            raise ApiProblemException(
                409,
                "Only parsed runs in review can be approved.",
                title="Run Is Not Reviewable",
            )

        before = self._serialize_run(session, run)
        blockers = self._build_approval_blockers(before)
        if blockers:
            raise ApiProblemException(
                409,
                "Resolve the remaining review blockers before approval.",
                title="Review Incomplete",
            )

        if before.selected_project_id:
            self._require_project(session, before.selected_project_id)
        if before.selected_target_mode == "new_version" and before.selected_quote_id:
            self._require_quote(session, before.selected_quote_id)

        approval_payload = QuoteApprovalPayload(
            project_id=before.selected_project_id or "",
            target_mode=before.selected_target_mode or "new_quote",
            target_quote_id=before.selected_quote_id,
            title=self._quote_title(before, approved_only=True),
            quote_number=self._decision_text(before, "quote.quote_number"),
            currency_code=(
                self._decision_text(
                    before,
                    "quote.currency_code",
                    approved_only=True,
                )
                or "GBP"
            ),
            source_document_date=self._decision_date(
                before,
                "quote.date",
                approved_only=True,
            ),
            source_version_label=self._decision_text(
                before,
                "quote.source_version_label",
            ),
            source_job_number=self._decision_text(before, "source.job_number"),
            subtotal_amount=self._decision_amount(before, "totals.subtotal") or 0.0,
            tax_amount=self._decision_amount(before, "totals.tax") or 0.0,
            total_amount=(
                self._decision_amount(
                    before,
                    "totals.total",
                    approved_only=True,
                )
                or self._approved_line_item_total(before)
            ),
            source_uploaded_file_id=run.uploaded_file_id,
            source_pdf_extraction_run_id=run.id,
            assumptions=self._decision_texts(
                before,
                prefix="assumptions[",
                approved_only=True,
            ),
            exclusions=self._decision_texts(
                before,
                prefix="exclusions[",
                approved_only=True,
            ),
            notes=self._decision_texts(
                before,
                prefix="notes[",
                approved_only=True,
            ),
            line_items=[
                QuoteApprovalLineItem(
                    sort_order=item.sort_order,
                    section_label=item.section_label,
                    line_type=item.line_type,
                    description=item.description,
                    quantity=item.quantity,
                    unit=item.unit,
                    rate=item.rate,
                    amount=item.amount,
                )
                for item in before.line_item_decisions
                if item.review_status == "approved"
            ],
        )
        result = quotes_service.create_from_ingestion(
            session,
            approval_payload,
            actor_id=actor_id,
        )

        run.status = PdfExtractionRunStatus.approved
        run.approved_quote_id = result.quote.id
        run.approved_quote_version_id = result.version.id
        run.approved_by_id = actor_id
        run.approved_at = datetime.now(UTC)
        session.flush()

        after = self._serialize_run(session, run)
        audit_service.record(
            session,
            action="quote_ingestion.approved",
            entity_type="pdf_extraction_run",
            entity_id=run.id,
            actor_id=actor_id,
            project_id=run.selected_project_id,
            summary=(
                f"Approved quote ingestion run {run.id} into quote "
                f"{result.quote.id} version {result.version.version_number}."
            ),
            before=before.model_dump(mode="json"),
            after=after.model_dump(mode="json"),
        )
        return QuoteApprovalResponse(
            run_id=run.id,
            status=run.status.value,
            approved_quote_id=result.quote.id,
            approved_quote_version_id=result.version.id,
            approval_summary=(
                f"Created draft quote version {result.version.version_number} for "
                f"{result.quote.title or result.quote.id}."
            ),
        )

    def apply_worker_result(
        self,
        session: Session,
        run_id: str,
        payload: WorkerParseResultRequest,
    ) -> QuoteIngestionRunDetail:
        run = self._get_run_entity(session, run_id)
        if run.job_id != payload.job_id:
            raise ApiProblemException(
                409,
                "Worker result did not match the run's queued job.",
                title="Worker Result Rejected",
            )
        related_job = job_service.get(session, payload.job_id)
        if related_job is None or related_job.status not in {
            BackgroundJobStatus.queued,
            BackgroundJobStatus.running,
        }:
            raise ApiProblemException(
                409,
                "Worker result was received for a job that is no longer active.",
                title="Worker Result Rejected",
            )
        if run.status in {PdfExtractionRunStatus.approved, PdfExtractionRunStatus.rejected}:
            raise ApiProblemException(
                409,
                "Terminal runs cannot accept worker parse results.",
                title="Worker Result Rejected",
            )

        before = self._serialize_run(session, run)

        if payload.status == "failed":
            run.status = PdfExtractionRunStatus.failed
            run.failure_code = payload.failure_code or "parse_failed"
            run.failure_message = payload.failure_message or "The parser failed to extract data."
            if run.job_id:
                job_service.mark_failed(
                    session,
                    run.job_id,
                    last_error=run.failure_message,
                )
            session.flush()
            after = self._serialize_run(session, run)
            audit_service.record(
                session,
                action="quote_ingestion.worker_result.failed",
                entity_type="pdf_extraction_run",
                entity_id=run.id,
                summary=f"Stored failed worker result for quote ingestion run {run.id}.",
                before=before.model_dump(mode="json"),
                after=after.model_dump(mode="json"),
            )
            return after

        run.status = PdfExtractionRunStatus.in_review
        run.parser_name = payload.parser_name
        run.parser_version = payload.parser_version
        run.parser_profile = payload.parser_profile
        run.page_count = payload.page_count
        run.text_page_count = payload.text_page_count
        run.raw_text = payload.raw_text
        run.failure_code = None
        run.failure_message = None
        run.warnings_json = [
            warning.model_dump(mode="json") for warning in payload.warnings
        ]
        run.acknowledged_warning_codes_json = []

        session.execute(
            delete(PdfExtractionFieldResult).where(PdfExtractionFieldResult.run_id == run.id)
        )
        session.execute(
            delete(PdfExtractionLineItemResult).where(PdfExtractionLineItemResult.run_id == run.id)
        )
        session.flush()

        field_results: list[PdfExtractionFieldResult] = []
        for field in payload.field_candidates:
            result = PdfExtractionFieldResult(
                run_id=run.id,
                result_source=PdfExtractionResultSource.parser,
                field_path=field.field_path,
                occurrence_index=field.occurrence_index,
                raw_value=field.raw_value,
                normalized_text=field.normalized_text,
                normalized_amount=field.normalized_amount,
                normalized_date=field.normalized_date,
                confidence_score=field.confidence_score,
                confidence_flag=self._confidence_flag(field.confidence_score),
                page_number=field.page_number,
                source_snippet=field.source_snippet,
                source_bounds=field.source_bounds,
            )
            session.add(result)
            field_results.append(result)
        session.flush()
        self._select_default_fields(field_results)

        for item in payload.line_item_candidates:
            session.add(
                PdfExtractionLineItemResult(
                    run_id=run.id,
                    result_source=PdfExtractionResultSource.parser,
                    sort_order=item.sort_order,
                    section_label=item.section_label,
                    line_type=QuoteLineItemType(item.line_type),
                    description=item.description,
                    quantity=item.quantity,
                    unit=item.unit,
                    rate=item.rate,
                    amount=item.amount,
                    currency_code=item.currency_code,
                    confidence_score=item.confidence_score,
                    confidence_flag=self._confidence_flag(item.confidence_score),
                    page_number=item.page_number,
                    source_snippet=item.source_snippet,
                    source_bounds=item.source_bounds,
                    is_selected=True,
                    reviewed_section_label=item.section_label,
                    reviewed_line_type=QuoteLineItemType(item.line_type),
                    reviewed_description=item.description,
                    reviewed_quantity=item.quantity,
                    reviewed_unit=item.unit,
                    reviewed_rate=item.rate,
                    reviewed_amount=item.amount,
                )
            )

        self._build_match_suggestions(
            session,
            run,
            project_id=payload.project_id or run.selected_project_id,
        )
        if run.job_id:
            job_service.mark_succeeded(session, run.job_id)
        session.flush()

        after = self._serialize_run(session, run)
        audit_service.record(
            session,
            action="quote_ingestion.worker_result.applied",
            entity_type="pdf_extraction_run",
            entity_id=run.id,
            project_id=run.selected_project_id,
            summary=f"Stored worker parse results for quote ingestion run {run.id}.",
            before=before.model_dump(mode="json"),
            after=after.model_dump(mode="json"),
        )
        return after

    def rerun(
        self,
        session: Session,
        run_id: str,
        payload: RerunQuoteIngestionRunRequest,
        *,
        actor_id: str,
    ) -> QuoteIngestionRunDetail:
        run = self.get_run(session, run_id)
        return self.create_run(
            session,
            CreateQuoteIngestionRunRequest(
                uploaded_file_id=run.uploaded_file_id,
                project_id=run.selected_project_id,
                parser_profile=payload.parser_profile or run.parser_profile,
            ),
            actor_id=actor_id,
        )

    def reject_run(
        self,
        session: Session,
        run_id: str,
        payload: RejectQuoteIngestionRunRequest,
        *,
        actor_id: str,
    ) -> QuoteIngestionRunDetail:
        run = self._get_run_entity(session, run_id)
        if run.status in {PdfExtractionRunStatus.approved, PdfExtractionRunStatus.rejected}:
            raise ApiProblemException(
                409,
                "Only active review runs can be rejected.",
                title="Run Is Not Reviewable",
            )

        before = self._serialize_run(session, run)
        run.status = PdfExtractionRunStatus.rejected
        run.failure_message = payload.reason
        run.rejected_by_id = actor_id
        run.rejected_at = datetime.now(UTC)
        session.flush()

        after = self._serialize_run(session, run)
        audit_service.record(
            session,
            action="quote_ingestion.rejected",
            entity_type="pdf_extraction_run",
            entity_id=run.id,
            actor_id=actor_id,
            project_id=run.selected_project_id,
            summary=f"Rejected quote ingestion run {run.id}: {payload.reason}",
            before=before.model_dump(mode="json"),
            after=after.model_dump(mode="json"),
        )
        return after

    def preview(self, session: Session, object_key: str) -> QuoteParsePreviewResponse:
        try:
            validated_object_key = validate_storage_object_key(object_key)
        except ValueError as exc:
            raise ApiProblemException(422, str(exc), title="Invalid Preview Request") from exc
        uploaded_file = session.scalar(
            select(UploadedFile).where(UploadedFile.storage_key == validated_object_key)
        )
        if uploaded_file is None:
            raise ApiProblemException(
                404,
                "Preview is only available for registered uploaded files.",
                title="File Not Found",
            )
        if uploaded_file.file_category != UploadedFileCategory.quote_pdf:
            raise ApiProblemException(
                422,
                "Preview is only available for registered quote PDF uploads.",
                title="Invalid Preview Request",
            )
        if uploaded_file.status != UploadedFileStatus.uploaded:
            raise ApiProblemException(
                409,
                "Finalize the upload before requesting a parse preview.",
                title="Upload Not Finalized",
            )
        result = quote_pdf_parser.parse(object_key=validated_object_key)
        return QuoteParsePreviewResponse(
            object_key=validated_object_key,
            parser_name=result.parser_name,
            parser_version=result.parser_version,
            text_page_count=result.text_page_count,
            warnings=[warning.message for warning in result.warnings],
            candidate_count=len(result.candidate_line_items),
        )

    def _serialize_run(self, session: Session, run: PdfExtractionRun) -> QuoteIngestionRunDetail:
        field_results = list(
            session.scalars(
                select(PdfExtractionFieldResult)
                .where(PdfExtractionFieldResult.run_id == run.id)
                .order_by(
                    PdfExtractionFieldResult.field_path,
                    PdfExtractionFieldResult.occurrence_index,
                    PdfExtractionFieldResult.created_at,
                )
            )
        )
        line_item_results = list(
            session.scalars(
                select(PdfExtractionLineItemResult)
                .where(PdfExtractionLineItemResult.run_id == run.id)
                .order_by(
                    PdfExtractionLineItemResult.sort_order,
                    PdfExtractionLineItemResult.created_at,
                )
            )
        )
        detail = QuoteIngestionRunDetail(
            id=run.id,
            status=run.status.value,
            uploaded_file_id=run.uploaded_file_id,
            parser_name=run.parser_name,
            parser_version=run.parser_version,
            parser_profile=run.parser_profile,
            page_count=run.page_count,
            text_page_count=run.text_page_count,
            failure_code=run.failure_code,
            failure_message=run.failure_message,
            selected_project_id=run.selected_project_id,
            selected_quote_id=run.selected_quote_id,
            selected_target_mode=(
                run.selected_target_mode.value if run.selected_target_mode else None
            ),
            approved_quote_id=run.approved_quote_id,
            approved_quote_version_id=run.approved_quote_version_id,
            job_id=run.job_id or "",
            queue_name=run.queue_name,
            review_mode=run.review_mode,
            approved_at=run.approved_at,
            rejected_at=run.rejected_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
            file=self._file_summary(self._require_uploaded_file(session, run.uploaded_file_id)),
            raw_text=run.raw_text,
            warnings=[
                ExtractionWarning.model_validate(warning)
                for warning in run.warnings_json
            ],
            confidence_summary=self._build_confidence_summary(field_results, line_item_results),
            match_suggestions=[
                MatchSuggestion.model_validate(suggestion)
                for suggestion in run.match_suggestions_json
            ],
            field_candidates=self._field_candidates(field_results),
            field_decisions=self._field_decisions(field_results),
            line_item_candidates=self._line_item_candidates(line_item_results),
            line_item_decisions=self._line_item_decisions(line_item_results),
            approval_preview=ApprovalPreview(),
            acknowledged_warning_codes=list(run.acknowledged_warning_codes_json or []),
        )
        detail.approval_blockers = self._build_approval_blockers(detail)
        detail.approval_preview = self._build_approval_preview(session, detail)
        return detail

    def _field_candidates(
        self, field_results: list[PdfExtractionFieldResult]
    ) -> list[FieldCandidate]:
        candidates: list[FieldCandidate] = []
        for result in field_results:
            if result.result_source != PdfExtractionResultSource.parser:
                continue
            candidates.append(
                FieldCandidate(
                    id=result.id,
                    field_path=result.field_path,
                    occurrence_index=result.occurrence_index,
                    raw_value=result.raw_value,
                    normalized_text=result.normalized_text,
                    normalized_amount=(
                        float(result.normalized_amount)
                        if result.normalized_amount is not None
                        else None
                    ),
                    normalized_date=result.normalized_date,
                    confidence_score=(
                        float(result.confidence_score)
                        if result.confidence_score is not None
                        else None
                    ),
                    confidence_flag=result.confidence_flag.value,
                    page_number=result.page_number,
                    review_status=result.review_status.value,
                    reviewer_note=result.reviewer_note,
                    source_snippet=result.source_snippet,
                    source_bounds=result.source_bounds,
                )
            )
        return candidates

    def _field_decisions(
        self, field_results: list[PdfExtractionFieldResult]
    ) -> list[FieldDecision]:
        decisions: list[FieldDecision] = []
        for result in field_results:
            if not result.is_selected:
                continue
            decisions.append(
                FieldDecision(
                    id=result.id,
                    field_path=result.field_path,
                    selected_result_id=(
                        result.id
                        if result.result_source == PdfExtractionResultSource.parser
                        else result.source_result_id
                    ),
                    reviewed_text=result.reviewed_text,
                    reviewed_amount=(
                        float(result.reviewed_amount)
                        if result.reviewed_amount is not None
                        else None
                    ),
                    reviewed_date=result.reviewed_date,
                    review_status=result.review_status.value,
                    reviewer_note=result.reviewer_note,
                )
            )
        return sorted(decisions, key=lambda item: item.field_path)

    def _line_item_candidates(
        self, line_item_results: list[PdfExtractionLineItemResult]
    ) -> list[LineItemCandidate]:
        candidates: list[LineItemCandidate] = []
        for result in line_item_results:
            if result.result_source != PdfExtractionResultSource.parser:
                continue
            candidates.append(
                LineItemCandidate(
                    id=result.id,
                    sort_order=result.sort_order,
                    section_label=result.section_label,
                    line_type=result.line_type.value,
                    description=result.description,
                    quantity=float(result.quantity),
                    unit=result.unit,
                    rate=float(result.rate),
                    amount=float(result.amount),
                    currency_code=result.currency_code,
                    confidence_score=(
                        float(result.confidence_score)
                        if result.confidence_score is not None
                        else None
                    ),
                    confidence_flag=result.confidence_flag.value,
                    page_number=result.page_number,
                    review_status=result.review_status.value,
                    source_snippet=result.source_snippet,
                    source_bounds=result.source_bounds,
                )
            )
        return candidates

    def _line_item_decisions(
        self, line_item_results: list[PdfExtractionLineItemResult]
    ) -> list[LineItemDecision]:
        decisions: list[LineItemDecision] = []
        for result in line_item_results:
            if not result.is_selected:
                continue
            decisions.append(
                LineItemDecision(
                    id=result.id,
                    sort_order=result.sort_order,
                    source_result_id=(
                        result.id
                        if result.result_source == PdfExtractionResultSource.parser
                        else result.source_result_id
                    ),
                    section_label=(
                        result.reviewed_section_label or result.section_label or "General"
                    ),
                    line_type=(result.reviewed_line_type or result.line_type).value,
                    description=result.reviewed_description or result.description,
                    quantity=(
                        float(result.reviewed_quantity)
                        if result.reviewed_quantity is not None
                        else float(result.quantity)
                    ),
                    unit=result.reviewed_unit or result.unit,
                    rate=(
                        float(result.reviewed_rate)
                        if result.reviewed_rate is not None
                        else float(result.rate)
                    ),
                    amount=(
                        float(result.reviewed_amount)
                        if result.reviewed_amount is not None
                        else float(result.amount)
                    ),
                    review_status=result.review_status.value,
                    reviewer_note=result.reviewer_note,
                )
            )
        return sorted(decisions, key=lambda item: item.sort_order)

    def _build_match_suggestions(
        self,
        session: Session,
        run: PdfExtractionRun,
        project_id: str | None,
    ) -> None:
        detail = self._serialize_run(session, run)
        project_title = self._project_title(detail)
        quote_title = self._quote_title(detail) or project_title
        client = self._decision_text(detail, "client.name") or ""
        extracted_quote_number = self._normalize_identifier(
            self._decision_text(detail, "quote.quote_number")
        )

        suggestions: list[MatchSuggestion] = []
        project_suggestions: list[MatchSuggestion] = []
        project_summaries = projects_service.list_projects(session)
        project_summaries_by_id = {
            summary.id: summary for summary in project_summaries
        }
        for rank, project in enumerate(project_summaries, start=1):
            score = self._project_match_score(
                project_name=project.name,
                aliases=[],
                client_name=project.primary_client_name or "",
                extracted_title=project_title,
                extracted_client=client,
                project_hint=project_id,
                project_id=project.id,
            )
            if score < 0.35:
                continue
            reasons = []
            if (
                client
                and project.primary_client_name
                and client.lower() == project.primary_client_name.lower()
            ):
                reasons.append("Client name matches an existing project.")
            if self._token_overlap(project_title, project.name, []) >= 0.5:
                reasons.append("Project title overlaps with an existing project.")
            if project_id and project_id == project.id:
                reasons.append("Project hint matches this project.")
            project_suggestions.append(
                MatchSuggestion(
                    id=f"project-{project.id}",
                    entity_type="project",
                    entity_id=project.id,
                    label=project.name,
                    score=round(score, 2),
                    reasons=reasons or ["Project metadata overlap suggests this match."],
                    rank=rank,
                )
            )

        quote_suggestions: list[MatchSuggestion] = []
        for rank, quote in enumerate(quotes_service.list_quotes(session), start=1):
            stored_quote_number = self._normalize_identifier(quote.quote_number)
            if extracted_quote_number and stored_quote_number == extracted_quote_number:
                reasons = ["Quote ID matches an existing quote."]
                if client:
                    project = project_summaries_by_id.get(quote.project_id)
                    if (
                        project
                        and project.primary_client_name
                        and project.primary_client_name.lower() != client.lower()
                    ):
                        reasons.append(
                            "Client differs from the stored project, which suggests "
                            "a client-entity revision."
                        )
                quote_suggestions.append(
                    MatchSuggestion(
                        id=f"quote-{quote.id}",
                        entity_type="quote",
                        entity_id=quote.id,
                        label=quote.title or quote.id,
                        score=0.99,
                        reasons=reasons,
                        rank=rank,
                    )
                )
                continue
            project_match = next(
                (
                    suggestion
                    for suggestion in project_suggestions
                    if suggestion.entity_id == quote.project_id
                ),
                None,
            )
            title_overlap = max(
                self._token_overlap(quote_title, quote.title or "", []),
                self._token_overlap(project_title, quote.title or "", []),
            )
            score = round(
                min(
                    0.99,
                    0.5 * (project_match.score if project_match else 0.0)
                    + 0.5 * title_overlap,
                ),
                2,
            )
            if score < 0.5:
                continue
            quote_suggestions.append(
                MatchSuggestion(
                    id=f"quote-{quote.id}",
                    entity_type="quote",
                    entity_id=quote.id,
                    label=quote.title or quote.id,
                    score=score,
                    reasons=[
                        "Existing quote belongs to a closely matched project.",
                        "Quote title overlaps with the extracted source title.",
                    ],
                    rank=rank,
                )
            )

        suggestions.extend(sorted(project_suggestions, key=lambda item: item.score, reverse=True))
        suggestions.extend(sorted(quote_suggestions, key=lambda item: item.score, reverse=True))

        selected_quote = max(quote_suggestions, key=lambda item: item.score, default=None)
        selected_project = max(project_suggestions, key=lambda item: item.score, default=None)
        if selected_quote and selected_quote.score >= 0.82:
            run.selected_quote_id = selected_quote.entity_id
            quote = quotes_service.get_quote(session, selected_quote.entity_id)
            run.selected_project_id = quote.project_id
            run.selected_target_mode = PdfExtractionTargetMode.new_version
            selected_quote.is_selected = True
        elif selected_project:
            run.selected_project_id = selected_project.entity_id
            run.selected_target_mode = PdfExtractionTargetMode.new_quote
            selected_project.is_selected = True

        run.match_suggestions_json = [item.model_dump(mode="json") for item in suggestions]

    def _project_match_score(
        self,
        *,
        project_name: str,
        aliases: list[str],
        client_name: str,
        extracted_title: str,
        extracted_client: str,
        project_hint: str | None,
        project_id: str,
    ) -> float:
        score = 0.0
        if extracted_client and client_name and extracted_client.lower() == client_name.lower():
            score += 0.3
        score += 0.6 * self._token_overlap(extracted_title, project_name, aliases)
        if project_hint and project_hint == project_id:
            score += 0.1
        return min(0.99, score)

    def _token_overlap(self, left: str, right: str, aliases: list[str]) -> float:
        left_tokens = set(self._normalize_text(left).split())
        if not left_tokens:
            return 0.0
        candidates = {
            self._normalize_text(right),
            *(self._normalize_text(alias) for alias in aliases),
        }
        best = 0.0
        for candidate in candidates:
            right_tokens = set(candidate.split())
            if not right_tokens:
                continue
            overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
            best = max(best, overlap)
        return best

    def _normalize_text(self, value: str) -> str:
        return "".join(char if char.isalnum() else " " for char in value.lower())

    def _select_default_fields(self, field_results: list[PdfExtractionFieldResult]) -> None:
        best_by_field: dict[str, PdfExtractionFieldResult] = {}
        for result in field_results:
            current = best_by_field.get(result.field_path)
            if current is None or (result.confidence_score or 0.0) > (
                current.confidence_score or 0.0
            ):
                best_by_field[result.field_path] = result
        for result in field_results:
            if best_by_field.get(result.field_path) != result:
                continue
            result.is_selected = True
            result.reviewed_text = result.normalized_text
            result.reviewed_amount = result.normalized_amount
            result.reviewed_date = result.normalized_date

    def _build_confidence_summary(
        self,
        field_results: list[PdfExtractionFieldResult],
        line_item_results: list[PdfExtractionLineItemResult],
    ) -> ConfidenceSummary:
        high = medium = low = 0
        for result in [*field_results, *line_item_results]:
            if result.result_source != PdfExtractionResultSource.parser:
                continue
            flag = result.confidence_flag
            if flag == PdfExtractionConfidenceFlag.high:
                high += 1
            elif flag == PdfExtractionConfidenceFlag.medium:
                medium += 1
            else:
                low += 1
        return ConfidenceSummary(high=high, medium=medium, low=low)

    def _upsert_field_decisions(
        self,
        session: Session,
        run: PdfExtractionRun,
        inputs: list[FieldDecisionInput],
    ) -> None:
        for item in inputs:
            results = list(
                session.scalars(
                    select(PdfExtractionFieldResult).where(
                        PdfExtractionFieldResult.run_id == run.id,
                        PdfExtractionFieldResult.field_path == item.field_path,
                    )
                )
            )
            for result in results:
                result.is_selected = False

            selected: PdfExtractionFieldResult | None = None
            if item.selected_result_id is not None:
                selected = session.get(PdfExtractionFieldResult, item.selected_result_id)
                if (
                    selected is None
                    or selected.run_id != run.id
                    or selected.field_path != item.field_path
                ):
                    raise ApiProblemException(
                        422,
                        (
                            f"Field result '{item.selected_result_id}' is not valid for "
                            f"'{item.field_path}'."
                        ),
                        title="Invalid Review Decision",
                    )
            else:
                selected = next(
                    (
                        result
                        for result in results
                        if result.result_source == PdfExtractionResultSource.reviewer
                        and result.source_result_id is None
                    ),
                    None,
                )
                if selected is None:
                    selected = PdfExtractionFieldResult(
                        run_id=run.id,
                        result_source=PdfExtractionResultSource.reviewer,
                        field_path=item.field_path,
                        occurrence_index=max(
                            (result.occurrence_index for result in results),
                            default=-1,
                        )
                        + 1,
                        confidence_score=None,
                        confidence_flag=PdfExtractionConfidenceFlag.low,
                    )
                    session.add(selected)

            selected.is_selected = True
            selected.review_status = PdfExtractionReviewStatus(item.review_status)
            selected.reviewer_note = item.reviewer_note
            selected.reviewed_text = (
                item.reviewed_text
                if item.reviewed_text is not None
                else selected.normalized_text
            )
            selected.reviewed_amount = (
                item.reviewed_amount
                if item.reviewed_amount is not None
                else selected.normalized_amount
            )
            selected.reviewed_date = (
                item.reviewed_date
                if item.reviewed_date is not None
                else selected.normalized_date
            )

    def _upsert_line_item_decisions(
        self,
        session: Session,
        run: PdfExtractionRun,
        inputs: list[LineItemDecisionInput],
    ) -> None:
        for item in inputs:
            results = list(
                session.scalars(
                    select(PdfExtractionLineItemResult).where(
                        PdfExtractionLineItemResult.run_id == run.id,
                        PdfExtractionLineItemResult.sort_order == item.sort_order,
                    )
                )
            )
            for result in results:
                result.is_selected = False

            selected: PdfExtractionLineItemResult | None = None
            if item.source_result_id is not None:
                selected = session.get(PdfExtractionLineItemResult, item.source_result_id)
                if (
                    selected is None
                    or selected.run_id != run.id
                    or selected.sort_order != item.sort_order
                ):
                    raise ApiProblemException(
                        422,
                        (
                            f"Line-item result '{item.source_result_id}' is not valid for "
                            f"sort order {item.sort_order}."
                        ),
                        title="Invalid Review Decision",
                    )
            else:
                selected = next(
                    (
                        result
                        for result in results
                        if result.result_source == PdfExtractionResultSource.reviewer
                        and result.source_result_id is None
                    ),
                    None,
                )
                if selected is None:
                    selected = PdfExtractionLineItemResult(
                        run_id=run.id,
                        result_source=PdfExtractionResultSource.reviewer,
                        sort_order=item.sort_order,
                        section_label=item.section_label,
                        line_type=QuoteLineItemType(item.line_type),
                        description=item.description,
                        quantity=item.quantity,
                        unit=item.unit,
                        rate=item.rate,
                        amount=item.amount,
                        confidence_score=None,
                        confidence_flag=PdfExtractionConfidenceFlag.low,
                    )
                    session.add(selected)

            selected.is_selected = True
            selected.review_status = PdfExtractionReviewStatus(item.review_status)
            selected.reviewer_note = item.reviewer_note
            selected.reviewed_section_label = item.section_label
            selected.reviewed_line_type = QuoteLineItemType(item.line_type)
            selected.reviewed_description = item.description
            selected.reviewed_quantity = item.quantity
            selected.reviewed_unit = item.unit
            selected.reviewed_rate = item.rate
            selected.reviewed_amount = item.amount

    def _build_approval_blockers(self, run: QuoteIngestionRunDetail) -> list[ApprovalBlocker]:
        blockers: list[ApprovalBlocker] = []
        if run.status in {"queued", "processing"}:
            return [
                ApprovalBlocker(
                    code="run.awaiting_parse",
                    message="Parsing has not completed yet. Wait for worker results.",
                )
            ]
        if run.status == "rejected":
            return [
                ApprovalBlocker(
                    code="run.rejected",
                    message="This run was rejected and cannot be approved.",
                )
            ]
        if run.status == "approved":
            return blockers
        if run.status == "failed":
            blockers.append(
                ApprovalBlocker(
                    code="run.failed",
                    message="This run failed parsing and must be rerun or handled manually.",
                )
            )
            return blockers
        if not run.selected_project_id:
            blockers.append(
                ApprovalBlocker(
                    code="target.project_required",
                    message="Select the target project before approval.",
                )
            )
        if not run.selected_target_mode:
            blockers.append(
                ApprovalBlocker(
                    code="target.mode_required",
                    message="Choose whether this creates a new quote or a new version.",
                )
            )
        if run.selected_target_mode == "new_version" and not run.selected_quote_id:
            blockers.append(
                ApprovalBlocker(
                    code="target.quote_required",
                    message="Select the target quote before creating a new version.",
                )
            )
        decisions_by_field = {decision.field_path: decision for decision in run.field_decisions}
        if not self._quote_title(run, approved_only=True):
            blockers.append(
                ApprovalBlocker(
                    code="field.quote.title.pending",
                    message=(
                        "Approve or correct 'quote.title' or 'project.title' "
                        "before approval."
                    ),
                )
            )
        for field_path in REQUIRED_FIELD_PATHS:
            decision = decisions_by_field.get(field_path)
            if decision is None or decision.review_status != "approved":
                blockers.append(
                    ApprovalBlocker(
                        code=f"field.{field_path}.pending",
                        message=f"Approve or correct '{field_path}' before approval.",
                    )
                )
                continue
            if self._decision_has_no_value(decision):
                blockers.append(
                    ApprovalBlocker(
                        code=f"field.{field_path}.missing_value",
                        message=f"'{field_path}' still needs a reviewed value.",
                    )
                )
        pending_lines = [
            item
            for item in run.line_item_decisions
            if item.review_status not in {"approved", "rejected"}
        ]
        if pending_lines:
            blockers.append(
                ApprovalBlocker(
                    code="line_items.pending",
                    message=(
                        "Every extracted or manually added line item must be approved "
                        "or rejected."
                    ),
                )
            )
        warning_codes = {warning.code for warning in run.warnings if warning.blocking}
        unresolved_codes = warning_codes - set(run.acknowledged_warning_codes)
        if "totals.mismatch" in unresolved_codes:
            reviewed_total = self._decision_amount(
                run,
                "totals.total",
                approved_only=True,
            )
            if reviewed_total is None or abs(
                reviewed_total - self._approved_line_item_total(run)
            ) > 0.01:
                blockers.append(
                    ApprovalBlocker(
                        code="warning.totals_mismatch",
                        message="Resolve or acknowledge the totals mismatch before approval.",
                    )
                )
            unresolved_codes.remove("totals.mismatch")
        for code in sorted(unresolved_codes):
            blockers.append(
                ApprovalBlocker(
                    code=f"warning.{code}",
                    message=f"Acknowledge the blocking warning '{code}' before approval.",
                )
            )
        return blockers

    def _build_approval_preview(
        self,
        session: Session,
        run: QuoteIngestionRunDetail,
    ) -> ApprovalPreview:
        next_version_number = None
        if run.selected_target_mode == "new_version" and run.selected_quote_id:
            quote = quotes_service.get_quote(session, run.selected_quote_id)
            next_version_number = (
                max((version.version_number for version in quote.versions), default=0) + 1
            )
        elif run.selected_project_id:
            next_version_number = 1
        return ApprovalPreview(
            project_id=run.selected_project_id,
            quote_id=run.selected_quote_id,
            target_mode=run.selected_target_mode,
            next_version_number=next_version_number,
            title=self._quote_title(run, approved_only=True),
            source_version_label=self._decision_text(
                run,
                "quote.source_version_label",
            ),
            total_amount=self._decision_amount(
                run,
                "totals.total",
                approved_only=True,
            ),
        )

    def _approved_line_item_total(self, run: QuoteIngestionRunDetail) -> float:
        return round(
            sum(
                item.amount
                for item in run.line_item_decisions
                if item.review_status == "approved"
            ),
            2,
        )

    def _decision_text(
        self,
        run: QuoteIngestionRunDetail,
        field_path: str,
        *,
        approved_only: bool = False,
    ) -> str | None:
        decision = next(
            (
                item
                for item in run.field_decisions
                if item.field_path == field_path
                and (
                    not approved_only
                    or item.review_status == PdfExtractionReviewStatus.approved.value
                )
            ),
            None,
        )
        return decision.reviewed_text if decision else None

    def _quote_title(
        self,
        run: QuoteIngestionRunDetail,
        *,
        approved_only: bool = False,
    ) -> str | None:
        return self._decision_text(
            run,
            "quote.title",
            approved_only=approved_only,
        ) or self._decision_text(
            run,
            "project.title",
            approved_only=approved_only,
        )

    def _project_title(self, run: QuoteIngestionRunDetail) -> str:
        project_title = self._decision_text(run, "project.title")
        if project_title:
            return project_title
        return self._project_title_from_quote_title(self._quote_title(run) or "")

    def _decision_amount(
        self,
        run: QuoteIngestionRunDetail,
        field_path: str,
        *,
        approved_only: bool = False,
    ) -> float | None:
        decision = next(
            (
                item
                for item in run.field_decisions
                if item.field_path == field_path
                and (
                    not approved_only
                    or item.review_status == PdfExtractionReviewStatus.approved.value
                )
            ),
            None,
        )
        return decision.reviewed_amount if decision else None

    def _decision_date(
        self,
        run: QuoteIngestionRunDetail,
        field_path: str,
        *,
        approved_only: bool = False,
    ):
        decision = next(
            (
                item
                for item in run.field_decisions
                if item.field_path == field_path
                and (
                    not approved_only
                    or item.review_status == PdfExtractionReviewStatus.approved.value
                )
            ),
            None,
        )
        return decision.reviewed_date if decision else None

    def _decision_texts(
        self,
        run: QuoteIngestionRunDetail,
        *,
        prefix: str,
        approved_only: bool = False,
    ) -> list[str]:
        values = [
            decision.reviewed_text
            for decision in sorted(run.field_decisions, key=lambda item: item.field_path)
            if decision.field_path.startswith(prefix)
            and (
                not approved_only
                or decision.review_status == PdfExtractionReviewStatus.approved.value
            )
            and decision.reviewed_text
        ]
        return [value for value in values if value]

    def _decision_has_no_value(self, decision: FieldDecision) -> bool:
        return (
            decision.reviewed_text is None
            and decision.reviewed_amount is None
            and decision.reviewed_date is None
        )

    def _project_title_from_quote_title(self, value: str) -> str:
        for separator in (" - ", " – ", " — "):
            if separator in value:
                return value.split(separator, maxsplit=1)[0].strip()
        return value

    def _normalize_identifier(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = "".join(char for char in value.upper() if char.isalnum())
        return normalized or None

    def _refresh_match_selection(self, run: PdfExtractionRun) -> None:
        suggestions: list[dict[str, object]] = []
        for suggestion in run.match_suggestions_json:
            updated = dict(suggestion)
            updated["is_selected"] = False
            if (
                run.selected_target_mode == PdfExtractionTargetMode.new_version
                and updated.get("entity_id") == run.selected_quote_id
            ):
                updated["is_selected"] = True
            if (
                run.selected_target_mode == PdfExtractionTargetMode.new_quote
                and updated.get("entity_type") == "project"
                and updated.get("entity_id") == run.selected_project_id
            ):
                updated["is_selected"] = True
            suggestions.append(updated)
        run.match_suggestions_json = suggestions

    def _file_summary(self, file: UploadedFileRead) -> QuoteIngestionFileSummary:
        return QuoteIngestionFileSummary(
            file_id=file.file_id,
            file_name=file.file_name,
            object_key=file.object_key,
            file_category=file.file_category,
            status=file.status,
            download_url=file.download_url,
            public_url=file.public_url,
        )

    def _require_uploaded_file(self, session: Session, file_id: str) -> UploadedFileRead:
        uploaded_file = files_service.get(session, file_id)
        if uploaded_file is None:
            raise ApiProblemException(
                404,
                f"Uploaded file '{file_id}' was not found.",
                title="Uploaded File Not Found",
            )
        return uploaded_file

    def _require_project(self, session: Session, project_id: str):
        return projects_service.get_project(session, project_id)

    def _require_quote(self, session: Session, quote_id: str):
        return quotes_service.get_quote(session, quote_id)

    def _get_run_entity(self, session: Session, run_id: str) -> PdfExtractionRun:
        run = session.get(PdfExtractionRun, run_id)
        if run is None:
            raise ApiProblemException(
                404,
                f"Quote ingestion run '{run_id}' was not found.",
                title="Quote Ingestion Run Not Found",
            )
        return run

    def _to_summary(self, run: QuoteIngestionRunDetail) -> QuoteIngestionRunSummary:
        return QuoteIngestionRunSummary(
            id=run.id,
            status=run.status,
            uploaded_file_id=run.uploaded_file_id,
            file_name=run.file.file_name,
            parser_name=run.parser_name,
            parser_version=run.parser_version,
            parser_profile=run.parser_profile,
            page_count=run.page_count,
            text_page_count=run.text_page_count,
            failure_code=run.failure_code,
            failure_message=run.failure_message,
            selected_project_id=run.selected_project_id,
            selected_quote_id=run.selected_quote_id,
            selected_target_mode=run.selected_target_mode,
            approved_quote_id=run.approved_quote_id,
            approved_quote_version_id=run.approved_quote_version_id,
            job_id=run.job_id,
            queue_name=run.queue_name,
            review_mode=run.review_mode,
            approved_at=run.approved_at,
            rejected_at=run.rejected_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    def _confidence_flag(self, score: float | None) -> PdfExtractionConfidenceFlag:
        if score is None:
            return PdfExtractionConfidenceFlag.low
        if score >= 0.9:
            return PdfExtractionConfidenceFlag.high
        if score >= 0.7:
            return PdfExtractionConfidenceFlag.medium
        return PdfExtractionConfidenceFlag.low


quote_ingestion_service = QuoteIngestionService()
