"""Decision-level tests for src/reconcile/match.py: score thresholds,
partial payments, one payment covering several invoices, duplicate use
of a bank line prevented, ambiguous lines, and the "same amount alone
isn't enough" rule. All crafted obligations/bank lines, no API calls.
"""

from __future__ import annotations

from datetime import date

from src.reconcile import config
from src.reconcile.ledger import PAYABLE, RECEIVABLE, Obligation
from src.reconcile.match import BankLine, decide_bank_line, reconcile


def _obligation(invoice_number, counterparty, total, *, kind=PAYABLE, issue=date(2026, 1, 1), due=date(2026, 1, 31), currency="EUR"):
    return Obligation(
        kind=kind,
        invoice_number=invoice_number,
        counterparty=counterparty,
        issue_date=issue,
        due_date=due,
        currency=currency,
        total=total,
    )


def _line(line_id, txn_date, description, amount):
    return BankLine(line_id=line_id, txn_date=txn_date, description=description, amount=amount)


# --- score thresholds --------------------------------------------------------


def test_exact_reference_and_amount_auto_matches():
    ob = _obligation("INV-1", "Some Supplier S.L.", 100.0, due=date(2026, 1, 20))
    line = _line(1, date(2026, 1, 18), "PAGO FRA INV-1", -100.0)

    decision = decide_bank_line(line, [ob])

    assert decision.category == "auto"
    assert decision.applied is True
    assert ob.amount_paid == 100.0


def test_weak_evidence_is_not_matched_at_all():
    ob = _obligation("INV-1", "Some Supplier S.L.", 100.0, issue=date(2026, 3, 1), due=date(2026, 3, 31))
    # No reference, no name overlap, and paid before the invoice even
    # existed - every signal fails.
    line = _line(1, date(2026, 1, 1), "UNRELATED TEXT HERE", -100.0)

    decision = decide_bank_line(line, [ob])

    assert decision.category == "unmatched"
    assert decision.applied is False
    assert ob.amount_paid == 0.0


# --- partial payments --------------------------------------------------------


def test_partial_payment_is_applied_and_always_reported():
    ob = _obligation("INV-1", "Some Supplier S.L.", 400.0, due=date(2026, 1, 20))
    line = _line(1, date(2026, 1, 18), "PAGO FRA INV-1", -150.0)

    decision = decide_bank_line(line, [ob])

    assert decision.category == "partial"
    assert decision.applied is True
    assert ob.amount_paid == 150.0
    assert ob.amount_outstanding == 250.0


def test_two_payments_settle_one_invoice():
    ob = _obligation("INV-1", "Some Supplier S.L.", 400.0, due=date(2026, 1, 20))
    lines = [
        _line(1, date(2026, 1, 10), "PAGO FRA INV-1", -150.0),
        _line(2, date(2026, 1, 18), "PAGO FRA INV-1", -250.0),
    ]

    decisions = reconcile(lines, [ob])

    assert [d.category for d in decisions] == ["partial", "auto"]
    assert ob.amount_paid == 400.0
    assert ob.status == "paid"


# --- one payment covering several invoices ----------------------------------


def test_one_payment_covers_two_invoices():
    ob1 = _obligation("INV-1", "Some Supplier S.L.", 100.0, due=date(2026, 1, 20))
    ob2 = _obligation("INV-2", "Some Supplier S.L.", 50.0, due=date(2026, 1, 25))
    # No invoice number in the text, but it names the supplier and the
    # amount is exactly the sum of both open invoices.
    line = _line(1, date(2026, 1, 20), "SOME SUPPLIER SL TRANSFER", -150.0)

    decision = decide_bank_line(line, [ob1, ob2])

    assert decision.category == "combo"
    assert decision.applied is True
    assert set(decision.invoice_numbers) == {"INV-1", "INV-2"}
    assert ob1.status == "paid"
    assert ob2.status == "paid"


# --- duplicate use of a bank line prevented ---------------------------------


def test_one_bank_line_only_ever_pays_the_winning_candidate():
    # Two different suppliers that happen to owe the exact same amount;
    # only one reference number, so only one should ever get paid.
    ob1 = _obligation("INV-1", "Correct Supplier", 100.0, due=date(2026, 1, 20))
    ob2 = _obligation("INV-2", "Other Supplier", 100.0, due=date(2026, 1, 20))
    line = _line(1, date(2026, 1, 18), "PAGO FRA INV-1", -100.0)

    decision = decide_bank_line(line, [ob1, ob2])

    assert decision.invoice_numbers == ["INV-1"]
    assert ob1.amount_paid == 100.0
    assert ob2.amount_paid == 0.0


# --- ambiguous ---------------------------------------------------------------


def test_two_equally_good_candidates_are_ambiguous_not_guessed():
    # Same amount, same (absent) reference, same weak-but-equal name
    # signal, same date plausibility - nothing to tell them apart.
    ob1 = _obligation("INV-1", "Acme Corp", 100.0, issue=date(2026, 1, 1), due=date(2026, 1, 20))
    ob2 = _obligation("INV-2", "Acme Corp", 100.0, issue=date(2026, 1, 1), due=date(2026, 1, 20))
    line = _line(1, date(2026, 1, 18), "ACME CORP PAYMENT", -100.0)

    decision = decide_bank_line(line, [ob1, ob2])

    assert decision.category == "ambiguous"
    assert decision.applied is False
    assert ob1.amount_paid == 0.0
    assert ob2.amount_paid == 0.0


# --- same amount alone is not enough ----------------------------------------


def test_same_amount_with_disagreeing_name_and_no_reference_never_auto_matches():
    ob = _obligation("INV-1", "Totally Different Company", 100.0, due=date(2026, 1, 20))
    line = _line(1, date(2026, 1, 18), "SOME UNRELATED PAYEE TEXT", -100.0)

    decision = decide_bank_line(line, [ob])

    assert decision.category != "auto"
    assert decision.applied is False
