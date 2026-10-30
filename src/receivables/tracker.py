"""Tracks the status of outgoing sales invoices: how much of each one
has been paid, and how much is still outstanding.

This is plain deterministic code per CLAUDE.md — no LLM involved.
sales_invoices.csv (data/synthetic/sales_invoices.csv) has these
columns: invoice_number, customer_name, issue_date, due_date, currency,
net, vat, total. It has no payment or status columns, so every invoice
loaded from it starts out "open" with nothing paid — payments are
applied afterwards with mark_payment(), in memory, on a copy of the
data. Loading never writes back to the committed CSV.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

STATUS_OPEN = "open"
STATUS_PARTIALLY_PAID = "partially_paid"
STATUS_PAID = "paid"


class UnknownInvoiceError(KeyError):
    """Raised when mark_payment() is given an invoice_id that isn't tracked."""


@dataclass
class Invoice:
    invoice_number: str
    customer_name: str
    issue_date: date
    due_date: date
    currency: str
    net: float
    vat: float
    total: float
    amount_paid: float = 0.0
    status: str = STATUS_OPEN
    # Only set when the tracker has a language column for this invoice;
    # the drafter falls back to English when it's None.
    language: str | None = None

    @property
    def amount_outstanding(self) -> float:
        # Clamped at zero: a payment that exceeds the total is recorded
        # in full in amount_paid (see OverpaymentFlag), but "outstanding"
        # should never read as negative.
        return round(max(self.total - self.amount_paid, 0.0), 2)


@dataclass
class OverpaymentFlag:
    """Recorded instead of silently accepting a payment that exceeds
    the invoice total — a human should look at these."""

    invoice_id: str
    amount_paid_total: float
    invoice_total: float
    overpaid_by: float
    date: date


@dataclass
class ReceivablesTracker:
    invoices: dict[str, Invoice] = field(default_factory=dict)
    overpayment_flags: list[OverpaymentFlag] = field(default_factory=list)

    @classmethod
    def from_csv(cls, path: str | Path) -> "ReceivablesTracker":
        """Load invoices from a sales-invoices CSV. This only reads the
        file — it never writes to it, so the committed synthetic file
        is always safe to reload from."""
        tracker = cls()
        with Path(path).open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                invoice = Invoice(
                    invoice_number=row["invoice_number"],
                    customer_name=row["customer_name"],
                    issue_date=date.fromisoformat(row["issue_date"]),
                    due_date=date.fromisoformat(row["due_date"]),
                    currency=row["currency"],
                    net=float(row["net"]),
                    vat=float(row["vat"]),
                    total=float(row["total"]),
                    language=row.get("language") or None,
                )
                tracker.invoices[invoice.invoice_number] = invoice
        return tracker

    def mark_payment(self, invoice_id: str, amount: float, on_date: date) -> Invoice:
        """Apply a payment to an invoice and update its status.

        Overpayments are never silently accepted: if the running total
        paid exceeds the invoice total, an OverpaymentFlag is recorded
        in self.overpayment_flags for a human to review, but the
        payment is still applied (amount_paid keeps the true total
        paid) rather than rejected outright.
        """
        try:
            invoice = self.invoices[invoice_id]
        except KeyError:
            raise UnknownInvoiceError(f"No tracked invoice with id {invoice_id!r}") from None

        invoice.amount_paid = round(invoice.amount_paid + amount, 2)

        if invoice.amount_paid > invoice.total:
            self.overpayment_flags.append(
                OverpaymentFlag(
                    invoice_id=invoice_id,
                    amount_paid_total=invoice.amount_paid,
                    invoice_total=invoice.total,
                    overpaid_by=round(invoice.amount_paid - invoice.total, 2),
                    date=on_date,
                )
            )

        if invoice.amount_paid <= 0:
            invoice.status = STATUS_OPEN
        elif invoice.amount_paid >= invoice.total:
            invoice.status = STATUS_PAID
        else:
            invoice.status = STATUS_PARTIALLY_PAID

        return invoice
