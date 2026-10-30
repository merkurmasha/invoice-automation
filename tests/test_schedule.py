"""Tests for src/receivables/schedule.py: stage dates, the
latest-missed-stage rule, no duplicate drafts, and paid invoices being
skipped. Uses a temp log file, never the real data/reminder_log.csv."""

from __future__ import annotations

from datetime import date

from src.receivables import schedule
from src.receivables.tracker import Invoice, ReceivablesTracker

DUE = date(2026, 10, 1)


def _tracker_with_one_invoice(status="open", amount_paid=0.0) -> ReceivablesTracker:
    tracker = ReceivablesTracker()
    tracker.invoices["INV-1"] = Invoice(
        invoice_number="INV-1",
        customer_name="Customer",
        issue_date=date(2026, 9, 1),
        due_date=DUE,
        currency="EUR",
        net=100.0,
        vat=0.0,
        total=100.0,
        amount_paid=amount_paid,
        status=status,
    )
    return tracker


def test_stage_date_offsets():
    assert schedule.stage_date(DUE, 1) == DUE
    assert schedule.stage_date(DUE, 2) == date(2026, 10, 8)
    assert schedule.stage_date(DUE, 3) == date(2026, 10, 15)


def test_nothing_due_before_due_date(tmp_path):
    tracker = _tracker_with_one_invoice()
    log_path = tmp_path / "reminder_log.csv"

    due = schedule.reminders_due(tracker, date(2026, 9, 30), log_path=log_path)

    assert due == []


def test_stage_1_due_on_the_due_date(tmp_path):
    tracker = _tracker_with_one_invoice()
    log_path = tmp_path / "reminder_log.csv"

    due = schedule.reminders_due(tracker, DUE, log_path=log_path)

    assert len(due) == 1
    assert due[0].invoice_id == "INV-1"
    assert due[0].stage == 1


def test_only_the_latest_missed_stage_is_returned(tmp_path):
    """10 days overdue with nothing drafted yet: stage 1 (due date) and
    stage 2 (due+7) have both technically arrived, but stage 3 (due+14)
    hasn't yet — only stage 2, the latest arrived stage, should be
    reported, not both 1 and 2."""
    tracker = _tracker_with_one_invoice()
    log_path = tmp_path / "reminder_log.csv"
    today = date(2026, 10, 11)  # 10 days after the Oct 1 due date

    due = schedule.reminders_due(tracker, today, log_path=log_path)

    assert len(due) == 1
    assert due[0].stage == 2


def test_already_drafted_stage_is_not_repeated(tmp_path):
    tracker = _tracker_with_one_invoice()
    log_path = tmp_path / "reminder_log.csv"
    schedule.record_drafted("INV-1", 1, DUE, log_path=log_path)

    due = schedule.reminders_due(tracker, DUE, log_path=log_path)

    assert due == []


def test_next_stage_becomes_due_after_earlier_stage_logged(tmp_path):
    tracker = _tracker_with_one_invoice()
    log_path = tmp_path / "reminder_log.csv"
    schedule.record_drafted("INV-1", 1, DUE, log_path=log_path)

    due = schedule.reminders_due(tracker, date(2026, 10, 8), log_path=log_path)

    assert len(due) == 1
    assert due[0].stage == 2


def test_paid_invoices_are_skipped(tmp_path):
    tracker = _tracker_with_one_invoice(status="paid", amount_paid=100.0)
    log_path = tmp_path / "reminder_log.csv"

    due = schedule.reminders_due(tracker, date(2026, 10, 20), log_path=log_path)

    assert due == []


def test_load_drafted_stages_on_missing_log_returns_empty(tmp_path):
    log_path = tmp_path / "does_not_exist.csv"

    assert schedule.load_drafted_stages(log_path) == {}
