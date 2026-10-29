"""Tests for src/validate/. No API calls anywhere — every test builds an
ExtractedInvoice directly from data/synthetic/answer_key.json (using a
confidence of 0.99 on every field unless a test overrides it), so these
tests prove the validator catches the traps the synthetic generator
actually produced, not made-up toy examples.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.extract.schema import ExtractedInvoice
from src.validate import checks
from src.validate.config import CONFIDENCE_THRESHOLD
from src.validate.duplicates import DuplicateDetector
from src.validate.validate import validate_invoice

ANSWER_KEY_PATH = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "answer_key.json"
ANSWER_KEY = json.loads(ANSWER_KEY_PATH.read_text())
ANSWER_KEY_BY_FILE = {entry["file"]: entry for entry in ANSWER_KEY}

# Every field FieldConfidence requires. Used to build a "confident
# extraction" fixture by default; tests override individual fields.
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

# "Today" for date checks — matches the fixed date these tests were written
# against, so FUTURE_ISSUE_DATE behaves predictably regardless of when
# pytest actually runs.
TODAY = date(2026, 10, 29)


def by_file(file_name: str) -> dict:
    return ANSWER_KEY_BY_FILE[file_name]


def make_extracted(entry: dict, **overrides) -> ExtractedInvoice:
    data = {
        "supplier": entry["supplier_as_printed"],
        "invoice_number": entry["invoice_number"],
        "issue_date": entry["issue_date"],
        "due_date": entry["due_date"],
        "currency": entry["currency"],
        "net": entry["net"],
        "vat": entry["vat"],
        "total": entry["total"],
        "document_type": entry["document_type"],
        "language": entry["language"],
        "confidence": {field: 0.99 for field in CONFIDENCE_FIELD_NAMES},
    }
    data.update(overrides)
    return ExtractedInvoice.model_validate(data)


# ---------------------------------------------------------------------------
# One test per trap type in the answer key
# ---------------------------------------------------------------------------


def test_maths_mismatch_trap_is_detected():
    entry = by_file("invoices/electricity_2026-07-10.pdf")
    assert entry["trap"] == "maths_error"
    extracted = make_extracted(entry)

    issues = checks.check_maths(extracted)

    assert len(issues) == 1
    assert issues[0].code == "MATH_MISMATCH"
    assert issues[0].severity == "error"


def test_no_due_date_trap_is_a_warning_not_an_error():
    entry = by_file("invoices/freelancer_2026-07-20.pdf")
    assert entry["trap"] == "no_due_date"
    assert entry["due_date"] is None
    extracted = make_extracted(entry)

    issues = checks.check_required_fields(extracted)

    due_date_issues = [i for i in issues if i.code == "MISSING_DUE_DATE"]
    assert len(due_date_issues) == 1
    assert due_date_issues[0].severity == "warning"
    # Missing due_date alone must not also raise a MISSING_FIELD error —
    # due_date isn't in REQUIRED_FIELDS.
    assert not any(i.code == "MISSING_FIELD" for i in issues)


def test_exact_duplicate_trap_is_detected(tmp_path):
    first_entry = by_file("invoices/electricity_2026-08-10.pdf")
    second_entry = by_file("invoices/electricity_2026-08-10_dup.pdf")
    assert first_entry["trap"] == "duplicate_exact"
    assert second_entry["trap"] == "duplicate_exact"
    assert first_entry["invoice_number"] == second_entry["invoice_number"]
    assert first_entry["total"] == second_entry["total"]

    detector = DuplicateDetector(cache_path=tmp_path / "seen.json")
    first = make_extracted(first_entry)
    second = make_extracted(second_entry)

    assert detector.check(first) == []
    detector.register(first)
    issues = detector.check(second)

    assert len(issues) == 1
    assert issues[0].code == "DUPLICATE"
    assert issues[0].severity == "error"


def test_duplicate_near_trap_is_an_amount_conflict(tmp_path):
    original_entry = by_file("invoices/coworking_2026-09-01.pdf")
    near_entry = by_file("invoices/coworking_2026-09-01_near.pdf")
    assert near_entry["trap"] == "duplicate_near"
    assert original_entry["invoice_number"] == near_entry["invoice_number"]
    assert original_entry["total"] != near_entry["total"]

    detector = DuplicateDetector(cache_path=tmp_path / "seen.json")
    detector.register(make_extracted(original_entry))
    issues = detector.check(make_extracted(near_entry))

    assert len(issues) == 1
    assert issues[0].code == "AMOUNT_CONFLICT"
    assert issues[0].severity == "error"
    assert str(original_entry["total"]) in issues[0].message
    assert str(near_entry["total"]) in issues[0].message


def test_duplicate_detected_despite_supplier_name_variant(tmp_path):
    # Same invoice, same total, but printed with two different variants
    # of the supplier's name — drawn from the real variants the
    # synthetic generator used for Notion's invoices.
    entry = by_file("invoices/notion_2026-08-03.pdf")
    detector = DuplicateDetector(cache_path=tmp_path / "seen.json")
    first = make_extracted(entry, supplier="Notion Labs Inc")
    second = make_extracted(entry, supplier="NOTION LABS")

    detector.register(first)
    issues = detector.check(second)

    assert len(issues) == 1
    assert issues[0].code == "DUPLICATE"


def test_reverse_charge_zero_vat_trap_passes_maths():
    entry = by_file("invoices/nordic_2026-08-01.pdf")
    assert entry["trap"] == "reverse_charge"
    assert entry["vat"] == 0.0
    extracted = make_extracted(entry)

    assert checks.check_maths(extracted) == []


def test_credit_note_trap_passes_maths_and_document_type_checks():
    entry = by_file("invoices/adobe_2026-10-15.pdf")
    assert entry["trap"] == "credit_note"
    assert entry["total"] < 0
    extracted = make_extracted(entry)

    assert checks.check_maths(extracted) == []
    assert checks.check_document_type(extracted) == []


# ---------------------------------------------------------------------------
# Edge cases the task explicitly asks for
# ---------------------------------------------------------------------------


def test_tolerance_edge_exactly_0_01_passes():
    entry = by_file("invoices/adobe_2026-10-05.pdf")  # net 167.97 + vat 35.27 = 203.24
    extracted = make_extracted(entry, total=203.25)  # diff is exactly 0.01

    assert checks.check_maths(extracted) == []


def test_tolerance_edge_0_02_fails():
    entry = by_file("invoices/adobe_2026-10-05.pdf")
    extracted = make_extracted(entry, total=203.26)  # diff is 0.02

    issues = checks.check_maths(extracted)

    assert len(issues) == 1
    assert issues[0].code == "MATH_MISMATCH"


def test_null_amount_field_skips_maths_check():
    entry = by_file("invoices/adobe_2026-10-05.pdf")
    extracted = make_extracted(entry, net=None)

    assert checks.check_maths(extracted) == []


def test_missing_required_fields_are_errors():
    entry = by_file("invoices/adobe_2026-10-05.pdf")
    extracted = make_extracted(entry, supplier=None, currency=None)

    issues = checks.check_required_fields(extracted)
    missing_field_issues = [i for i in issues if i.code == "MISSING_FIELD"]

    assert len(missing_field_issues) == 2
    assert all(i.severity == "error" for i in missing_field_issues)


def test_low_confidence_required_field_is_a_warning():
    entry = by_file("invoices/adobe_2026-10-05.pdf")
    confidence = {field: 0.99 for field in CONFIDENCE_FIELD_NAMES}
    confidence["total"] = 0.5
    extracted = make_extracted(entry, confidence=confidence)

    issues = checks.check_low_confidence(extracted)

    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert "total" in issues[0].message
    assert "0.50" in issues[0].message


def test_low_confidence_non_required_field_is_not_flagged():
    # due_date isn't in REQUIRED_FIELDS, so a shaky read on it shouldn't
    # raise a LOW_CONFIDENCE warning.
    entry = by_file("invoices/adobe_2026-10-05.pdf")
    confidence = {field: 0.99 for field in CONFIDENCE_FIELD_NAMES}
    confidence["due_date"] = 0.1
    extracted = make_extracted(entry, confidence=confidence)

    assert checks.check_low_confidence(extracted) == []


def test_confidence_exactly_at_threshold_is_not_low():
    entry = by_file("invoices/adobe_2026-10-05.pdf")
    confidence = {field: 0.99 for field in CONFIDENCE_FIELD_NAMES}
    confidence["total"] = CONFIDENCE_THRESHOLD
    extracted = make_extracted(entry, confidence=confidence)

    assert checks.check_low_confidence(extracted) == []


def test_due_before_issue_date_is_an_error():
    entry = by_file("invoices/adobe_2026-10-05.pdf")  # issue_date 2026-10-05
    extracted = make_extracted(entry, due_date="2026-10-01")

    issues = checks.check_dates(extracted, TODAY)

    assert any(i.code == "DUE_BEFORE_ISSUE" and i.severity == "error" for i in issues)


def test_future_issue_date_is_only_a_warning():
    entry = by_file("invoices/adobe_2026-10-05.pdf")
    extracted = make_extracted(entry, issue_date="2026-11-15", due_date="2026-12-15")

    issues = checks.check_dates(extracted, TODAY)

    future_issues = [i for i in issues if i.code == "FUTURE_ISSUE_DATE"]
    assert len(future_issues) == 1
    assert future_issues[0].severity == "warning"
    assert not any(i.code == "DUE_BEFORE_ISSUE" for i in issues)


# ---------------------------------------------------------------------------
# validate_invoice(): the combined result, and the "don't register a bad
# read" design choice
# ---------------------------------------------------------------------------


def test_validate_invoice_clean_invoice_passes(tmp_path):
    entry = by_file("invoices/adobe_2026-10-05.pdf")
    assert entry["trap"] is None
    detector = DuplicateDetector(cache_path=tmp_path / "seen.json")

    result = validate_invoice(make_extracted(entry), detector, today=TODAY)

    assert result.status == "pass"
    assert result.issues == []


def test_validate_invoice_maths_error_needs_review(tmp_path):
    entry = by_file("invoices/electricity_2026-07-10.pdf")
    detector = DuplicateDetector(cache_path=tmp_path / "seen.json")

    result = validate_invoice(make_extracted(entry), detector, today=TODAY)

    assert result.status == "review"
    assert any(i.code == "MATH_MISMATCH" for i in result.issues)


def test_bad_read_is_not_registered_so_a_correction_is_not_blocked(tmp_path):
    # First pass: the extraction is bad (maths doesn't add up). That
    # must NOT get remembered as "already seen".
    entry = by_file("invoices/electricity_2026-07-10.pdf")
    detector = DuplicateDetector(cache_path=tmp_path / "seen.json")
    bad_reading = make_extracted(entry)
    first_result = validate_invoice(bad_reading, detector, today=TODAY)
    assert first_result.status == "review"

    # Second pass: a corrected re-extraction of the SAME invoice, with
    # consistent maths. It should pass cleanly — not get an
    # AMOUNT_CONFLICT against the bad first reading.
    fixed_total = entry["net"] + entry["vat"]
    corrected_reading = make_extracted(entry, total=fixed_total)
    second_result = validate_invoice(corrected_reading, detector, today=TODAY)

    assert second_result.status == "pass"
    assert second_result.issues == []


def test_genuine_duplicate_is_still_registered_and_caught(tmp_path):
    # A clean (no-error) invoice IS registered, so a later genuine
    # duplicate of it is correctly caught.
    first_entry = by_file("invoices/electricity_2026-08-10.pdf")
    second_entry = by_file("invoices/electricity_2026-08-10_dup.pdf")
    detector = DuplicateDetector(cache_path=tmp_path / "seen.json")

    first_result = validate_invoice(make_extracted(first_entry), detector, today=TODAY)
    assert first_result.status == "pass"

    second_result = validate_invoice(make_extracted(second_entry), detector, today=TODAY)

    assert second_result.status == "review"
    assert any(i.code == "DUPLICATE" for i in second_result.issues)
