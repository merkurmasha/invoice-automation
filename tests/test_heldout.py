"""Tests for the held-out dataset generator (src/synthetic/heldout.py).
No Claude API calls here - this is pure deterministic fixture
generation, same as tests/test_synthetic.py for the main dataset.
"""
from __future__ import annotations

import json
import math

import pytest

from src.synthetic.heldout import generate

EXPECTED_CHALLENGES = {
    "us_date",
    "written_month",
    "two_column_layout",
    "multi_page",
    "tax_inclusive",
    "multiple_vat_rates",
    "scan_like",
    "handwritten_note",
    "european_numbers",
    "no_invoice_number",
    "usd_with_symbol_variants",
    "credit_note_es",
}


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("heldout")
    answer_key = generate(out_dir)
    return out_dir, answer_key


def test_every_file_in_the_answer_key_exists(dataset):
    out_dir, answer_key = dataset
    for entry in answer_key:
        assert (out_dir / entry["file"]).exists(), f"missing file: {entry['file']}"


def test_every_entry_lives_under_invoices_or_photos(dataset):
    _, answer_key = dataset
    for entry in answer_key:
        assert entry["file"].startswith("invoices/") or entry["file"].startswith("photos/")


def test_all_requested_challenge_types_are_present(dataset):
    _, answer_key = dataset
    seen = {entry["challenge"] for entry in answer_key}
    assert seen == EXPECTED_CHALLENGES


def test_written_month_has_one_document_per_language(dataset):
    _, answer_key = dataset
    written_month_entries = [e for e in answer_key if e["challenge"] == "written_month"]
    languages = {e["language"] for e in written_month_entries}
    assert languages == {"en", "es", "ca"}
    assert len(written_month_entries) == 3


def test_scan_like_is_a_photo_with_no_matching_invoices_entry(dataset):
    _, answer_key = dataset
    scan_entry = next(e for e in answer_key if e["challenge"] == "scan_like")
    assert scan_entry["file"].startswith("photos/")
    assert scan_entry["file"].endswith(".jpg")
    # scan_like deliberately keeps only the degraded photo, not the
    # intermediate PDF it was rendered from - so no invoices/ entry
    # should exist for the same document.
    stem = scan_entry["file"].rsplit("/", 1)[-1].removesuffix(".jpg")
    assert not any(e["file"] == f"invoices/{stem}.pdf" for e in answer_key)


def test_net_plus_vat_equals_total_where_both_are_printed(dataset):
    _, answer_key = dataset
    for entry in answer_key:
        if entry["net"] is None or entry["vat"] is None:
            continue
        expected_total = round(entry["net"] + entry["vat"], 2)
        assert math.isclose(expected_total, entry["total"], abs_tol=0.01), entry["file"]


def test_handwritten_note_has_no_net_or_vat_printed(dataset):
    _, answer_key = dataset
    entry = next(e for e in answer_key if e["challenge"] == "handwritten_note")
    assert entry["net"] is None
    assert entry["vat"] is None
    assert entry["total"] is not None


def test_no_invoice_number_entry_has_a_null_invoice_number(dataset):
    _, answer_key = dataset
    entry = next(e for e in answer_key if e["challenge"] == "no_invoice_number")
    assert entry["invoice_number"] is None


def test_credit_note_es_is_negative_and_tagged_credit_note_trap(dataset):
    _, answer_key = dataset
    entry = next(e for e in answer_key if e["challenge"] == "credit_note_es")
    assert entry["document_type"] == "credit_note"
    assert entry["trap"] == "credit_note"
    assert entry["net"] < 0 and entry["vat"] < 0 and entry["total"] < 0


def test_trap_is_null_unless_it_is_a_genuine_existing_trap_type(dataset):
    _, answer_key = dataset
    allowed = {
        None,
        "duplicate_exact",
        "duplicate_near",
        "maths_error",
        "no_due_date",
        "name_variant",
        "reverse_charge",
        "credit_note",
    }
    for entry in answer_key:
        assert entry["trap"] in allowed, f"{entry['file']}: unexpected trap {entry['trap']!r}"


def test_us_date_document_has_an_unambiguous_day_over_12(dataset):
    _, answer_key = dataset
    entry = next(e for e in answer_key if e["challenge"] == "us_date")
    assert entry["issue_date"] == "2026-03-04"
    assert entry["due_date"] == "2026-03-25"  # day 25 > 12: unambiguous


def test_dataset_size_is_about_twelve(dataset):
    _, answer_key = dataset
    assert 12 <= len(answer_key) <= 16


def test_generation_is_deterministic(tmp_path_factory):
    import hashlib

    out_a = tmp_path_factory.mktemp("heldout_a")
    out_b = tmp_path_factory.mktemp("heldout_b")
    key_a = generate(out_a)
    key_b = generate(out_b)
    assert json.dumps(key_a, sort_keys=True) == json.dumps(key_b, sort_keys=True)

    sample_file = key_a[0]["file"]
    hash_a = hashlib.sha256((out_a / sample_file).read_bytes()).hexdigest()
    hash_b = hashlib.sha256((out_b / sample_file).read_bytes()).hexdigest()
    assert hash_a == hash_b
