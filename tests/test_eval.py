"""Tests for evals/scoring.py. No API calls, no real cache, no real
answer key — every test builds a tiny fake answer-key entry and
ExtractedInvoice directly, so these tests check the scoring logic
itself, not any particular extraction result.
"""

from __future__ import annotations

from src.extract.schema import ExtractedInvoice
from src.validate.checks import Issue
from src.validate.duplicates import DuplicateDetector
from src.validate.validate import validate_invoice
from datetime import date

from evals import scoring
from evals.run_eval import genuinely_skipped

CONFIDENCE_FIELD_NAMES = [
    "supplier",
    "invoice_number",
    "issue_date",
    "due_date",
    "currency",
    "net",
    "vat",
    "total",
    "document_type",
    "language",
]

BASE_ANSWER = {
    "file": "invoices/fake_2026-01-01.pdf",
    "supplier": "Fake Supplier, Inc.",
    "supplier_as_printed": "Fake Supplier Inc",
    "invoice_number": "FAKE-001",
    "issue_date": "2026-01-01",
    "due_date": "2026-01-31",
    "currency": "EUR",
    "net": 100.0,
    "vat": 21.0,
    "total": 121.0,
    "document_type": "invoice",
    "language": "en",
    "trap": None,
}


def make_extracted(**overrides) -> ExtractedInvoice:
    data = {
        "supplier": BASE_ANSWER["supplier_as_printed"],
        "invoice_number": BASE_ANSWER["invoice_number"],
        "issue_date": BASE_ANSWER["issue_date"],
        "due_date": BASE_ANSWER["due_date"],
        "currency": BASE_ANSWER["currency"],
        "net": BASE_ANSWER["net"],
        "vat": BASE_ANSWER["vat"],
        "total": BASE_ANSWER["total"],
        "document_type": BASE_ANSWER["document_type"],
        "language": BASE_ANSWER["language"],
        "confidence": {field: 0.95 for field in CONFIDENCE_FIELD_NAMES},
    }
    data.update(overrides)
    return ExtractedInvoice.model_validate(data)


# ---------------------------------------------------------------------------
# Field-level scoring
# ---------------------------------------------------------------------------


def test_exact_match_is_correct():
    extracted = make_extracted()

    scores = scoring.score_fields(BASE_ANSWER, extracted, doc_kind="pdf")

    assert all(s.correct for s in scores)
    assert len(scores) == len(scoring.FIELDS)


def test_amount_tolerance_edge_0_01_passes_0_02_fails():
    assert scoring.fields_match(50.0, 50.01, "total") is True
    assert scoring.fields_match(50.0, 50.02, "total") is False


def test_null_vs_null_counts_as_correct():
    assert scoring.fields_match(None, None, "due_date") is True


def test_null_vs_value_counts_as_wrong():
    assert scoring.fields_match(None, "2026-01-31", "due_date") is False
    assert scoring.fields_match("2026-01-31", None, "due_date") is False


# ---------------------------------------------------------------------------
# Trap scoring
# ---------------------------------------------------------------------------


def test_trap_caught_when_expected_issue_is_present():
    issues = [Issue("error", "MATH_MISMATCH", "net + vat != total")]

    result = scoring.evaluate_trap("invoices/x.pdf", "maths_error", issues)

    assert result.caught is True
    assert result.is_false_flag is False


def test_trap_missed_when_expected_issue_is_absent():
    issues: list[Issue] = []

    result = scoring.evaluate_trap("invoices/x.pdf", "maths_error", issues)

    assert result.caught is False
    assert result in scoring.trap_misses([result])


def test_false_flag_counted_for_clean_document_with_unexpected_error():
    issues = [Issue("error", "MATH_MISMATCH", "unexpected")]

    result = scoring.evaluate_trap("invoices/clean.pdf", None, issues)
    flagged, tally = scoring.false_flags([result])

    assert result.is_false_flag is True
    assert flagged == [result]
    assert tally == {"MATH_MISMATCH": 1}


def test_low_confidence_warning_alone_is_a_soft_flag_not_a_false_flag():
    issues = [Issue("warning", "LOW_CONFIDENCE", "shaky read")]

    result = scoring.evaluate_trap("invoices/clean.pdf", "name_variant", issues)

    assert result.caught is True
    assert result.is_false_flag is False
    assert result.has_soft_flag is True
    assert scoring.soft_flag_count([result]) == 1


# ---------------------------------------------------------------------------
# Photo scored standalone with a fresh detector
# ---------------------------------------------------------------------------


def test_photo_validated_with_fresh_detector_is_not_flagged_as_duplicate_of_its_pdf(tmp_path):
    # Same invoice, same total — exactly what a PDF and its phone-photo
    # counterpart would extract to. Register the PDF in one detector,
    # then validate the "photo" with a brand-new detector, as run_eval's
    # Pass B does. It must come back clean, not DUPLICATE.
    pdf_extracted = make_extracted()
    photo_extracted = make_extracted()

    pdf_detector = DuplicateDetector(cache_path=tmp_path / "unused.json")
    pdf_result = validate_invoice(pdf_extracted, pdf_detector, today=date(2026, 1, 1))
    assert pdf_result.status == "pass"

    fresh_detector = DuplicateDetector(cache_path=tmp_path / "also_unused.json")
    photo_result = validate_invoice(photo_extracted, fresh_detector, today=date(2026, 1, 1))

    assert photo_result.status == "pass"
    assert not any(i.code == "DUPLICATE" for i in photo_result.issues)

    # Contrast: reusing the SAME detector for both would incorrectly
    # flag the photo as a duplicate — confirming the fresh-detector rule
    # is actually doing something, not vacuously true.
    shared_detector = DuplicateDetector(cache_path=tmp_path / "shared.json")
    validate_invoice(make_extracted(), shared_detector, today=date(2026, 1, 1))
    reused_result = validate_invoice(make_extracted(), shared_detector, today=date(2026, 1, 1))
    assert any(i.code == "DUPLICATE" for i in reused_result.issues)


# ---------------------------------------------------------------------------
# genuinely_skipped (evals/run_eval.py) — the "Not cached" report bug.
#
# Previously this list was the PRE-run cache snapshot, so after a live
# run it still listed files that had just been successfully extracted.
# It must instead reflect what actually has no result in the report.
# ---------------------------------------------------------------------------


def test_genuinely_skipped_excludes_files_extracted_this_run():
    all_entries = [{"file": "invoices/a.pdf"}, {"file": "invoices/b.pdf"}]
    # Both were uncached before the run, but both got extracted live —
    # simulated here by both being present in extracted_by_file.
    extracted_by_file = {"invoices/a.pdf": object(), "invoices/b.pdf": object()}

    skipped = genuinely_skipped(all_entries, extracted_by_file, extraction_failures=[])

    assert skipped == []


def test_genuinely_skipped_excludes_recorded_extraction_failures():
    all_entries = [{"file": "invoices/a.pdf"}]
    extraction_failures = [("invoices/a.pdf", "schema validation failed twice")]

    skipped = genuinely_skipped(all_entries, extracted_by_file={}, extraction_failures=extraction_failures)

    assert skipped == []


def test_genuinely_skipped_lists_files_with_neither_result_nor_failure():
    all_entries = [{"file": "invoices/a.pdf"}, {"file": "invoices/b.pdf"}]
    extracted_by_file = {"invoices/a.pdf": object()}

    skipped = genuinely_skipped(all_entries, extracted_by_file, extraction_failures=[])

    assert skipped == ["invoices/b.pdf"]
