"""Tests for the synthetic dataset generator. No Claude API calls here -
this phase doesn't touch the LLM at all, it only builds deterministic
fixture data with plain code.
"""
from __future__ import annotations

import hashlib
import json
import math

import pytest

from src.synthetic.generate import generate

EXPECTED_TRAP_COUNTS = {
    "duplicate_exact": 2,
    "duplicate_near": 1,
    "maths_error": 3,
    "no_due_date": 2,
    "name_variant": 4,
    "reverse_charge": 1,
    "credit_note": 1,
}


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("synthetic")
    answer_key = generate(out_dir)
    return out_dir, answer_key


def test_every_file_in_the_answer_key_exists(dataset):
    out_dir, answer_key = dataset
    for entry in answer_key:
        assert (out_dir / entry["file"]).exists(), f"missing file: {entry['file']}"


def test_net_plus_vat_equals_total_except_maths_traps(dataset):
    _, answer_key = dataset
    for entry in answer_key:
        if entry["trap"] == "maths_error":
            continue
        expected_total = round(entry["net"] + entry["vat"], 2)
        assert math.isclose(expected_total, entry["total"], abs_tol=0.01), entry["file"]


def test_maths_trap_entries_are_flagged_inconsistent(dataset):
    _, answer_key = dataset
    maths_trap_entries = [e for e in answer_key if e["trap"] == "maths_error"]
    assert len(maths_trap_entries) > 0
    for entry in maths_trap_entries:
        assert entry.get("printed_total_is_consistent") is False
        expected_total = round(entry["net"] + entry["vat"], 2)
        assert not math.isclose(expected_total, entry["total"], abs_tol=0.01)


def test_non_maths_trap_entries_have_no_consistency_flag(dataset):
    _, answer_key = dataset
    for entry in answer_key:
        if entry["trap"] != "maths_error":
            assert "printed_total_is_consistent" not in entry


def test_trap_counts_match_the_requested_set(dataset):
    _, answer_key = dataset
    pdf_entries = [e for e in answer_key if e["file"].startswith("invoices/")]
    counts: dict[str, int] = {}
    for entry in pdf_entries:
        if entry["trap"]:
            counts[entry["trap"]] = counts.get(entry["trap"], 0) + 1
    assert counts == EXPECTED_TRAP_COUNTS


def test_dataset_sizes(dataset):
    _, answer_key = dataset
    pdf_entries = [e for e in answer_key if e["file"].startswith("invoices/")]
    photo_entries = [e for e in answer_key if e["file"].startswith("photos/")]
    assert len(pdf_entries) == 40
    assert len(photo_entries) == 6


def test_sales_invoices_csv_has_twelve_rows(dataset):
    out_dir, _ = dataset
    lines = (out_dir / "sales_invoices.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 13  # header + 12 invoices


def test_bank_statement_balance_is_internally_consistent(dataset):
    out_dir, _ = dataset
    import csv

    with (out_dir / "bank" / "statement.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 0
    running = float(rows[0]["balance"]) - float(rows[0]["amount"])
    for row in rows:
        running = round(running + float(row["amount"]), 2)
        assert math.isclose(running, float(row["balance"]), abs_tol=0.01)


def test_generation_is_deterministic(tmp_path_factory):
    out_a = tmp_path_factory.mktemp("synthetic_a")
    out_b = tmp_path_factory.mktemp("synthetic_b")
    key_a = generate(out_a)
    key_b = generate(out_b)
    assert json.dumps(key_a, sort_keys=True) == json.dumps(key_b, sort_keys=True)

    sample_file = key_a[0]["file"]
    hash_a = hashlib.sha256((out_a / sample_file).read_bytes()).hexdigest()
    hash_b = hashlib.sha256((out_b / sample_file).read_bytes()).hexdigest()
    assert hash_a == hash_b
