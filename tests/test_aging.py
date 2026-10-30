"""Tests for src/receivables/aging.py, including every edge case
CLAUDE.md's plan calls out: due today, 1 day late, and the exact
boundary days of each bucket."""

from __future__ import annotations

from datetime import date

from src.receivables import aging
from src.receivables.tracker import Invoice, ReceivablesTracker


def test_not_yet_due_is_current():
    assert aging.aging_bucket(date(2026, 11, 1), date(2026, 10, 28)) == aging.CURRENT


def test_due_today_is_current():
    assert aging.aging_bucket(date(2026, 10, 28), date(2026, 10, 28)) == aging.CURRENT


def test_one_day_late_is_1_30():
    assert aging.aging_bucket(date(2026, 10, 27), date(2026, 10, 28)) == aging.BUCKET_1_30


def test_exactly_30_days_late_is_1_30():
    due = date(2026, 9, 28)
    today = date(2026, 10, 28)
    assert (today - due).days == 30
    assert aging.aging_bucket(due, today) == aging.BUCKET_1_30


def test_exactly_31_days_late_is_31_60():
    due = date(2026, 9, 27)
    today = date(2026, 10, 28)
    assert (today - due).days == 31
    assert aging.aging_bucket(due, today) == aging.BUCKET_31_60


def test_exactly_60_days_late_is_31_60():
    due = date(2026, 8, 29)
    today = date(2026, 10, 28)
    assert (today - due).days == 60
    assert aging.aging_bucket(due, today) == aging.BUCKET_31_60


def test_exactly_61_days_late_is_60_plus():
    due = date(2026, 8, 28)
    today = date(2026, 10, 28)
    assert (today - due).days == 61
    assert aging.aging_bucket(due, today) == aging.BUCKET_60_PLUS


def _invoice(invoice_number, due_date, total, status="open", amount_paid=0.0) -> Invoice:
    inv = Invoice(
        invoice_number=invoice_number,
        customer_name="Customer",
        issue_date=date(2026, 1, 1),
        due_date=due_date,
        currency="EUR",
        net=total,
        vat=0.0,
        total=total,
        amount_paid=amount_paid,
        status=status,
    )
    return inv


def test_aging_summary_counts_and_sums_excluding_paid():
    tracker = ReceivablesTracker()
    today = date(2026, 10, 28)
    tracker.invoices["A"] = _invoice("A", date(2026, 11, 1), 100.0)  # current
    tracker.invoices["B"] = _invoice("B", date(2026, 10, 20), 200.0)  # 8 days late -> 1-30
    tracker.invoices["C"] = _invoice("C", date(2026, 9, 1), 300.0)  # 57 days late -> 31-60
    tracker.invoices["D"] = _invoice("D", date(2026, 7, 1), 400.0)  # 119 days late -> 60+
    tracker.invoices["PAID"] = _invoice(
        "PAID", date(2026, 7, 1), 500.0, status="paid", amount_paid=500.0
    )

    summary = aging.aging_summary(tracker, today)

    assert summary[aging.CURRENT] == {"count": 1, "outstanding": 100.0}
    assert summary[aging.BUCKET_1_30] == {"count": 1, "outstanding": 200.0}
    assert summary[aging.BUCKET_31_60] == {"count": 1, "outstanding": 300.0}
    assert summary[aging.BUCKET_60_PLUS] == {"count": 1, "outstanding": 400.0}
    total_counted = sum(row["count"] for row in summary.values())
    assert total_counted == 4  # the paid invoice never shows up anywhere
