"""Loads the two sets of invoices a bank line can be paying:

- "payable" obligations: supplier invoices Costa Brava Studio owes
  money on, loaded from data/synthetic/answer_key.json (the synthetic
  demo's stand-in for a validated extraction ledger - see CLAUDE.md on
  using synthetic data, and the chart_of_accounts.yaml comment on why
  category/canonical-name come from the answer key here).
- "receivable" obligations: sales invoices Costa Brava Studio issued to
  its own customers, loaded from data/synthetic/sales_invoices.csv.

Both become the same simple Obligation shape so match.py only has to
know how to score one kind of thing, regardless of which ledger it came
from. This module only reads files - nothing here ever writes to
the committed synthetic data.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PAYABLE = "payable"
RECEIVABLE = "receivable"

STATUS_OPEN = "open"
STATUS_PARTIALLY_PAID = "partially_paid"
STATUS_PAID = "paid"

# document_type values in the answer key that represent money actually
# owed to a supplier. Credit notes adjust a future invoice rather than
# being something a bank payment settles on its own, so they're never
# loaded as a payable obligation here (the synthetic generator never
# creates a bank line for one either - see src/synthetic/sales_bank.py).
_PAYABLE_DOCUMENT_TYPES = {"invoice"}


@dataclass
class Obligation:
    kind: str  # PAYABLE or RECEIVABLE
    invoice_number: str
    counterparty: str
    issue_date: date
    due_date: date | None
    currency: str
    total: float
    category: str | None = None
    amount_paid: float = 0.0
    # One entry per payment applied to this obligation, in the order
    # applied: (bank_line_id, payment_date, amount). Lets exceptions.py
    # explain *why* an invoice is paid/partial, and lets the reconcile
    # CLI replay each payment onto the real receivables tracker via its
    # mark_payment() (see src/reconcile/run.py) without re-deriving dates.
    payment_events: list[tuple[int, date, float]] = field(default_factory=list)

    @property
    def amount_outstanding(self) -> float:
        return round(max(self.total - self.amount_paid, 0.0), 2)

    @property
    def status(self) -> str:
        if self.amount_paid <= 0:
            return STATUS_OPEN
        if self.amount_outstanding <= 0:
            return STATUS_PAID
        return STATUS_PARTIALLY_PAID

    def apply_payment(self, amount: float, bank_line_id: int, on_date: date) -> None:
        self.amount_paid = round(self.amount_paid + amount, 2)
        self.payment_events.append((bank_line_id, on_date, round(amount, 2)))


def load_payable_obligations(path: str | Path) -> list[Obligation]:
    """Load supplier invoices from an answer-key-shaped JSON file.

    Several answer-key entries describe the same real invoice twice
    (a PDF and a photo of it, or the generator's deliberate
    duplicate/near-duplicate traps) - only the first entry seen for a
    given invoice_number is kept, exactly as the real pipeline's
    duplicate detector would (src/validate/duplicates.py): a bad
    near-duplicate reading never gets its own obligation.
    """
    entries = json.loads(Path(path).read_text())
    obligations: list[Obligation] = []
    seen_invoice_numbers: set[str] = set()

    for entry in entries:
        if entry.get("document_type") not in _PAYABLE_DOCUMENT_TYPES:
            continue
        invoice_number = entry["invoice_number"]
        if invoice_number in seen_invoice_numbers:
            continue
        seen_invoice_numbers.add(invoice_number)

        due_date_str = entry.get("due_date")
        obligations.append(
            Obligation(
                kind=PAYABLE,
                invoice_number=invoice_number,
                counterparty=entry["supplier"],
                issue_date=date.fromisoformat(entry["issue_date"]),
                due_date=date.fromisoformat(due_date_str) if due_date_str else None,
                currency=entry["currency"],
                total=float(entry["total"]),
                category=entry.get("expected_category"),
            )
        )
    return obligations


def load_receivable_obligations(path: str | Path) -> list[Obligation]:
    """Load Costa Brava Studio's own sales invoices from sales_invoices.csv."""
    obligations: list[Obligation] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            obligations.append(
                Obligation(
                    kind=RECEIVABLE,
                    invoice_number=row["invoice_number"],
                    counterparty=row["customer_name"],
                    issue_date=date.fromisoformat(row["issue_date"]),
                    due_date=date.fromisoformat(row["due_date"]),
                    currency=row["currency"],
                    total=float(row["total"]),
                )
            )
    return obligations


def load_credit_notes(path: str | Path) -> list[dict]:
    """Credit notes aren't obligations to match against the bank (see
    _PAYABLE_DOCUMENT_TYPES above) but the accountant pack's ledger
    still needs them, with their sign kept negative. Returns the raw
    answer-key entries for every document_type == "credit_note"."""
    entries = json.loads(Path(path).read_text())
    return [entry for entry in entries if entry.get("document_type") == "credit_note"]
