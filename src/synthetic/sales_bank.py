"""Generates the two CSVs that sit on the "money owed" side of the pipeline:

- data/synthetic/sales_invoices.csv - invoices Costa Brava Studio issued
  to its own customers, spread across the aging buckets used later by the
  receivables phase (current / 1-30 / 31-60 / 60+ days overdue, measured
  against 2026-10-28).
- data/synthetic/bank/statement.csv - a bank export that partially
  reconciles against both the supplier invoices (jobs.py) and the sales
  invoices below: some payments match cleanly, some are missing, two are
  partial, one matches nothing, and several have messy reference text.
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from src.synthetic.jobs import InvoiceJob

SEED = 777
AS_OF = date(2026, 10, 28)
STARTING_BALANCE = 12000.00

CUSTOMERS = [
    "Taverna del Call, S.L.",
    "Hotel Vista Mar, S.A.",
    "Marc Fuster Arquitectes",
    "Clínica Dental Girona",
    "Llibreria Horitzons",
    "Restaurant Can Pla",
    "Botiga Natura Barcelona",
    "Estudi Fotogràfic Lux",
    "Perruqueria Nova Imatge",
    "Fundació Art Jove",
    "Immobiliària Costa Clara",
    "Escola d'Idiomes Babel",
]

# (due_date, paid "status") - current / 1-30 / 31-60 / 60+ overdue vs AS_OF.
SALES_PLAN = [
    (date(2026, 11, 5), "unpaid"),
    (date(2026, 11, 15), "unpaid"),
    (date(2026, 10, 30), "unpaid"),
    (date(2026, 10, 5), "paid"),
    (date(2026, 10, 12), "partial"),
    (date(2026, 10, 20), "unpaid"),
    (date(2026, 9, 1), "paid_late"),
    (date(2026, 9, 10), "unpaid"),
    (date(2026, 9, 20), "unpaid"),
    (date(2026, 7, 15), "paid_late"),
    (date(2026, 8, 1), "unpaid"),
    (date(2026, 8, 20), "unpaid"),
]


@dataclass
class SalesInvoice:
    invoice_number: str
    customer_name: str
    issue_date: date
    due_date: date
    currency: str
    net: float
    vat: float
    total: float
    paid_status: str
    paid_amount: float


@dataclass
class BankLine:
    txn_date: date
    description: str
    amount: float
    balance: float = 0.0


def _round(x: float) -> float:
    return round(x, 2)


def build_sales_invoices() -> list[SalesInvoice]:
    rng = random.Random(SEED)
    invoices: list[SalesInvoice] = []
    for i, ((due_date, status), customer) in enumerate(zip(SALES_PLAN, CUSTOMERS), start=1):
        issue_date = due_date - timedelta(days=30)
        net = _round(rng.uniform(900, 3200))
        vat = _round(net * 0.21)
        total = _round(net + vat)
        if status == "partial":
            paid_amount = _round(total * rng.uniform(0.4, 0.7))
        elif status in ("paid", "paid_late"):
            paid_amount = total
        else:
            paid_amount = 0.0
        invoices.append(
            SalesInvoice(
                invoice_number=f"CBS-2026-{i:04d}",
                customer_name=customer,
                issue_date=issue_date,
                due_date=due_date,
                currency="EUR",
                net=net,
                vat=vat,
                total=total,
                paid_status=status,
                paid_amount=paid_amount,
            )
        )
    return invoices


def write_sales_invoices_csv(invoices: list[SalesInvoice], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["invoice_number", "customer_name", "issue_date", "due_date", "currency", "net", "vat", "total"]
        )
        for inv in invoices:
            writer.writerow(
                [
                    inv.invoice_number,
                    inv.customer_name,
                    inv.issue_date.isoformat(),
                    inv.due_date.isoformat(),
                    inv.currency,
                    f"{inv.net:.2f}",
                    f"{inv.vat:.2f}",
                    f"{inv.total:.2f}",
                ]
            )


# Supplier invoices we deliberately do NOT pay, so the reconciliation
# phase has real gaps to find (foreign-currency ones are skipped because
# converting USD/GBP to the EUR bank account is out of scope for phase 1).
UNPAID_SUPPLIER_STEMS = {
    "figma_2026-07-12",
    "figma_2026-09-12",
    "pixelco_2026-09-25",
    "officesupplies_2026-10-02",
    "travel_2026-10-20",
}
PARTIAL_SUPPLIER_PAYMENTS = {
    "freelancer_2026-07-20": 300.00,
    "printer_2026-08-18": 150.00,
}

SUPPLIER_REFERENCE_STYLES = [
    lambda job: f"{job.supplier_canonical.upper()} {job.invoice_number}",
    lambda job: f"PAGO FRA {job.invoice_number}",
    lambda job: f"{job.supplier_canonical[:10].upper()} FACT",
    lambda job: f"TRANSFERENCIA {job.supplier_canonical.split(',')[0].split(' ')[0].upper()}",
    lambda job: job.invoice_number,
]


def _payment_date(job: InvoiceJob, rng: random.Random) -> date:
    auto_charge = {"notion", "adobe", "figma", "nordic", "studiofonts", "cloudhost"}
    if job.supplier_id in auto_charge:
        return job.issue_date
    if job.due_date is not None:
        return job.due_date - timedelta(days=rng.randint(0, 3))
    return job.issue_date + timedelta(days=rng.randint(5, 15))


def build_bank_lines(supplier_jobs: list[InvoiceJob], sales_invoices: list[SalesInvoice]) -> list[BankLine]:
    rng = random.Random(SEED + 1)
    lines: list[BankLine] = []

    # One payment per *unique* supplier invoice number - the duplicate
    # and near-duplicate files represent the same real-world obligation,
    # so they must not generate two bank lines each.
    seen_invoice_keys: set[tuple[str, str]] = set()
    for job in supplier_jobs:
        if job.document_type == "credit_note":
            continue
        key = (job.supplier_id, job.invoice_number)
        if key in seen_invoice_keys:
            continue
        seen_invoice_keys.add(key)
        if job.file_stem in UNPAID_SUPPLIER_STEMS:
            continue
        amount = -job.printed_total
        if job.file_stem in PARTIAL_SUPPLIER_PAYMENTS:
            amount = -PARTIAL_SUPPLIER_PAYMENTS[job.file_stem]
        ref_style = SUPPLIER_REFERENCE_STYLES[rng.randrange(len(SUPPLIER_REFERENCE_STYLES))]
        lines.append(BankLine(_payment_date(job, rng), ref_style(job), _round(amount)))

    customer_ref_styles = [
        lambda inv: f"REBUT {inv.customer_name.upper()} {inv.invoice_number}",
        lambda inv: f"TRANSFERENCIA {inv.customer_name.split(',')[0].split(' ')[0].upper()}",
        lambda inv: f"COBRAMENT {inv.invoice_number}",
        lambda inv: inv.customer_name.upper(),
    ]
    for inv in sales_invoices:
        if inv.paid_amount <= 0:
            continue
        pay_date = inv.due_date if inv.paid_status == "paid" else inv.due_date + timedelta(days=rng.randint(3, 25))
        ref_style = customer_ref_styles[rng.randrange(len(customer_ref_styles))]
        lines.append(BankLine(pay_date, ref_style(inv), _round(inv.paid_amount)))

    # One line that matches nothing in either ledger.
    lines.append(BankLine(date(2026, 9, 30), "COMISSIONS BANCARIES TRIMESTRALS", -12.50))

    lines.sort(key=lambda bl: bl.txn_date)
    balance = STARTING_BALANCE
    for bl in lines:
        balance = _round(balance + bl.amount)
        bl.balance = balance
    return lines


def write_bank_csv(lines: list[BankLine], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "description", "amount", "balance"])
        for bl in lines:
            writer.writerow([bl.txn_date.isoformat(), bl.description, f"{bl.amount:.2f}", f"{bl.balance:.2f}"])
