"""Tests for scripts/receivables_today.py. Per CLAUDE.md, no real
Claude API calls — a fake client returns canned responses, same
pattern as tests/test_draft.py (which this wrapper calls into).
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from scripts import receivables_today as receivables_today_module
from src.receivables import draft as draft_module

CSV_HEADER = ["invoice_number", "customer_name", "issue_date", "due_date", "currency", "net", "vat", "total"]

VALID_BODY = (
    "Dear Test Customer,\n\nThis is a reminder that invoice INV-1 for "
    "121.00 EUR is now overdue. Please arrange payment at your "
    "convenience.\n\nBest regards,\nCosta Brava Studio S.L."
)
VALID_RAW = {"subject": "Payment reminder: invoice INV-1", "body": VALID_BODY}

MISSING_FACTS_RAW = {
    "subject": "Payment reminder",
    "body": "Dear Test Customer,\n\nYour invoice is overdue. Please pay soon.",
}


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, tool_input: dict) -> None:
        self.input = tool_input


class _FakeUsage:
    def __init__(self) -> None:
        self.input_tokens = 200
        self.output_tokens = 100


class _FakeResponse:
    def __init__(self, tool_input: dict) -> None:
        self.content = [_FakeToolUseBlock(tool_input)]
        self.usage = _FakeUsage()


class _FakeMessages:
    def __init__(self, client: "FakeClient") -> None:
        self._client = client

    def create(self, **kwargs):
        self._client.calls += 1
        item = self._client.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _FakeResponse(item)


class FakeClient:
    """Stands in for anthropic.Anthropic: returns queued responses in order."""

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.messages = _FakeMessages(self)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(draft_module, "CACHE_DIR", tmp_path / "cache")


@pytest.fixture
def overdue_csv(tmp_path) -> Path:
    path = tmp_path / "sales_invoices.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        writer.writerow(
            ["INV-1", "Test Customer", "2026-09-01", "2026-10-01", "EUR", "100.00", "21.00", "121.00"]
        )
    return path


def test_no_reminders_due_returns_pass_with_no_drafts(tmp_path):
    path = tmp_path / "sales_invoices.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        writer.writerow(
            ["INV-1", "Test Customer", "2026-10-01", "2026-12-01", "EUR", "100.00", "21.00", "121.00"]
        )

    result = receivables_today_module.draft_due_reminders(
        date(2026, 10, 20),
        csv_path=path,
        log_path=tmp_path / "reminder_log.csv",
        drafts_dir=tmp_path / "drafts",
    )

    assert result["status"] == "pass"
    assert result["due_count"] == 0
    assert result["drafts"] == []


def test_due_reminder_is_drafted_with_to_subject_body(overdue_csv, tmp_path):
    client = FakeClient([VALID_RAW])

    result = receivables_today_module.draft_due_reminders(
        date(2026, 10, 1),
        csv_path=overdue_csv,
        log_path=tmp_path / "reminder_log.csv",
        drafts_dir=tmp_path / "drafts",
        client=client,
    )

    assert result["status"] == "pass"
    assert result["due_count"] == 1
    draft_entry = result["drafts"][0]
    assert draft_entry["invoice"] == "INV-1"
    assert draft_entry["stage"] == 1
    assert draft_entry["to"] == "Test Customer"
    assert draft_entry["subject"] == "Payment reminder: invoice INV-1"
    assert "INV-1" in draft_entry["body"]
    assert "121.00" in draft_entry["body"]
    assert draft_entry["needs_review"] is False


def test_reminder_log_prevents_the_same_stage_being_drafted_twice(overdue_csv, tmp_path):
    log_path = tmp_path / "reminder_log.csv"
    client = FakeClient([VALID_RAW])
    receivables_today_module.draft_due_reminders(
        date(2026, 10, 1),
        csv_path=overdue_csv,
        log_path=log_path,
        drafts_dir=tmp_path / "drafts",
        client=client,
    )

    second_client = FakeClient([])
    result = receivables_today_module.draft_due_reminders(
        date(2026, 10, 1),
        csv_path=overdue_csv,
        log_path=log_path,
        drafts_dir=tmp_path / "drafts",
        client=second_client,
    )

    assert result["due_count"] == 0
    assert second_client.calls == 0


def test_dry_run_drafts_without_touching_the_reminder_log(overdue_csv, tmp_path):
    log_path = tmp_path / "reminder_log.csv"
    client = FakeClient([VALID_RAW])

    result = receivables_today_module.draft_due_reminders(
        date(2026, 10, 1),
        csv_path=overdue_csv,
        log_path=log_path,
        drafts_dir=tmp_path / "drafts",
        client=client,
        dry_run=True,
    )

    assert result["due_count"] == 1
    assert not log_path.exists()

    second_client = FakeClient([VALID_RAW])
    second_result = receivables_today_module.draft_due_reminders(
        date(2026, 10, 1),
        csv_path=overdue_csv,
        log_path=log_path,
        drafts_dir=tmp_path / "drafts",
        client=second_client,
        dry_run=True,
    )

    assert second_result["due_count"] == 1
    assert not log_path.exists()


def test_draft_missing_required_facts_is_flagged_review(overdue_csv, tmp_path):
    client = FakeClient([MISSING_FACTS_RAW, MISSING_FACTS_RAW])

    result = receivables_today_module.draft_due_reminders(
        date(2026, 10, 1),
        csv_path=overdue_csv,
        log_path=tmp_path / "reminder_log.csv",
        drafts_dir=tmp_path / "drafts",
        client=client,
    )

    assert result["status"] == "review"
    assert result["drafts"][0]["needs_review"] is True


def test_main_exits_zero_for_pass(overdue_csv, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        receivables_today_module.draft,
        "_default_client",
        lambda: FakeClient([VALID_RAW]),
    )

    exit_code = receivables_today_module.main(
        [
            "--today",
            "2026-10-01",
            "--csv",
            str(overdue_csv),
            "--log-path",
            str(tmp_path / "reminder_log.csv"),
            "--drafts-dir",
            str(tmp_path / "drafts"),
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert '"status": "pass"' in out


def test_main_dry_run_does_not_write_the_reminder_log(overdue_csv, tmp_path, monkeypatch):
    monkeypatch.setattr(
        receivables_today_module.draft,
        "_default_client",
        lambda: FakeClient([VALID_RAW]),
    )
    log_path = tmp_path / "reminder_log.csv"

    exit_code = receivables_today_module.main(
        [
            "--today",
            "2026-10-01",
            "--csv",
            str(overdue_csv),
            "--log-path",
            str(log_path),
            "--drafts-dir",
            str(tmp_path / "drafts"),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert not log_path.exists()
