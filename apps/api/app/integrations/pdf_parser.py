from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pdfplumber

from app.integrations.storage import object_storage_service


@dataclass(frozen=True)
class ParseWarning:
    code: str
    message: str
    severity: str
    blocking: bool = False


@dataclass(frozen=True)
class CandidateField:
    field_path: str
    occurrence_index: int
    raw_value: str | None
    normalized_text: str | None
    normalized_amount: float | None
    normalized_date: date | None
    confidence: float
    page_number: int
    source_snippet: str
    source_bounds: dict[str, object]


@dataclass(frozen=True)
class CandidateLineItem:
    section_name: str
    description: str
    quantity: float
    unit: str
    rate: float
    amount: float
    confidence: float
    page_number: int
    source_snippet: str
    source_bounds: dict[str, object]


@dataclass(frozen=True)
class PdfParseResult:
    parser_name: str
    parser_version: str
    parser_profile: str
    page_count: int
    text_page_count: int
    raw_text: str
    warnings: list[ParseWarning]
    field_candidates: list[CandidateField]
    candidate_line_items: list[CandidateLineItem]


@dataclass
class ParsedLineItemCandidate:
    section_name: str
    description: str
    quantity: float
    unit: str
    rate: float
    amount: float
    confidence: float
    page_number: int
    source_bounds: dict[str, object]
    source_lines: list[str]


class QuotePdfParseError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class QuotePdfParser:
    _header_break_markers = (
        "Bid Prepared by:",
        "Bid Prepared for:",
        "Bid Prepared on:",
        "Estimate prepared for:",
        "Estimate prepared by:",
        "COMMENTS | BID ASSUMPTIONS",
        "ESTIMATE COMMENTS / ASSUMPTIONS:",
        "SECTION SUMMARY",
    )
    _skip_prefixes = (
        "This estimate is not authorised",
        "CONFIDENTIAL |",
        "CONFIRMATION TERMS",
        "By signing this page",
        "APPROVAL",
        "Signature",
        "Print Name",
        "Date Date",
    )
    _number_token_re = re.compile(r"^\d[\d,]*(?:\.\d+)?$")
    _header_row_re = re.compile(r"^ITEM\s+QTY\s+TIME\s+RATE\s+UNITS\s+TOTAL$")
    _grand_total_re = re.compile(
        r"GRAND TOTAL:\s*(?P<amount>\d[\d,]*\.\d{2})(?:\s+(?P<currency>[A-Z]{3}))?",
        re.IGNORECASE,
    )
    _rate_suffix_re = re.compile(
        r"(?P<rate>-?\d[\d,]*\.\d{2})\s*/\s*(?P<unit>[A-Za-z]+)\s+"
        r"(?P<amount>-?\d[\d,]*\.\d{2})$"
    )
    _currency_re = re.compile(r"\b(?P<currency>GBP|USD|EUR)\b", re.IGNORECASE)
    _date_re = re.compile(r"DATE:\s*(?P<value>.+)$")
    _title_re = re.compile(r"TITLE:\s*(?P<value>.+)$")
    _client_re = re.compile(r"CLIENT:\s*(?P<value>.+)$")
    _contact_re = re.compile(r"CONTACT:\s*(?P<value>.+)$")
    _job_number_re = re.compile(r"JOB NO:\s*(?P<value>[A-Z0-9-]+)", re.IGNORECASE)
    _quote_id_re = re.compile(r"QUOTE ID:\s*(?P<value>[A-Z0-9-]+)", re.IGNORECASE)
    _ordinal_suffix_re = re.compile(r"(?P<day>\d+)(?:st|nd|rd|th)")
    _version_re = re.compile(
        r"(?<![A-Za-z])(?P<label>v\d+|latest)(?![A-Za-z])", re.IGNORECASE
    )

    def parse(self, *, object_key: str, parser_profile: str | None = None) -> PdfParseResult:
        parser_version = "2026.03.31"
        try:
            source_bytes = object_storage_service.read_object_bytes(object_key)
        except Exception as exc:  # pragma: no cover - exercised through worker/API integration
            raise QuotePdfParseError(
                "source_unavailable",
                f"The source PDF '{object_key}' could not be loaded from storage.",
            ) from exc

        page_texts = self._extract_page_texts(source_bytes)
        page_count = len(page_texts)
        text_page_count = sum(1 for text in page_texts if text.strip())
        if page_count == 0 or text_page_count == 0:
            raise QuotePdfParseError(
                "unreadable_pdf",
                "The PDF could not be profiled into usable text output.",
            )

        profile = parser_profile or self._detect_profile(object_key, page_texts)
        parser_name = {
            "harbor-estimate": "harbor-estimate-parser",
            "generic-layout": "generic-layout-parser",
        }.get(profile, "generic-layout-parser")
        raw_text = "\n\n".join(
            f"=== Page {page_number} ===\n{page_text}".strip()
            for page_number, page_text in enumerate(page_texts, start=1)
        )

        warnings: list[ParseWarning] = []
        if text_page_count < page_count:
            warnings.append(
                ParseWarning(
                    code="ocr.low_confidence",
                    message="One or more pages did not contain reliable extractable text.",
                    severity="warning",
                )
            )

        fields: list[CandidateField] = []
        occurrence_counts: dict[str, int] = {}
        first_page_lines = self._page_lines(page_texts[0])

        self._append_header_fields(
            fields,
            occurrence_counts,
            first_page_lines,
            object_key=object_key,
            profile=profile,
        )

        assumptions, notes = self._extract_assumptions_and_notes(first_page_lines)
        for index, value in enumerate(assumptions):
            self._append_field(
                fields,
                occurrence_counts,
                field_path=f"assumptions[{index}]",
                raw_value=value,
                normalized_text=value,
                confidence=0.82,
                page_number=1,
                source_snippet=value,
                line_number=self._find_line_number(first_page_lines, value),
            )
        for index, value in enumerate(notes):
            self._append_field(
                fields,
                occurrence_counts,
                field_path=f"notes[{index}]",
                raw_value=value,
                normalized_text=value,
                confidence=0.78,
                page_number=1,
                source_snippet=value,
                line_number=self._find_line_number(first_page_lines, value),
            )

        line_items = self._extract_line_items(page_texts)
        explicit_total = self._extract_explicit_total(page_texts)
        currency_code = explicit_total["currency"] if explicit_total else None
        if currency_code is None:
            currency_code = self._detect_currency(page_texts) or (
                "GBP" if profile == "harbor-estimate" else None
            )
        if currency_code:
            self._append_field(
                fields,
                occurrence_counts,
                field_path="quote.currency_code",
                raw_value=currency_code,
                normalized_text=currency_code,
                confidence=0.96 if explicit_total else 0.72,
                page_number=explicit_total["page_number"] if explicit_total else 1,
                source_snippet=(
                    explicit_total["snippet"]
                    if explicit_total
                    else f"Currency inferred as {currency_code}"
                ),
                line_number=explicit_total["line_number"] if explicit_total else None,
            )

        explicit_total_amount = explicit_total["amount"] if explicit_total else None
        computed_total_amount = (
            round(sum(item.amount for item in line_items), 2)
            if line_items
            else None
        )
        if explicit_total_amount is not None:
            self._append_field(
                fields,
                occurrence_counts,
                field_path="totals.total",
                raw_value=self._format_amount(explicit_total_amount),
                normalized_amount=explicit_total_amount,
                confidence=0.97,
                page_number=explicit_total["page_number"],
                source_snippet=explicit_total["snippet"],
                line_number=explicit_total["line_number"],
            )
            self._append_field(
                fields,
                occurrence_counts,
                field_path="totals.subtotal",
                raw_value=self._format_amount(explicit_total_amount),
                normalized_amount=explicit_total_amount,
                confidence=0.89,
                page_number=explicit_total["page_number"],
                source_snippet=explicit_total["snippet"],
                line_number=explicit_total["line_number"],
            )
            self._append_field(
                fields,
                occurrence_counts,
                field_path="totals.tax",
                raw_value="0.00",
                normalized_amount=0.0,
                confidence=0.84,
                page_number=explicit_total["page_number"],
                source_snippet=explicit_total["snippet"],
                line_number=explicit_total["line_number"],
            )
        elif computed_total_amount is not None:
            warnings.append(
                ParseWarning(
                    code="totals.inferred_from_line_items",
                    message=(
                        "No explicit grand total was found; "
                        "the total was inferred from parsed line items."
                    ),
                    severity="warning",
                )
            )
            self._append_field(
                fields,
                occurrence_counts,
                field_path="totals.total",
                raw_value=self._format_amount(computed_total_amount),
                normalized_amount=computed_total_amount,
                confidence=0.79,
                page_number=line_items[-1].page_number,
                source_snippet="Inferred from approved line-item arithmetic.",
            )
            self._append_field(
                fields,
                occurrence_counts,
                field_path="totals.subtotal",
                raw_value=self._format_amount(computed_total_amount),
                normalized_amount=computed_total_amount,
                confidence=0.79,
                page_number=line_items[-1].page_number,
                source_snippet="Inferred from approved line-item arithmetic.",
            )
            self._append_field(
                fields,
                occurrence_counts,
                field_path="totals.tax",
                raw_value="0.00",
                normalized_amount=0.0,
                confidence=0.76,
                page_number=line_items[-1].page_number,
                source_snippet="No explicit tax line was found in the source PDF.",
            )
        else:
            warnings.append(
                ParseWarning(
                    code="field.missing_total",
                    message="The parser could not identify a reliable grand total.",
                    severity="error",
                    blocking=True,
                )
            )

        if explicit_total_amount is not None and computed_total_amount is not None:
            if abs(explicit_total_amount - computed_total_amount) > 0.01:
                warnings.append(
                    ParseWarning(
                        code="totals.mismatch",
                        message="Extracted totals do not equal the sum of extracted line items.",
                        severity="error",
                        blocking=True,
                    )
                )

        return PdfParseResult(
            parser_name=parser_name,
            parser_version=parser_version,
            parser_profile=profile,
            page_count=page_count,
            text_page_count=text_page_count,
            raw_text=raw_text,
            warnings=warnings,
            field_candidates=fields,
            candidate_line_items=[
                CandidateLineItem(
                    section_name=item.section_name,
                    description=item.description,
                    quantity=item.quantity,
                    unit=item.unit,
                    rate=item.rate,
                    amount=item.amount,
                    confidence=item.confidence,
                    page_number=item.page_number,
                    source_snippet="\n".join(item.source_lines),
                    source_bounds=item.source_bounds,
                )
                for item in line_items
            ],
        )

    def _detect_profile(self, object_key: str, page_texts: list[str]) -> str:
        joined = "\n".join(page_texts[:2]).lower()
        key = object_key.lower()
        if "quote breakdown" in joined and "quote id:" in joined:
            return "harbor-estimate"
        if "harbor" in joined or "turnmill" in joined or "estimate is not authorised" in joined:
            return "harbor-estimate"
        if "harbor" in key or "quote" in key:
            return "generic-layout"
        return "generic-layout"

    def _extract_page_texts(self, source_bytes: bytes) -> list[str]:
        try:
            with pdfplumber.open(BytesIO(source_bytes)) as pdf:
                return [
                    page.extract_text(x_tolerance=2, y_tolerance=2) or ""
                    for page in pdf.pages
                ]
        except Exception as exc:  # pragma: no cover - depends on parser backend failures
            raise QuotePdfParseError(
                "unreadable_pdf",
                "The PDF could not be profiled into usable text output.",
            ) from exc

    def _page_lines(self, page_text: str) -> list[str]:
        return [line for line in (self._clean_line(raw) for raw in page_text.splitlines()) if line]

    def _clean_line(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def _append_header_fields(
        self,
        fields: list[CandidateField],
        occurrence_counts: dict[str, int],
        first_page_lines: list[str],
        *,
        object_key: str,
        profile: str,
    ) -> None:
        date_match = self._search_lines(first_page_lines, self._date_re)
        if date_match:
            normalized_date = self._parse_document_date(date_match["value"])
            if normalized_date is not None:
                self._append_field(
                    fields,
                    occurrence_counts,
                    field_path="quote.date",
                    raw_value=date_match["value"],
                    normalized_date=normalized_date,
                    confidence=0.97,
                    page_number=1,
                    source_snippet=date_match["snippet"],
                    line_number=date_match["line_number"],
                )

        title_match = self._search_lines(first_page_lines, self._title_re)
        quote_title = title_match["value"] if title_match else None
        if quote_title:
            self._append_field(
                fields,
                occurrence_counts,
                field_path="quote.title",
                raw_value=quote_title,
                normalized_text=quote_title,
                confidence=0.98,
                page_number=1,
                source_snippet=title_match["snippet"],
                line_number=title_match["line_number"],
            )

        client_match = self._search_lines(first_page_lines, self._client_re)
        if client_match:
            self._append_field(
                fields,
                occurrence_counts,
                field_path="client.name",
                raw_value=client_match["value"],
                normalized_text=client_match["value"],
                confidence=0.97,
                page_number=1,
                source_snippet=client_match["snippet"],
                line_number=client_match["line_number"],
            )

        contact_match = self._search_lines(first_page_lines, self._contact_re)
        if contact_match:
            self._append_field(
                fields,
                occurrence_counts,
                field_path="client.contact_name",
                raw_value=contact_match["value"],
                normalized_text=contact_match["value"],
                confidence=0.92,
                page_number=1,
                source_snippet=contact_match["snippet"],
                line_number=contact_match["line_number"],
            )

        quote_id_match = self._search_lines(first_page_lines, self._quote_id_re)
        if quote_id_match:
            self._append_field(
                fields,
                occurrence_counts,
                field_path="quote.quote_number",
                raw_value=quote_id_match["value"],
                normalized_text=quote_id_match["value"],
                confidence=0.99,
                page_number=1,
                source_snippet=quote_id_match["snippet"],
                line_number=quote_id_match["line_number"],
            )

        job_number_match = self._search_lines(first_page_lines, self._job_number_re)
        if job_number_match:
            self._append_field(
                fields,
                occurrence_counts,
                field_path="source.job_number",
                raw_value=job_number_match["value"],
                normalized_text=job_number_match["value"],
                confidence=0.95,
                page_number=1,
                source_snippet=job_number_match["snippet"],
                line_number=job_number_match["line_number"],
            )

        project_title = self._extract_project_title(first_page_lines)
        if project_title is None and quote_title is not None:
            project_title = self._derive_project_title(quote_title)
        if project_title:
            self._append_field(
                fields,
                occurrence_counts,
                field_path="project.title",
                raw_value=project_title,
                normalized_text=project_title,
                confidence=0.84 if quote_id_match else 0.74,
                page_number=1,
                source_snippet=project_title,
                line_number=self._find_line_number(first_page_lines, project_title),
            )

        version_label, version_snippet = self._extract_version_label(quote_title, object_key)
        if version_label:
            self._append_field(
                fields,
                occurrence_counts,
                field_path="quote.source_version_label",
                raw_value=version_label,
                normalized_text=version_label,
                confidence=0.9 if quote_title and version_label in quote_title else 0.76,
                page_number=1,
                source_snippet=version_snippet,
                line_number=self._find_line_number(first_page_lines, version_snippet),
            )

        if profile == "harbor-estimate" and not any(
            field.field_path == "quote.currency_code" for field in fields
        ):
            self._append_field(
                fields,
                occurrence_counts,
                field_path="quote.currency_code",
                raw_value="GBP",
                normalized_text="GBP",
                confidence=0.72,
                page_number=1,
                source_snippet="Defaulted to GBP for Harbor estimate profile.",
            )

    def _search_lines(
        self,
        lines: list[str],
        pattern: re.Pattern[str],
    ) -> dict[str, object] | None:
        for line_number, line in enumerate(lines, start=1):
            match = pattern.search(line)
            if match:
                return {
                    "value": self._clean_line(match.group("value")),
                    "snippet": line,
                    "line_number": line_number,
                }
        return None

    def _extract_project_title(self, first_page_lines: list[str]) -> str | None:
        anchor_index = next(
            (
                index
                for index, line in enumerate(first_page_lines)
                if "QUOTE ID:" in line.upper()
            ),
            None,
        )
        if anchor_index is None:
            return None

        collected: list[str] = []
        for line in first_page_lines[anchor_index + 1 :]:
            if any(line.startswith(marker) for marker in self._header_break_markers):
                break
            if any(line.startswith(prefix) for prefix in self._skip_prefixes):
                continue
            cleaned = line.rstrip(":").strip()
            if cleaned:
                collected.append(cleaned)
        return collected[0] if collected else None

    def _derive_project_title(self, quote_title: str) -> str | None:
        for separator in (" - ", " – ", " — "):
            if separator in quote_title:
                return quote_title.split(separator, maxsplit=1)[0].strip() or None
        return None

    def _extract_version_label(
        self,
        quote_title: str | None,
        object_key: str,
    ) -> tuple[str | None, str]:
        for candidate in filter(None, (quote_title, Path(object_key).stem)):
            match = self._version_re.search(candidate)
            if match:
                return match.group("label"), candidate
        return None, ""

    def _extract_assumptions_and_notes(
        self, first_page_lines: list[str]
    ) -> tuple[list[str], list[str]]:
        start_index = next(
            (
                index
                for index, line in enumerate(first_page_lines)
                if line in {"COMMENTS | BID ASSUMPTIONS", "ESTIMATE COMMENTS / ASSUMPTIONS:"}
            ),
            None,
        )
        if start_index is None:
            return [], []

        assumptions: list[str] = []
        notes: list[str] = []
        target = assumptions
        for line in first_page_lines[start_index + 1 :]:
            if line.startswith("SECTION SUMMARY"):
                break
            if any(line.startswith(prefix) for prefix in self._skip_prefixes):
                continue
            if line.endswith(":") and not line.startswith(("•", "-")):
                target = notes
                continue
            cleaned = line.lstrip("•- ").strip()
            if cleaned:
                target.append(cleaned)
        return assumptions, notes

    def _extract_line_items(self, page_texts: list[str]) -> list[ParsedLineItemCandidate]:
        items: list[ParsedLineItemCandidate] = []
        breakdown_started = False
        current_section = "General"
        for page_number, page_text in enumerate(page_texts, start=1):
            if not breakdown_started and "QUOTE BREAKDOWN" not in page_text:
                continue
            if breakdown_started and "CONFIRMATION TERMS" in page_text:
                break

            lines = self._page_lines(page_text)
            pending_section_lines: list[str] = []
            in_breakdown = breakdown_started
            in_table = False
            current_item: ParsedLineItemCandidate | None = None

            for line_number, line in enumerate(lines, start=1):
                if line == "QUOTE BREAKDOWN":
                    breakdown_started = True
                    in_breakdown = True
                    in_table = False
                    pending_section_lines = []
                    current_item = None
                    continue
                if not in_breakdown or any(
                    line.startswith(prefix) for prefix in self._skip_prefixes
                ):
                    continue
                if self._grand_total_re.search(line):
                    in_table = False
                    current_item = None
                    continue
                if self._header_row_re.match(line):
                    current_section = self._resolve_section_name(
                        pending_section_lines,
                        current_section,
                    )
                    pending_section_lines = []
                    in_table = True
                    current_item = None
                    continue
                if not in_table:
                    if not self._is_section_total_line(line):
                        pending_section_lines.append(line)
                    continue

                parsed_row = self._parse_line_item_row(
                    line,
                    section_name=current_section,
                    page_number=page_number,
                    line_number=line_number,
                )
                if parsed_row is not None:
                    items.append(parsed_row)
                    current_item = parsed_row
                    continue

                if self._is_section_total_line(line):
                    in_table = False
                    current_item = None
                    continue

                if current_item is None:
                    continue

                current_item.source_lines.append(line)
                if not line.startswith(("•", "-")):
                    current_item.description = f"{current_item.description} {line}".strip()
                    current_item.confidence = max(0.7, current_item.confidence - 0.04)

        return items

    def _resolve_section_name(self, pending_lines: list[str], fallback: str) -> str:
        for line in pending_lines:
            if line.startswith(("•", "-")):
                continue
            if self._is_section_total_line(line):
                continue
            return line.rstrip(":").strip() or fallback
        return fallback

    def _parse_line_item_row(
        self,
        line: str,
        *,
        section_name: str,
        page_number: int,
        line_number: int,
    ) -> ParsedLineItemCandidate | None:
        suffix_match = self._rate_suffix_re.search(line)
        if suffix_match is None:
            return None

        rate = self._parse_number(suffix_match.group("rate"))
        amount = self._parse_number(suffix_match.group("amount"))
        unit = suffix_match.group("unit").lower()
        prefix = line[: suffix_match.start()].strip()
        if not prefix:
            return None

        prefix_tokens = prefix.split()
        trailing_numeric_tokens: list[str] = []
        remaining_tokens = prefix_tokens[:]
        while remaining_tokens and len(trailing_numeric_tokens) < 2:
            token = remaining_tokens[-1]
            if not self._number_token_re.fullmatch(token):
                break
            trailing_numeric_tokens.insert(0, remaining_tokens.pop())
        if not trailing_numeric_tokens:
            return None

        selected = self._select_row_candidate(
            trailing_numeric_tokens,
            remaining_tokens,
            unit=unit,
            rate=rate,
            amount=amount,
        )
        if selected is None:
            return None

        return ParsedLineItemCandidate(
            section_name=section_name,
            description=selected["description"],
            quantity=selected["quantity"],
            unit=unit,
            rate=rate,
            amount=amount,
            confidence=selected["confidence"],
            page_number=page_number,
            source_bounds={
                "page": page_number,
                "line": line_number,
                "raw_qty": selected["raw_qty"],
                "raw_time": selected["raw_time"],
            },
            source_lines=[line],
        )

    def _select_row_candidate(
        self,
        trailing_numeric_tokens: list[str],
        remaining_tokens: list[str],
        *,
        unit: str,
        rate: float,
        amount: float,
    ) -> dict[str, object] | None:
        single_candidate = self._build_single_quantity_candidate(
            trailing_numeric_tokens,
            remaining_tokens,
            rate=rate,
            amount=amount,
        )
        double_candidate = self._build_quantity_time_candidate(
            trailing_numeric_tokens,
            remaining_tokens,
            rate=rate,
            amount=amount,
        )
        unit_key = unit.lower()

        if double_candidate is not None and double_candidate["difference"] <= 0.01:
            if single_candidate is not None and single_candidate["difference"] <= 0.01:
                return double_candidate
            if unit_key not in {"each", "flat"}:
                return double_candidate
            if single_candidate is None or single_candidate["difference"] > 0.01:
                return double_candidate
        if single_candidate is not None and single_candidate["difference"] <= 0.01:
            return single_candidate
        if double_candidate is not None and double_candidate["difference"] <= 0.01:
            return double_candidate
        if single_candidate is None:
            return double_candidate
        if double_candidate is None:
            return single_candidate
        if (
            unit_key in {"each", "flat"}
            and single_candidate["difference"] <= double_candidate["difference"]
        ):
            return single_candidate
        if double_candidate["difference"] < single_candidate["difference"]:
            return double_candidate
        return single_candidate

    def _build_single_quantity_candidate(
        self,
        trailing_numeric_tokens: list[str],
        remaining_tokens: list[str],
        *,
        rate: float,
        amount: float,
    ) -> dict[str, object] | None:
        raw_qty = self._parse_number(trailing_numeric_tokens[-1])
        description = " ".join([*remaining_tokens, *trailing_numeric_tokens[:-1]]).strip()
        if not description:
            return None
        difference = abs((raw_qty * rate) - amount)
        return {
            "description": description,
            "quantity": raw_qty,
            "raw_qty": raw_qty,
            "raw_time": None,
            "difference": difference,
            "confidence": self._line_item_confidence(
                difference,
                amount=amount,
                rate=rate,
                had_time=False,
            ),
        }

    def _build_quantity_time_candidate(
        self,
        trailing_numeric_tokens: list[str],
        remaining_tokens: list[str],
        *,
        rate: float,
        amount: float,
    ) -> dict[str, object] | None:
        if len(trailing_numeric_tokens) < 2:
            return None
        raw_qty = self._parse_number(trailing_numeric_tokens[-2])
        raw_time = self._parse_number(trailing_numeric_tokens[-1])
        description = " ".join(remaining_tokens).strip()
        if not description:
            return None
        difference = abs((raw_qty * raw_time * rate) - amount)
        return {
            "description": description,
            "quantity": raw_qty * raw_time,
            "raw_qty": raw_qty,
            "raw_time": raw_time,
            "difference": difference,
            "confidence": self._line_item_confidence(
                difference,
                amount=amount,
                rate=rate,
                had_time=True,
            ),
        }

    def _line_item_confidence(
        self,
        difference: float,
        *,
        amount: float,
        rate: float,
        had_time: bool,
    ) -> float:
        confidence = 0.93 if had_time else 0.9
        if difference > 0.01:
            confidence -= 0.12
        if amount == 0.0 and rate > 0.0:
            confidence -= 0.08
        return max(0.58, min(0.98, confidence))

    def _extract_explicit_total(self, page_texts: list[str]) -> dict[str, object] | None:
        for page_number in range(len(page_texts), 0, -1):
            lines = self._page_lines(page_texts[page_number - 1])
            for line_number, line in reversed(list(enumerate(lines, start=1))):
                match = self._grand_total_re.search(line)
                if match:
                    return {
                        "amount": self._parse_number(match.group("amount")),
                        "currency": (
                            match.group("currency").upper()
                            if match.group("currency")
                            else None
                        ),
                        "page_number": page_number,
                        "line_number": line_number,
                        "snippet": line,
                    }
        return None

    def _detect_currency(self, page_texts: list[str]) -> str | None:
        for page_number in range(len(page_texts), 0, -1):
            lines = self._page_lines(page_texts[page_number - 1])
            for line in reversed(lines):
                match = self._currency_re.search(line)
                if match:
                    return match.group("currency").upper()
        return None

    def _append_field(
        self,
        fields: list[CandidateField],
        occurrence_counts: dict[str, int],
        *,
        field_path: str,
        raw_value: str | None,
        confidence: float,
        page_number: int,
        source_snippet: str,
        normalized_text: str | None = None,
        normalized_amount: float | None = None,
        normalized_date: date | None = None,
        line_number: int | None = None,
    ) -> None:
        occurrence_index = occurrence_counts.get(field_path, 0)
        occurrence_counts[field_path] = occurrence_index + 1
        source_bounds: dict[str, object] = {"page": page_number}
        if line_number is not None:
            source_bounds["line"] = line_number
        fields.append(
            CandidateField(
                field_path=field_path,
                occurrence_index=occurrence_index,
                raw_value=raw_value,
                normalized_text=normalized_text,
                normalized_amount=normalized_amount,
                normalized_date=normalized_date,
                confidence=max(0.05, min(0.99, confidence)),
                page_number=page_number,
                source_snippet=source_snippet,
                source_bounds=source_bounds,
            )
        )

    def _find_line_number(self, lines: list[str], snippet: str) -> int | None:
        if not snippet:
            return None
        normalized_snippet = self._clean_line(snippet)
        for line_number, line in enumerate(lines, start=1):
            if normalized_snippet and normalized_snippet in line:
                return line_number
        return None

    def _parse_document_date(self, raw_value: str) -> date | None:
        normalized = self._ordinal_suffix_re.sub(r"\g<day>", raw_value.replace(",", ""))
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(normalized, fmt).date()
            except ValueError:
                continue
        return None

    def _parse_number(self, value: str) -> float:
        return float(value.replace(",", "").strip())

    def _format_amount(self, value: float) -> str:
        return f"{value:,.2f}"

    def _is_section_total_line(self, value: str) -> bool:
        return bool(re.fullmatch(r"-?\d[\d,]*\.\d{2}", value))


quote_pdf_parser = QuotePdfParser()
