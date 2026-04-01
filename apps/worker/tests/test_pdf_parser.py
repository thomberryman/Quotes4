from __future__ import annotations

from app.integrations import pdf_parser as pdf_parser_module


class FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self, *, x_tolerance: int = 2, y_tolerance: int = 2) -> str:
        return self._text


class FakePdf:
    def __init__(self, pages: list[str]) -> None:
        self.pages = [FakePage(page) for page in pages]

    def __enter__(self) -> FakePdf:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_harbor_parser_extracts_header_fields_and_line_items(monkeypatch) -> None:
    first_page = """This estimate is not authorised
DATE: 20th November 2025
TITLE: Lightbulb - Mix 1 Dry Hire Rates V2
CLIENT: A24 Films
CONTACT: Helen Phelps
EC1M 5RR JOB NO: 70215
+44 2038 55 6570 QUOTE ID: 5414
LIGHTBULB, 8 x 35' Episodes, delivering to ATV+ & A24
Estimate prepared for: Claire Davis-Bell
ESTIMATE COMMENTS / ASSUMPTIONS:
- Dry hire of HARBOR's Mix 1 Rates included.
ADR RATECARD:
ADR Recording (ADR 1) - Discounted rate
SECTION SUMMARY
Section Quoted
Dry Hire Rates Only (Mix 1) 57,800.00
"""
    second_page = """This estimate is not authorised
QUOTE BREAKDOWN
Dry Hire Rates Only (Mix 1)
ITEM QTY TIME RATE UNITS TOTAL
Mix Set-Up for Series 1 1 600.00 / Each 600.00
- ingest mix data from Phaze's drive prior to mixes
Dry Hire Mix 1 - 4 days Mix for episodes 1 & 2 2 4 2,200.00 / Day 17,600.00
57,800.00
GRAND TOTAL: 57,800.00 GBP
"""

    monkeypatch.setattr(
        pdf_parser_module.object_storage_service,
        "read_object_bytes",
        lambda object_key: b"%PDF-1.4 fake document bytes",
    )
    monkeypatch.setattr(
        pdf_parser_module.pdfplumber,
        "open",
        lambda source: FakePdf([first_page, second_page]),
    )

    result = pdf_parser_module.quote_pdf_parser.parse(
        object_key="/tmp/Lightbulb-Mix-1-Dry-Hire-Rates-V2_03122025.pdf"
    )

    assert result.parser_name == "harbor-estimate-parser"
    assert result.page_count == 2
    assert result.text_page_count == 2

    fields = {
        (field.field_path, field.occurrence_index): field for field in result.field_candidates
    }
    assert fields[("quote.title", 0)].normalized_text == "Lightbulb - Mix 1 Dry Hire Rates V2"
    assert fields[("quote.quote_number", 0)].normalized_text == "5414"
    assert fields[("source.job_number", 0)].normalized_text == "70215"
    assert (
        fields[("project.title", 0)].normalized_text
        == "LIGHTBULB, 8 x 35' Episodes, delivering to ATV+ & A24"
    )
    assert fields[("quote.source_version_label", 0)].normalized_text == "V2"
    assert fields[("quote.currency_code", 0)].normalized_text == "GBP"
    assert fields[("totals.total", 0)].normalized_amount == 57800.0
    assert (
        fields[("assumptions[0]", 0)].normalized_text
        == "Dry hire of HARBOR's Mix 1 Rates included."
    )
    assert fields[("notes[0]", 0)].normalized_text == "ADR Recording (ADR 1) - Discounted rate"

    assert len(result.candidate_line_items) == 2
    first_item, second_item = result.candidate_line_items
    assert first_item.description == "Mix Set-Up for Series"
    assert first_item.quantity == 1.0
    assert first_item.unit == "each"
    assert "ingest mix data" in first_item.source_snippet
    assert second_item.description == "Dry Hire Mix 1 - 4 days Mix for episodes 1 & 2"
    assert second_item.quantity == 8.0
    assert second_item.unit == "day"
    assert second_item.amount == 17600.0


def test_harbor_parser_uses_filename_suffix_for_version_label(monkeypatch) -> None:
    first_page = """This estimate is not authorised
DATE: 13th February 2026
TITLE: People of the Book - Offline Rates
CLIENT: Good Films Collective
CONTACT: James Corless
EC1M 5RR JOB NO: 70712
+44 2038 55 6570 QUOTE ID: 6074
People of the Book
COMMENTS | BID ASSUMPTIONS
• Offline estimate
SECTION SUMMARY
Section Quoted
Offline Rates 67,730.00
"""
    second_page = """This estimate is not authorised
QUOTE BREAKDOWN
Offline Rates
ITEM QTY TIME RATE UNITS TOTAL
Offline Edit 1 10 200.00 / Hour 2,000.00
2,000.00
GRAND TOTAL: 2,000.00 GBP
"""

    monkeypatch.setattr(
        pdf_parser_module.object_storage_service,
        "read_object_bytes",
        lambda object_key: b"%PDF-1.4 fake document bytes",
    )
    monkeypatch.setattr(
        pdf_parser_module.pdfplumber,
        "open",
        lambda source: FakePdf([first_page, second_page]),
    )

    result = pdf_parser_module.quote_pdf_parser.parse(
        object_key="/tmp/Good-Films-Collective-70712-People-of-the-Book---Offline-Rates-6074v3.pdf"
    )

    fields = {
        (field.field_path, field.occurrence_index): field for field in result.field_candidates
    }
    assert fields[("quote.source_version_label", 0)].normalized_text == "v3"


def test_harbor_parser_continues_breakdown_across_pages(monkeypatch) -> None:
    first_page = """This estimate is not authorised
DATE: 13th February 2026
TITLE: People of the Book - 4K DI & Delivery
CLIENT: Good Films Collective
CONTACT: James Corless
EC1M 5RR JOB NO: 70711
+44 2038 55 6570 QUOTE ID: 6073
People of the Book
COMMENTS | BID ASSUMPTIONS
• Delivery estimate
SECTION SUMMARY
Section Quoted
Conform 2,500.00
Grade 30,000.00
32,500.00
"""
    second_page = """This estimate is not authorised
QUOTE BREAKDOWN
Conform
ITEM QTY TIME RATE UNITS TOTAL
Media Management 1 1 2,500.00 / flat 2,500.00
2,500.00
"""
    third_page = """This estimate is not authorised
Grade
ITEM QTY TIME RATE UNITS TOTAL
4K P3 Theatrical Grade 1 80 375.00 / Hour 30,000.00
30,000.00
GRAND TOTAL: 32,500.00 GBP
"""

    monkeypatch.setattr(
        pdf_parser_module.object_storage_service,
        "read_object_bytes",
        lambda object_key: b"%PDF-1.4 fake document bytes",
    )
    monkeypatch.setattr(
        pdf_parser_module.pdfplumber,
        "open",
        lambda source: FakePdf([first_page, second_page, third_page]),
    )

    result = pdf_parser_module.quote_pdf_parser.parse(
        object_key="/tmp/Good-Films-Collective-70711-People-of-the-Book---4K-DI-Delivery-6073-v3.pdf"
    )

    assert [warning.code for warning in result.warnings] == []
    assert len(result.candidate_line_items) == 2
    assert result.candidate_line_items[0].section_name == "Conform"
    assert result.candidate_line_items[1].section_name == "Grade"
    assert result.candidate_line_items[1].description == "4K P3 Theatrical Grade"
    assert result.candidate_line_items[1].amount == 30000.0


def test_harbor_parser_preserves_negative_discount_rows(monkeypatch) -> None:
    first_page = """This estimate is not authorised
DATE: 16th December 2025
TITLE: Lightbulb, Picture Finishing, 8 x 45' V5
CLIENT: A24 Films
CONTACT: Helen Phelps
EC1M 5RR JOB NO: 70214
+44 2038 55 6570 QUOTE ID: 5598
LIGHTBULB, 8 x 45' Episodes - Delivering to ATV+ & A24
ESTIMATE COMMENTS / ASSUMPTIONS:
- Finishing estimate
SECTION SUMMARY
Section Quoted
Series Discount Structure & Spend Criteria -50,835.60
256,210.40
"""
    second_page = """This estimate is not authorised
QUOTE BREAKDOWN
Series Discount Structure & Spend Criteria
ITEM QTY TIME RATE UNITS TOTAL
Series Discount 1 1 -50,835.60 / Each -50,835.60
-50,835.60
GRAND TOTAL: 256,210.40 GBP
"""

    monkeypatch.setattr(
        pdf_parser_module.object_storage_service,
        "read_object_bytes",
        lambda object_key: b"%PDF-1.4 fake document bytes",
    )
    monkeypatch.setattr(
        pdf_parser_module.pdfplumber,
        "open",
        lambda source: FakePdf([first_page, second_page]),
    )

    result = pdf_parser_module.quote_pdf_parser.parse(
        object_key="/tmp/Lightbulb-Picture-Finishing-8x45-V5-5598_16122025.pdf"
    )

    assert len(result.candidate_line_items) == 1
    assert result.candidate_line_items[0].description == "Series Discount"
    assert result.candidate_line_items[0].rate == -50835.6
    assert result.candidate_line_items[0].amount == -50835.6
