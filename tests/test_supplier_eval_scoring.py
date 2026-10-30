"""Tests for the pure scoring helpers in evals/run_supplier_eval.py.
No API calls, no filesystem — hand-built fixtures only."""

from __future__ import annotations

import pytest

from evals.run_supplier_eval import (
    ANSWER_KEY_TO_CODE,
    confidently_wrong,
    expected_code,
    score_supplier_merging,
)


def test_expected_code_maps_known_category():
    assert expected_code({"file": "a.pdf", "expected_category": "Insurance"}) == "insurance"


def test_expected_code_raises_on_unmapped_category():
    with pytest.raises(KeyError):
        expected_code({"file": "a.pdf", "expected_category": "Not A Real Category"})


def test_every_answer_key_category_resolves_to_a_real_chart_code():
    from src.suppliers.categorise import load_chart

    valid_codes = {c["code"] for c in load_chart()}
    for category, code in ANSWER_KEY_TO_CODE.items():
        assert code in valid_codes, f"{category!r} maps to unknown code {code!r}"


def test_score_supplier_merging_detects_no_issues_when_all_correct():
    answer_key = [
        {"file": "a.pdf", "supplier": "Adobe Inc."},
        {"file": "b.pdf", "supplier": "Adobe Inc."},
        {"file": "c.pdf", "supplier": "Figma, Inc."},
    ]
    assigned_ids = {"a.pdf": "SUP-1", "b.pdf": "SUP-1", "c.pdf": "SUP-2"}

    missed, false = score_supplier_merging(answer_key, assigned_ids)

    assert missed == {}
    assert false == {}


def test_score_supplier_merging_detects_missed_merge():
    # Same real supplier, but the matcher gave the two files different ids.
    answer_key = [
        {"file": "a.pdf", "supplier": "Adobe Inc."},
        {"file": "b.pdf", "supplier": "Adobe Inc."},
    ]
    assigned_ids = {"a.pdf": "SUP-1", "b.pdf": "SUP-2"}

    missed, false = score_supplier_merging(answer_key, assigned_ids)

    assert missed == {"Adobe Inc.": {"SUP-1", "SUP-2"}}
    assert false == {}


def test_score_supplier_merging_detects_false_merge():
    # Two different real suppliers, but the matcher gave them the same id.
    answer_key = [
        {"file": "a.pdf", "supplier": "Energia Costa Brava, S.L."},
        {"file": "b.pdf", "supplier": "Assegurances Costa Brava, S.L."},
    ]
    assigned_ids = {"a.pdf": "SUP-1", "b.pdf": "SUP-1"}

    missed, false = score_supplier_merging(answer_key, assigned_ids)

    assert missed == {}
    assert false == {"SUP-1": {"Energia Costa Brava, S.L.", "Assegurances Costa Brava, S.L."}}


def test_confidently_wrong_filters_correctly():
    scores = [
        {"correct": True, "confidence": 0.99},
        {"correct": False, "confidence": 0.95},
        {"correct": False, "confidence": 0.5},
    ]

    result = confidently_wrong(scores, threshold=0.90)

    assert len(result) == 1
    assert result[0]["confidence"] == 0.95
