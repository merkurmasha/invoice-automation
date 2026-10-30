"""Turns the output of match.reconcile() into the things a human needs
to look at - every row has a plain-English reason, per CLAUDE.md.

Five lists, each its own category in one combined CSV:

  - unmatched_bank_line:    a bank line that explains nothing in either
                             ledger (match.MatchDecision category "unmatched").
  - ambiguous:               a bank line with two equally good candidates
                             - never guessed, always needs a human.
  - possible_match:          a bank line that pointed at one invoice, but
                             not confidently enough to apply automatically.
  - no_payment_not_yet_due / no_payment_overdue:
                             an invoice that has never received a cent,
                             split by whether `today` is past its due date.
  - partial_payment_balance: an invoice that's been paid some, but not
                             all, of its total - shows the remaining
                             balance.

A sixth, informational-only category (combo_payment) is included too:
one bank line that turned out to be several invoices paid at once is
still worth a human's attention, even though match.py applied it
confidently - this isn't one of CLAUDE.md's required lists, just extra
visibility that doesn't cost anything to add.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .ledger import Obligation
from .match import MatchDecision

UNMATCHED_BANK_LINE = "unmatched_bank_line"
AMBIGUOUS = "ambiguous"
POSSIBLE_MATCH = "possible_match"
NO_PAYMENT_NOT_YET_DUE = "no_payment_not_yet_due"
NO_PAYMENT_OVERDUE = "no_payment_overdue"
PARTIAL_PAYMENT_BALANCE = "partial_payment_balance"
COMBO_PAYMENT = "combo_payment"

FIELDNAMES = [
    "category",
    "date",
    "invoice_numbers",
    "counterparty",
    "currency",
    "amount",
    "outstanding",
    "reason",
]


@dataclass(frozen=True)
class ExceptionRow:
    category: str
    date: date | None
    invoice_numbers: list[str]
    counterparty: str
    currency: str
    amount: float | None
    outstanding: float | None
    reason: str

    def to_row(self) -> dict:
        return {
            "category": self.category,
            "date": self.date.isoformat() if self.date else "",
            "invoice_numbers": "|".join(self.invoice_numbers),
            "counterparty": self.counterparty,
            "currency": self.currency,
            "amount": f"{self.amount:.2f}" if self.amount is not None else "",
            "outstanding": f"{self.outstanding:.2f}" if self.outstanding is not None else "",
            "reason": self.reason,
        }


def _decision_rows(decisions: list[MatchDecision]) -> list[ExceptionRow]:
    rows: list[ExceptionRow] = []
    for decision in decisions:
        line = decision.bank_line
        if decision.category == "unmatched":
            category = UNMATCHED_BANK_LINE
        elif decision.category == "ambiguous":
            category = AMBIGUOUS
        elif decision.category == "possible":
            category = POSSIBLE_MATCH
        elif decision.category == "combo":
            category = COMBO_PAYMENT
        else:
            # "auto" and "partial" bank-line decisions are represented by
            # the obligation-level rows below instead (partial shows the
            # invoice's remaining balance; auto needs no exception at all).
            continue

        rows.append(
            ExceptionRow(
                category=category,
                date=line.txn_date,
                invoice_numbers=decision.invoice_numbers,
                counterparty=line.description,
                currency="EUR",
                amount=line.amount,
                outstanding=None,
                reason=decision.reason,
            )
        )
    return rows


def _obligation_rows(obligations: list[Obligation], today: date) -> list[ExceptionRow]:
    rows: list[ExceptionRow] = []
    for ob in obligations:
        if ob.amount_paid <= 0:
            if ob.due_date is None:
                rows.append(
                    ExceptionRow(
                        category=NO_PAYMENT_NOT_YET_DUE,
                        date=None,
                        invoice_numbers=[ob.invoice_number],
                        counterparty=ob.counterparty,
                        currency=ob.currency,
                        amount=ob.total,
                        outstanding=ob.amount_outstanding,
                        reason="No due date on file, so overdue status can't be determined - treating as not yet due.",
                    )
                )
            elif ob.due_date >= today:
                days = (ob.due_date - today).days
                rows.append(
                    ExceptionRow(
                        category=NO_PAYMENT_NOT_YET_DUE,
                        date=ob.due_date,
                        invoice_numbers=[ob.invoice_number],
                        counterparty=ob.counterparty,
                        currency=ob.currency,
                        amount=ob.total,
                        outstanding=ob.amount_outstanding,
                        reason=f"No payment seen yet; due in {days} day(s).",
                    )
                )
            else:
                days = (today - ob.due_date).days
                rows.append(
                    ExceptionRow(
                        category=NO_PAYMENT_OVERDUE,
                        date=ob.due_date,
                        invoice_numbers=[ob.invoice_number],
                        counterparty=ob.counterparty,
                        currency=ob.currency,
                        amount=ob.total,
                        outstanding=ob.amount_outstanding,
                        reason=f"No payment seen; {days} day(s) overdue as of {today.isoformat()}.",
                    )
                )
        elif ob.amount_outstanding > 0:
            rows.append(
                ExceptionRow(
                    category=PARTIAL_PAYMENT_BALANCE,
                    date=ob.due_date,
                    invoice_numbers=[ob.invoice_number],
                    counterparty=ob.counterparty,
                    currency=ob.currency,
                    amount=ob.total,
                    outstanding=ob.amount_outstanding,
                    reason=(
                        f"Paid {ob.amount_paid:.2f} of {ob.total:.2f}; "
                        f"{ob.amount_outstanding:.2f} still outstanding."
                    ),
                )
            )
    return rows


def build_exceptions(
    decisions: list[MatchDecision],
    obligations: list[Obligation],
    today: date,
) -> list[ExceptionRow]:
    """Builds the full exceptions list. Must be called AFTER
    match.reconcile() has run (so obligations reflect applied payments)."""
    return _decision_rows(decisions) + _obligation_rows(obligations, today)


def write_exceptions_csv(rows: list[ExceptionRow], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_row())
