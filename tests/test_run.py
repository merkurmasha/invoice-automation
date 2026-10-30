"""A light smoke test for the receivables CLI: exit codes and that
--draft without typing "yes" never writes anything or touches the API.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from src.receivables import run as run_module

CSV_HEADER = ["invoice_number", "customer_name", "issue_date", "due_date", "currency", "net", "vat", "total"]


@pytest.fixture
def small_csv(tmp_path) -> Path:
    path = tmp_path / "sales_invoices.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        writer.writerow(["INV-1", "Customer A", "2026-09-01", "2026-10-01", "EUR", "100.00", "21.00", "121.00"])
    return path


def test_plain_run_prints_summary_and_exits_zero(small_csv, tmp_path, capsys):
    exit_code = run_module.main(
        [
            "--today",
            "2026-10-20",
            "--csv",
            str(small_csv),
            "--log-path",
            str(tmp_path / "reminder_log.csv"),
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Aging summary as of 2026-10-20" in out
    assert "INV-1" in out
    assert "--draft" in out  # tells the user how to actually draft it


def test_draft_without_confirmation_writes_nothing(small_csv, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "no")

    exit_code = run_module.main(
        [
            "--today",
            "2026-10-20",
            "--draft",
            "--csv",
            str(small_csv),
            "--log-path",
            str(tmp_path / "reminder_log.csv"),
        ]
    )

    assert exit_code == 1
    assert not (tmp_path / "reminder_log.csv").exists()
    out = capsys.readouterr().out
    assert "Aborted" in out
