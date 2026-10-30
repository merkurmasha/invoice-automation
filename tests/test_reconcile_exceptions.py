"""Tests for src/reconcile/exceptions.py: every category of exception
row gets built correctly, and the CSV writer round-trips."""

from __future__ import annotations

import csv
from datetime import date

from src.reconcile.exceptions import (
    NO_PAYMENT_NOT_YET_DUE,
    NO_PAYMENT_OVERDUE,
    PARTIAL_PAYMENT_BALANCE,
    build_exceptions,
    write_exceptions_csv,
)
from src.reconcile.ledger import PAYABLE, RECEIVABLE, Obligation
from src.reconcile.match import BankLine, decide_bank_line

TODAY = date(2026, 10, 28)


def _obligation(invoice_number, total, due, amount_paid=0.0, kind=PAYABLE, counterparty="Some Supplier"):
    ob = Obligation(
        kind=kind,
        invoice_number=invoice_number,
        counterparty=counterparty,
        issue_date=date(2026, 1, 1),
        due_date=due,
        currency="EUR",
        total=total,
    )
    if amount_paid:
        ob.apply_payment(amount_paid, bank_line_id=0, on_date=due)
    return ob


def test_no_payment_split_into_not_yet_due_and_overdue():
    not_yet_due = _obligation("INV-1", 100.0, date(2026, 11, 1))
    overdue = _obligation("INV-2", 100.0, date(2026, 10, 1))

    rows = build_exceptions([], [not_yet_due, overdue], TODAY)

    categories = {row.invoice_numbers[0]: row.category for row in rows}
    assert categories["INV-1"] == NO_PAYMENT_NOT_YET_DUE
    assert categories["INV-2"] == NO_PAYMENT_OVERDUE


def test_no_due_date_is_treated_as_not_yet_due():
    ob = _obligation("INV-1", 100.0, due=None)

    rows = build_exceptions([], [ob], TODAY)

    assert len(rows) == 1
    assert rows[0].category == NO_PAYMENT_NOT_YET_DUE
    assert "no due date" in rows[0].reason.lower()


def test_partial_payment_balance_shows_outstanding():
    ob = _obligation("INV-1", 400.0, date(2026, 10, 1), amount_paid=150.0)

    rows = build_exceptions([], [ob], TODAY)

    assert len(rows) == 1
    assert rows[0].category == PARTIAL_PAYMENT_BALANCE
    assert rows[0].outstanding == 250.0


def test_fully_paid_invoice_is_not_an_exception():
    ob = _obligation("INV-1", 400.0, date(2026, 10, 1), amount_paid=400.0)

    rows = build_exceptions([], [ob], TODAY)

    assert rows == []


def test_unmatched_and_ambiguous_decisions_become_exception_rows():
    line = BankLine(line_id=1, txn_date=date(2026, 9, 30), description="NO MATCH HERE", amount=-12.50)
    decision = decide_bank_line(line, [])  # empty pool -> unmatched

    rows = build_exceptions([decision], [], TODAY)

    assert len(rows) == 1
    assert rows[0].category == "unmatched_bank_line"
    assert rows[0].amount == -12.50


def test_write_exceptions_csv_round_trips(tmp_path):
    ob = _obligation("INV-1", 400.0, date(2026, 10, 1), amount_paid=150.0)
    rows = build_exceptions([], [ob], TODAY)
    out_path = tmp_path / "exceptions.csv"

    write_exceptions_csv(rows, out_path)

    with out_path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    assert len(written) == 1
    assert written[0]["category"] == PARTIAL_PAYMENT_BALANCE
    assert written[0]["invoice_numbers"] == "INV-1"


def test_direction_reflects_payable_vs_receivable():
    payable = _obligation("INV-1", 100.0, date(2026, 10, 1), kind=PAYABLE)
    receivable = _obligation("INV-2", 100.0, date(2026, 10, 1), kind=RECEIVABLE)

    rows = build_exceptions([], [payable, receivable], TODAY)

    directions = {row.invoice_numbers[0]: row.direction for row in rows}
    assert directions["INV-1"] == PAYABLE
    assert directions["INV-2"] == RECEIVABLE


def test_obligation_rows_carry_due_date_not_bank_date():
    ob = _obligation("INV-1", 400.0, date(2026, 10, 1), amount_paid=150.0)

    rows = build_exceptions([], [ob], TODAY)

    assert rows[0].due_date == date(2026, 10, 1)
    assert rows[0].bank_date is None


def test_decision_rows_carry_bank_date_and_direction():
    line = BankLine(line_id=1, txn_date=date(2026, 9, 30), description="NO MATCH HERE", amount=-12.50)
    decision = decide_bank_line(line, [])

    rows = build_exceptions([decision], [], TODAY)

    assert rows[0].bank_date == date(2026, 9, 30)
    assert rows[0].due_date is None
    assert rows[0].direction == PAYABLE


def _weak_name_possible_match_fixture():
    # A truncated-name, no-reference-number bank line: full amount and a
    # plausible date, but the name match alone isn't quite strong enough
    # to clear AUTO_MATCH_THRESHOLD - lands as "possible" (see
    # test_reconcile_match.py / config.py's calibration notes for why).
    ob = _obligation(
        "INV-1", 67.15, date(2026, 8, 24), counterparty="Missatgeria Girona, S.L."
    )
    line = BankLine(line_id=1, txn_date=date(2026, 8, 22), description="MISSATGERI FACT", amount=-67.15)
    decision = decide_bank_line(line, [ob])
    assert decision.category == "possible"  # sanity-check the fixture
    return ob, decision


def test_possible_match_row_carries_the_matched_invoice_due_date():
    ob, decision = _weak_name_possible_match_fixture()

    rows = build_exceptions([decision], [ob], TODAY)

    possible_row = next(r for r in rows if r.category == "possible_match")
    assert possible_row.due_date == date(2026, 8, 24)


def test_no_payment_overdue_mentions_the_possible_match_instead_of_no_payment():
    ob, decision = _weak_name_possible_match_fixture()
    assert ob.amount_paid == 0.0  # "possible" is never applied, so the obligation is still unpaid

    rows = build_exceptions([decision], [ob], TODAY)

    overdue_row = next(r for r in rows if r.category == NO_PAYMENT_OVERDUE)
    assert "possible payment found" in overdue_row.reason.lower()
    assert "no payment seen" not in overdue_row.reason.lower()


def test_no_payment_overdue_keeps_plain_reason_when_nothing_was_found():
    ob = _obligation("INV-1", 100.0, date(2026, 1, 20))

    rows = build_exceptions([], [ob], TODAY)

    overdue_row = next(r for r in rows if r.category == NO_PAYMENT_OVERDUE)
    assert "no payment seen" in overdue_row.reason.lower()
