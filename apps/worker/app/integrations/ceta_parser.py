from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class CetaParseIssue:
    severity: str
    issue_code: str
    message: str
    field_name: str | None = None
    details: dict[str, object] | None = None


@dataclass(frozen=True)
class CetaParsedRow:
    row_number: int
    source_row_uid: str | None
    row_hash: str
    business_key_hash: str
    duplicate_group_key: str | None
    external_project_code: str | None
    normalized_project_code: str | None
    work_date: date | None
    posting_date: date | None
    source_discipline_code: str | None
    description: str | None
    normalized_description: str | None
    vendor_name: str | None
    normalized_vendor_name: str | None
    amount: float
    currency_code: str
    financial_type: str
    raw_payload: dict[str, object]
    issues: list[CetaParseIssue] = field(default_factory=list)


@dataclass(frozen=True)
class CetaParseResult:
    parser_name: str
    parser_version: str
    parser_profile: str
    source_system: str
    coverage_start: date | None
    coverage_end: date | None
    batch_issues: list[CetaParseIssue]
    rows: list[CetaParsedRow]


class CetaParseError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().lower().split())
    return normalized or None


def _hash_fields(payload: dict[str, object]) -> str:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _build_row(
    *,
    row_number: int,
    source_row_uid: str | None,
    external_project_code: str | None,
    work_date: date | None,
    posting_date: date | None,
    source_discipline_code: str | None,
    description: str | None,
    vendor_name: str | None,
    amount: float,
    currency_code: str,
    financial_type: str,
    raw_payload: dict[str, object],
    issues: list[CetaParseIssue] | None = None,
) -> CetaParsedRow:
    normalized_project_code = _normalize_text(external_project_code)
    normalized_description = _normalize_text(description)
    normalized_vendor_name = _normalize_text(vendor_name)
    business_key_hash = _hash_fields(
        {
            "externalProjectCode": normalized_project_code,
            "workDate": work_date.isoformat() if work_date else None,
            "postingDate": posting_date.isoformat() if posting_date else None,
            "sourceDisciplineCode": _normalize_text(source_discipline_code),
            "description": normalized_description,
            "vendorName": normalized_vendor_name,
            "financialType": financial_type,
        }
    )
    row_hash = _hash_fields(
        {
            "businessKeyHash": business_key_hash,
            "amount": amount,
            "currencyCode": currency_code,
            "rawPayload": raw_payload,
        }
    )
    return CetaParsedRow(
        row_number=row_number,
        source_row_uid=source_row_uid,
        row_hash=row_hash,
        business_key_hash=business_key_hash,
        duplicate_group_key=None,
        external_project_code=external_project_code,
        normalized_project_code=normalized_project_code,
        work_date=work_date,
        posting_date=posting_date,
        source_discipline_code=source_discipline_code,
        description=description,
        normalized_description=normalized_description,
        vendor_name=vendor_name,
        normalized_vendor_name=normalized_vendor_name,
        amount=amount,
        currency_code=currency_code,
        financial_type=financial_type,
        raw_payload=raw_payload,
        issues=issues or [],
    )


class CetaParser:
    def parse(self, *, object_key: str, parser_profile: str | None = None) -> CetaParseResult:
        key = object_key.lower()
        profile = parser_profile or self._detect_profile(key)
        if "fail" in key:
            raise CetaParseError(
                "unsupported_ceta_export",
                "The CETA export could not be recognized as a supported layout.",
            )

        if profile == "vendor-summary":
            return self._vendor_summary_result()
        if profile == "revenue-mixed":
            return self._revenue_mixed_result()
        return self._generic_ledger_result()

    def _detect_profile(self, key: str) -> str:
        if "vendor" in key:
            return "vendor-summary"
        if "revenue" in key or "mixed" in key:
            return "revenue-mixed"
        return "generic-ledger"

    def _generic_ledger_result(self) -> CetaParseResult:
        rows = [
            _build_row(
                row_number=1,
                source_row_uid="GL-001",
                external_project_code="BGS1-TRAILER",
                work_date=date(2026, 4, 8),
                posting_date=date(2026, 4, 8),
                source_discipline_code="online",
                description="Conform suite",
                vendor_name="Halo Post",
                amount=2350.0,
                currency_code="GBP",
                financial_type="cost",
                raw_payload={
                    "projectCode": "BGS1-TRAILER",
                    "workDate": "2026-04-08",
                    "department": "online",
                    "description": "Conform suite",
                    "vendor": "Halo Post",
                    "amount": 2350.0,
                    "currency": "GBP",
                    "financialType": "cost",
                },
            ),
            _build_row(
                row_number=2,
                source_row_uid="GL-002",
                external_project_code="BGS1-TRAILER",
                work_date=date(2026, 4, 11),
                posting_date=date(2026, 4, 11),
                source_discipline_code="grade",
                description="Colour theatre",
                vendor_name="Halo Post",
                amount=4100.0,
                currency_code="GBP",
                financial_type="cost",
                raw_payload={
                    "projectCode": "BGS1-TRAILER",
                    "workDate": "2026-04-11",
                    "department": "grade",
                    "description": "Colour theatre",
                    "vendor": "Halo Post",
                    "amount": 4100.0,
                    "currency": "GBP",
                    "financialType": "cost",
                },
            ),
            _build_row(
                row_number=3,
                source_row_uid="GL-003",
                external_project_code="BGS1-TRAILER",
                work_date=date(2026, 4, 15),
                posting_date=date(2026, 4, 15),
                source_discipline_code="delivery",
                description="Client re-bill",
                vendor_name="BBC Studios",
                amount=1800.0,
                currency_code="GBP",
                financial_type="revenue",
                raw_payload={
                    "projectCode": "BGS1-TRAILER",
                    "workDate": "2026-04-15",
                    "department": "delivery",
                    "description": "Client re-bill",
                    "vendor": "BBC Studios",
                    "amount": 1800.0,
                    "currency": "GBP",
                    "financialType": "revenue",
                },
            ),
        ]
        return CetaParseResult(
            parser_name="ceta-generic-ledger-parser",
            parser_version="2026.03.31",
            parser_profile="generic-ledger",
            source_system="ceta",
            coverage_start=date(2026, 4, 1),
            coverage_end=date(2026, 4, 30),
            batch_issues=[],
            rows=rows,
        )

    def _vendor_summary_result(self) -> CetaParseResult:
        row_one = _build_row(
            row_number=1,
            source_row_uid="VS-001",
            external_project_code="REDROOM-S1",
            work_date=date(2026, 5, 4),
            posting_date=date(2026, 5, 5),
            source_discipline_code=None,
            description="Assistant edit prep",
            vendor_name="North Star Offline",
            amount=950.0,
            currency_code="GBP",
            financial_type="cost",
            raw_payload={
                "projectRef": "REDROOM-S1",
                "bookedDate": "2026-05-04",
                "service": "Assistant edit prep",
                "vendorName": "North Star Offline",
                "amountGbp": 950.0,
                "type": "cost",
            },
        )
        row_two = _build_row(
            row_number=2,
            source_row_uid="VS-002",
            external_project_code="REDROOM-S1",
            work_date=date(2026, 5, 4),
            posting_date=date(2026, 5, 5),
            source_discipline_code=None,
            description="Assistant edit prep",
            vendor_name="North Star Offline",
            amount=950.0,
            currency_code="GBP",
            financial_type="cost",
            raw_payload={
                "projectRef": "REDROOM-S1",
                "bookedDate": "2026-05-04",
                "service": "Assistant edit prep",
                "vendorName": "North Star Offline",
                "amountGbp": 950.0,
                "type": "cost",
            },
        )
        row_two = CetaParsedRow(
            **{
                **row_two.__dict__,
                "duplicate_group_key": row_one.row_hash,
                "issues": [
                    CetaParseIssue(
                        severity="warning",
                        issue_code="duplicate_row",
                        message="This row appears to duplicate another row in the same export.",
                    )
                ],
            }
        )
        return CetaParseResult(
            parser_name="ceta-vendor-summary-parser",
            parser_version="2026.03.31",
            parser_profile="vendor-summary",
            source_system="ceta",
            coverage_start=date(2026, 5, 1),
            coverage_end=date(2026, 5, 31),
            batch_issues=[],
            rows=[row_one, row_two],
        )

    def _revenue_mixed_result(self) -> CetaParseResult:
        rows = [
            _build_row(
                row_number=1,
                source_row_uid="RM-001",
                external_project_code="BGS1-TRAILER",
                work_date=date(2026, 6, 2),
                posting_date=date(2026, 6, 2),
                source_discipline_code="offline",
                description="Edit assist prep",
                vendor_name="BBC Studios",
                amount=1200.0,
                currency_code="GBP",
                financial_type="revenue",
                raw_payload={
                    "project": "BGS1-TRAILER",
                    "date": "2026-06-02",
                    "discipline": "offline",
                    "description": "Edit assist prep",
                    "counterparty": "BBC Studios",
                    "amount": 1200.0,
                    "currency": "GBP",
                    "kind": "revenue",
                },
            ),
            _build_row(
                row_number=2,
                source_row_uid="RM-002",
                external_project_code=None,
                work_date=date(2026, 6, 9),
                posting_date=date(2026, 6, 9),
                source_discipline_code="mix",
                description="5.1 mix day",
                vendor_name="North Star Audio",
                amount=780.0,
                currency_code="GBP",
                financial_type="cost",
                raw_payload={
                    "project": None,
                    "date": "2026-06-09",
                    "discipline": "mix",
                    "description": "5.1 mix day",
                    "counterparty": "North Star Audio",
                    "amount": 780.0,
                    "currency": "GBP",
                    "kind": "cost",
                },
                issues=[
                    CetaParseIssue(
                        severity="blocking",
                        issue_code="missing_project_code",
                        field_name="project",
                        message="The source row does not include a project code.",
                    )
                ],
            ),
        ]
        return CetaParseResult(
            parser_name="ceta-revenue-mixed-parser",
            parser_version="2026.03.31",
            parser_profile="revenue-mixed",
            source_system="ceta",
            coverage_start=date(2026, 6, 1),
            coverage_end=date(2026, 6, 30),
            batch_issues=[],
            rows=rows,
        )


ceta_parser = CetaParser()
