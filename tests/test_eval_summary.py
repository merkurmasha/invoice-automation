"""Tests for scripts/eval_summary.py: reads this project's real eval
result files and falls back to hardcoded numbers only when none exist.
No LLM call involved — it only reads already-committed JSON."""

from __future__ import annotations

import json

from scripts.eval_summary import load_accuracy_strip


def test_reads_the_projects_real_eval_result_files():
    result = load_accuracy_strip()

    assert result["missing"] == []
    assert result["extraction_synthetic_before_pct"] == 97.4
    assert result["extraction_synthetic_after_pct"] == 100.0
    assert result["extraction_heldout_pct"] == 98.6
    assert result["categorisation_synthetic_pct"] == 87.0
    assert result["categorisation_heldout_pct"] == 64.3
    assert result["reconciliation_correct"] == 36
    assert result["reconciliation_expected"] == 36
    assert result["reconciliation_false_matches"] == 0


def test_falls_back_to_hardcoded_numbers_when_no_result_files_exist(tmp_path):
    result = load_accuracy_strip(tmp_path)

    assert sorted(result["missing"]) == [
        "categorisation_heldout",
        "categorisation_synthetic",
        "extraction_heldout",
        "extraction_synthetic",
        "reconciliation",
    ]
    # Still returns usable numbers, not None/missing keys.
    assert result["extraction_synthetic_after_pct"] == 100.0
    assert result["reconciliation_correct"] == 36


def test_bucketing_is_by_content_shape_not_filename(tmp_path):
    # A categorisation-heldout-shaped file named nothing like the real
    # ones should still land in the right bucket.
    (tmp_path / "whatever.json").write_text(
        json.dumps(
            {
                "dataset": "heldout",
                "category_accuracy": {"correct": 1, "total": 2},
            }
        )
    )
    result = load_accuracy_strip(tmp_path)

    assert result["categorisation_heldout_pct"] == 50.0
    assert "categorisation_heldout" not in result["missing"]
    assert "categorisation_synthetic" in result["missing"]


def test_unreadable_json_file_is_skipped_not_crashed(tmp_path):
    (tmp_path / "broken.json").write_text("{not valid json")

    result = load_accuracy_strip(tmp_path)

    assert "extraction_synthetic" in result["missing"]


def test_extraction_synthetic_reports_first_and_last_by_filename_order(tmp_path):
    (tmp_path / "2026-01-01_0000_a.json").write_text(
        json.dumps({"overall_accuracy": {"correct": 90, "total": 100}})
    )
    (tmp_path / "2026-01-02_0000_b.json").write_text(
        json.dumps({"overall_accuracy": {"correct": 95, "total": 100}})
    )
    (tmp_path / "2026-01-03_0000_c.json").write_text(
        json.dumps({"overall_accuracy": {"correct": 100, "total": 100}})
    )

    result = load_accuracy_strip(tmp_path)

    assert result["extraction_synthetic_before_pct"] == 90.0
    assert result["extraction_synthetic_after_pct"] == 100.0
