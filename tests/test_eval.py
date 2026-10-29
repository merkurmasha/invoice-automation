"""Tests for evals/scoring.py. No API calls, no real cache, no real
answer key — every test builds a tiny fake answer-key entry and
ExtractedInvoice directly, so these tests check the scoring logic
itself, not any particular extraction result.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.extract import config as extract_config
from src.extract.schema import ExtractedInvoice
from src.validate.checks import Issue
from src.validate.duplicates import DuplicateDetector
from src.validate.validate import validate_invoice

from evals import run_eval, scoring
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


# ---------------------------------------------------------------------------
# duplicate_exact: only the repeat (_dup) file should be expected to raise
# DUPLICATE. The synthetic generator tags the original and its _dup copy
# with the same trap, so the original — being the first thing the
# detector ever sees — can never raise DUPLICATE itself.
# ---------------------------------------------------------------------------


def test_duplicate_exact_original_expects_no_error_not_is_repeat():
    result = scoring.evaluate_trap("invoices/electricity_2026-08-10.pdf", "duplicate_exact", [], is_repeat=False)

    assert result.caught is True


def test_duplicate_exact_original_with_an_error_is_a_miss():
    issues = [Issue("error", "MATH_MISMATCH", "unrelated problem")]

    result = scoring.evaluate_trap("invoices/electricity_2026-08-10.pdf", "duplicate_exact", issues, is_repeat=False)

    assert result.caught is False


def test_duplicate_exact_repeat_expects_duplicate_is_repeat_true():
    issues = [Issue("error", "DUPLICATE", "seen before")]

    result = scoring.evaluate_trap("invoices/electricity_2026-08-10_dup.pdf", "duplicate_exact", issues, is_repeat=True)

    assert result.caught is True


def test_duplicate_exact_repeat_missing_duplicate_is_a_miss():
    result = scoring.evaluate_trap("invoices/electricity_2026-08-10_dup.pdf", "duplicate_exact", [], is_repeat=True)

    assert result.caught is False


def test_duplicate_exact_defaults_to_not_is_repeat():
    # is_repeat defaults to False, so a caller that forgets to pass it
    # gets the "original" expectation, not a silent pass-through.
    result = scoring.evaluate_trap("invoices/x.pdf", "duplicate_exact", [])

    assert result.caught is True


# ---------------------------------------------------------------------------
# --dataset heldout (evals/run_eval.py). No real API call anywhere here -
# extract_module.is_cached and extract_module.extract_invoice are both
# monkeypatched, so "extraction" is just a lookup into the answer key
# itself. This checks the --dataset *plumbing* (paths, filename, the new
# "By challenge" report section), not extraction accuracy.
# ---------------------------------------------------------------------------


def _extracted_from_answer(entry: dict) -> ExtractedInvoice:
    return ExtractedInvoice.model_validate(
        {
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
            "confidence": {field: 0.95 for field in CONFIDENCE_FIELD_NAMES},
        }
    )


def test_dataset_flag_defaults_to_synthetic():
    assert run_eval.parse_args([]).dataset == "synthetic"


def test_dataset_flag_accepts_heldout():
    assert run_eval.parse_args(["--dataset", "heldout"]).dataset == "heldout"


def test_dataset_heldout_runs_end_to_end_with_a_mocked_extractor(tmp_path, monkeypatch):
    heldout_dir = extract_config.PROJECT_ROOT / "data" / "heldout"
    answers_by_file = {e["file"]: e for e in json.loads((heldout_dir / "answer_key.json").read_text())}

    def fake_extract_invoice(path, model=None, on_usage=None):
        rel = Path(path).relative_to(heldout_dir).as_posix()
        return _extracted_from_answer(answers_by_file[rel])

    monkeypatch.setattr(run_eval.extract_module, "is_cached", lambda path, model=None: True)
    monkeypatch.setattr(run_eval.extract_module, "extract_invoice", fake_extract_invoice)
    monkeypatch.setattr(run_eval, "RESULTS_DIR", tmp_path)

    exit_code = run_eval.main(["--dataset", "heldout"])

    assert exit_code == 0
    md_files = list(tmp_path.glob("*_heldout.md"))
    json_files = list(tmp_path.glob("*_heldout.json"))
    assert len(md_files) == 1
    assert len(json_files) == 1

    report = json.loads(json_files[0].read_text())
    # A perfect mocked extraction should score 100% and expose a
    # per-challenge accuracy breakdown that the synthetic report doesn't have.
    assert report["overall_accuracy"]["correct"] == report["overall_accuracy"]["total"]
    assert "accuracy_by_challenge" in report
    assert "us_date" in report["accuracy_by_challenge"]
    assert "By challenge" in md_files[0].read_text()


def test_default_dataset_run_is_unaffected_by_the_dataset_flag(tmp_path, monkeypatch):
    synthetic_dir = extract_config.PROJECT_ROOT / "data" / "synthetic"
    answers_by_file = {e["file"]: e for e in json.loads((synthetic_dir / "answer_key.json").read_text())}

    def fake_extract_invoice(path, model=None, on_usage=None):
        rel = Path(path).relative_to(synthetic_dir).as_posix()
        return _extracted_from_answer(answers_by_file[rel])

    monkeypatch.setattr(run_eval.extract_module, "is_cached", lambda path, model=None: True)
    monkeypatch.setattr(run_eval.extract_module, "extract_invoice", fake_extract_invoice)
    monkeypatch.setattr(run_eval, "RESULTS_DIR", tmp_path)

    exit_code = run_eval.main([])  # no --dataset flag at all

    assert exit_code == 0
    md_files = list(tmp_path.glob("*.md"))
    assert len(md_files) == 1
    assert "heldout" not in md_files[0].name
    assert "synthetic" not in md_files[0].name  # default filename pattern is unsuffixed

    md_text = md_files[0].read_text()
    assert "By challenge" not in md_text

    report = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert "accuracy_by_challenge" not in report
