"""Tests for src/receivables/tracker.py. Plain deterministic code, no
API calls involved.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.receivables import tracker as tracker_module

SALES_INVOICES_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "synthetic" / "sales_invoices.csv"
)


def test_loading_the_synthetic_csv_leaves_the_file_untouched():
    before = SALES_INVOICES_PATH.read_text()

    loaded = tracker_module.ReceivablesTracker.from_csv(SALES_INVOICES_PATH)

    assert SALES_INVOICES_PATH.read_text() == before
    assert len(loaded.invoices) == 12
    first = loaded.invoices["CBS-2026-0001"]
    assert first.customer_name == "Taverna del Call, S.L."
    assert first.due_date == date(2026, 11, 5)
    assert first.total == 1727.24
    assert first.amount_paid == 0.0
    assert first.amount_outstanding == 1727.24
    assert first.status == tracker_module.STATUS_OPEN
    # No language column in this CSV — every invoice should fall back
    # to None here, and to English later in draft.py.
    assert first.language is None


def _one_invoice_tracker() -> tracker_module.ReceivablesTracker:
    tracker = tracker_module.ReceivablesTracker()
    tracker.invoices["INV-1"] = tracker_module.Invoice(
        invoice_number="INV-1",
        customer_name="Test Customer",
        issue_date=date(2026, 1, 1),
        due_date=date(2026, 2, 1),
        currency="EUR",
        net=100.0,
        vat=21.0,
        total=121.0,
    )
    return tracker


def test_partial_payment_sets_partially_paid():
    tracker = _one_invoice_tracker()

    invoice = tracker.mark_payment("INV-1", 50.0, date(2026, 2, 5))

    assert invoice.status == tracker_module.STATUS_PARTIALLY_PAID
    assert invoice.amount_paid == 50.0
    assert invoice.amount_outstanding == 71.0
    assert tracker.overpayment_flags == []


def test_exact_payment_sets_paid():
    tracker = _one_invoice_tracker()

    invoice = tracker.mark_payment("INV-1", 121.0, date(2026, 2, 5))

    assert invoice.status == tracker_module.STATUS_PAID
    assert invoice.amount_outstanding == 0.0
    assert tracker.overpayment_flags == []


def test_overpayment_is_flagged_not_silently_accepted():
    tracker = _one_invoice_tracker()

    invoice = tracker.mark_payment("INV-1", 150.0, date(2026, 2, 5))

    assert invoice.status == tracker_module.STATUS_PAID
    assert invoice.amount_paid == 150.0
    # Outstanding reads as zero, never negative...
    assert invoice.amount_outstanding == 0.0
    # ...but the overpayment itself is recorded for a human to see.
    assert len(tracker.overpayment_flags) == 1
    flag = tracker.overpayment_flags[0]
    assert flag.invoice_id == "INV-1"
    assert flag.overpaid_by == 29.0


def test_two_partial_payments_that_sum_to_an_overpayment_are_flagged():
    tracker = _one_invoice_tracker()
    tracker.mark_payment("INV-1", 100.0, date(2026, 2, 2))

    invoice = tracker.mark_payment("INV-1", 50.0, date(2026, 2, 6))

    assert invoice.amount_paid == 150.0
    assert len(tracker.overpayment_flags) == 1


def test_mark_payment_on_unknown_invoice_raises():
    tracker = _one_invoice_tracker()

    with pytest.raises(tracker_module.UnknownInvoiceError):
        tracker.mark_payment("NOT-A-REAL-INVOICE", 10.0, date(2026, 2, 5))
