"""Builds the month-end accountant pack:

    python -m src.pack.build --month 2026-09 --out data/packs/

Creates data/packs/<month>/ containing:
  - ledger.csv:      every supplier invoice issued that month
  - documents/:      copies of that month's source files, renamed and
                      sorted into per-supplier folders
  - exceptions.csv:  this month's reconciliation exceptions
  - summary.md:      one human-readable page

Plain deterministic code per CLAUDE.md - no LLM call anywhere in this
module. Everything it needs is either already-synthetic ground truth
(the answer key's category/canonical-name values - this is a demo, not
real bookkeeping, and summary.md says so) or the real validate.py and
reconcile.py modules, reused as-is.

Reproducibility: running this twice with the same --month produces
byte-identical ledger.csv/exceptions.csv/summary.md (deterministic
iteration order, deterministic float formatting, no timestamps in the
content) - see tests/test_pack_build.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.extract.schema import DocumentType, ExtractedInvoice, FieldConfidence
from src.receivables import aging
from src.receivables.tracker import ReceivablesTracker
from src.reconcile import config as reconcile_config
from src.reconcile import exceptions as exceptions_module
from src.reconcile import ledger, match
from src.validate.duplicates import DuplicateDetector
from src.validate.validate import validate_invoice

from . import config

LEDGER_FIELDNAMES = [
    "date",
    "supplier",
    "invoice_number",
    "currency",
    "net",
    "vat",
    "total",
    "category",
    "validation_status",
    "paid_status",
]


@dataclass(frozen=True)
class LedgerRow:
    issue_date: date
    supplier: str
    invoice_number: str
    currency: str
    net: float
    vat: float
    total: float
    category: str
    validation_status: str
    paid_status: str
    source_file: str | None  # answer-key "file" field, for documents/

    def to_row(self) -> dict:
        return {
            "date": self.issue_date.isoformat(),
            "supplier": self.supplier,
            "invoice_number": self.invoice_number,
            "currency": self.currency,
            "net": f"{self.net:.2f}",
            "vat": f"{self.vat:.2f}",
            "total": f"{self.total:.2f}",
            "category": self.category,
            "validation_status": self.validation_status,
            "paid_status": self.paid_status,
        }


def _confidence() -> FieldConfidence:
    c = config.SYNTHETIC_CONFIDENCE
    return FieldConfidence(
        supplier=c, invoice_number=c, issue_date=c, due_date=c, currency=c,
        net=c, vat=c, total=c, document_type=c, language=c,
    )


def _to_extracted(entry: dict) -> ExtractedInvoice:
    due_date_str = entry.get("due_date")
    return ExtractedInvoice(
        supplier=entry["supplier"],
        invoice_number=entry["invoice_number"],
        issue_date=date.fromisoformat(entry["issue_date"]),
        due_date=date.fromisoformat(due_date_str) if due_date_str else None,
        currency=entry["currency"],
        net=float(entry["net"]),
        vat=float(entry["vat"]),
        total=float(entry["total"]),
        document_type=DocumentType(entry["document_type"]),
        language=entry.get("language"),
        confidence=_confidence(),
    )


def validation_statuses(answer_key_entries: list[dict]) -> dict[str, str]:
    """Runs every answer-key entry, IN ORDER, through the real
    src.validate.validate.validate_invoice() against a fresh, in-memory
    DuplicateDetector (never the committed cache) - exactly how the
    real pipeline would see them arrive one at a time. Returns
    invoice_number -> "pass"/"review" for the FIRST entry seen for each
    invoice_number, matching the same first-entry-wins dedup rule
    src.reconcile.ledger uses, so a bad near-duplicate reading never
    taints the ledger row for the real invoice."""
    with tempfile.TemporaryDirectory(prefix="pack_duplicates_") as tmp_dir:
        detector = DuplicateDetector(cache_path=Path(tmp_dir) / "seen_invoices.json")
        statuses: dict[str, str] = {}
        for entry in answer_key_entries:
            extracted = _to_extracted(entry)
            result = validate_invoice(extracted, detector, today=date.fromisoformat(config.DEFAULT_TODAY))
            statuses.setdefault(entry["invoice_number"], result.status)
        return statuses


def _month_matches(d: date, month: str) -> bool:
    return f"{d.year:04d}-{d.month:02d}" == month


def build_ledger_rows(
    answer_key_entries: list[dict],
    month: str,
    statuses: dict[str, str],
    obligations_by_invoice: dict[str, ledger.Obligation],
) -> list[LedgerRow]:
    """One row per invoice issued in `month` - payable invoices AND
    credit notes (credit notes keep their negative sign, and are never
    reconciliation obligations - see ledger.py). Deduped the same way
    ledger.load_payable_obligations() is: first entry wins per
    invoice_number, so a duplicate/near-duplicate reading never
    produces a second row."""
    rows: list[LedgerRow] = []
    seen: set[str] = set()
    for entry in answer_key_entries:
        invoice_number = entry["invoice_number"]
        if invoice_number in seen:
            continue
        issue_date = date.fromisoformat(entry["issue_date"])
        if not _month_matches(issue_date, month):
            continue
        seen.add(invoice_number)

        document_type = entry.get("document_type")
        if document_type == "credit_note":
            paid_status = "credit_note"
        else:
            obligation = obligations_by_invoice.get(invoice_number)
            paid_status = obligation.status if obligation is not None else "open"

        rows.append(
            LedgerRow(
                issue_date=issue_date,
                supplier=entry["supplier"],
                invoice_number=invoice_number,
                currency=entry["currency"],
                net=float(entry["net"]),
                vat=float(entry["vat"]),
                total=float(entry["total"]),
                category=entry["expected_category"],
                validation_status=statuses.get(invoice_number, "review"),
                paid_status=paid_status,
                source_file=entry.get("file"),
            )
        )
    rows.sort(key=lambda r: (r.issue_date.isoformat(), r.invoice_number))
    return rows


def write_ledger_csv(rows: list[LedgerRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_row())


def _safe_name(text: str) -> str:
    keep = "".join(ch if ch.isalnum() else "_" for ch in text)
    while "__" in keep:
        keep = keep.replace("__", "_")
    return keep.strip("_")


def copy_documents(rows: list[LedgerRow], documents_dir: Path) -> list[Path]:
    """Copies the source file for each ledger row into
    documents/<Supplier>/<date>_<Supplier>_<InvoiceNo>.<ext>. Rows with
    no source file on record (shouldn't happen for this synthetic
    dataset, but checked rather than assumed) are skipped. Returns the
    paths written, sorted, so callers can report them deterministically."""
    written: list[Path] = []
    for row in rows:
        if not row.source_file:
            continue
        source_path = config.DOCUMENTS_ROOT / row.source_file
        if not source_path.exists():
            continue
        supplier_dir = documents_dir / _safe_name(row.supplier)
        supplier_dir.mkdir(parents=True, exist_ok=True)
        ext = source_path.suffix
        dest_name = f"{row.issue_date.isoformat()}_{_safe_name(row.supplier)}_{_safe_name(row.invoice_number)}{ext}"
        dest_path = supplier_dir / dest_name
        shutil.copyfile(source_path, dest_path)
        written.append(dest_path)
    return sorted(written)


def build_summary_md(
    month: str,
    rows: list[LedgerRow],
    exception_rows: list[exceptions_module.ExceptionRow],
    aging_summary: dict[str, dict[str, float]],
) -> str:
    totals_by_currency: dict[str, float] = {}
    vat_by_currency: dict[str, float] = {}
    category_totals: dict[tuple[str, str], float] = {}  # (category, currency) -> total

    for row in rows:
        totals_by_currency[row.currency] = round(totals_by_currency.get(row.currency, 0.0) + row.total, 2)
        vat_by_currency[row.currency] = round(vat_by_currency.get(row.currency, 0.0) + row.vat, 2)
        key = (row.category, row.currency)
        category_totals[key] = round(category_totals.get(key, 0.0) + row.total, 2)

    review_count = sum(1 for row in rows if row.validation_status == "review")

    lines: list[str] = []
    lines.append(f"# Accountant pack - {month}")
    lines.append("")
    lines.append(
        "*Demo data for a fictional company (Costa Brava Studio S.L.). "
        "Category and supplier names come from the synthetic dataset's "
        "answer key, not a real categorisation run - see CLAUDE.md.*"
    )
    lines.append("")

    lines.append("## Totals by currency")
    lines.append("")
    lines.append("Never added together across currencies - see the per-currency rows below.")
    lines.append("")
    lines.append("| Currency | Total (net+vat, credit notes negative) | VAT |")
    lines.append("| --- | --- | --- |")
    for currency in sorted(totals_by_currency):
        lines.append(f"| {currency} | {totals_by_currency[currency]:.2f} | {vat_by_currency[currency]:.2f} |")
    lines.append("")

    lines.append("## Top categories")
    lines.append("")
    lines.append("| Category | Currency | Total |")
    lines.append("| --- | --- | --- |")
    for (category, currency), total in sorted(category_totals.items(), key=lambda kv: (-abs(kv[1]), kv[0])):
        lines.append(f"| {category} | {currency} | {total:.2f} |")
    lines.append("")

    lines.append("## Items needing review")
    lines.append("")
    lines.append(f"- {review_count} invoice(s) this month failed validation (see `validation_status` in ledger.csv).")
    lines.append(f"- {len(exception_rows)} reconciliation exception(s) this month (see exceptions.csv).")
    lines.append("")

    lines.append("## Overdue receivables (whole book, not just this month)")
    lines.append("")
    lines.append("| Bucket | Count | Outstanding (EUR) |")
    lines.append("| --- | --- | --- |")
    for bucket in aging.BUCKETS:
        row = aging_summary[bucket]
        lines.append(f"| {bucket} | {row['count']} | {row['outstanding']:.2f} |")
    lines.append("")

    lines.append("## Needs your attention")
    lines.append("")
    attention: list[str] = []
    if review_count:
        attention.append(f"{review_count} invoice(s) this month need a validation review.")
    unmatched = sum(1 for r in exception_rows if r.category == exceptions_module.UNMATCHED_BANK_LINE)
    ambiguous = sum(1 for r in exception_rows if r.category == exceptions_module.AMBIGUOUS)
    if unmatched:
        attention.append(f"{unmatched} unmatched bank line(s) this month.")
    if ambiguous:
        attention.append(f"{ambiguous} ambiguous bank line(s) this month - pick the right invoice by hand.")
    overdue_60 = aging_summary[aging.BUCKET_60_PLUS]
    if overdue_60["count"]:
        attention.append(
            f"{overdue_60['count']} receivable(s) are 60+ days overdue, {overdue_60['outstanding']:.2f} EUR outstanding."
        )
    if not attention:
        attention.append("Nothing urgent this month.")
    for item in attention:
        lines.append(f"- {item}")
    lines.append("")

    return "\n".join(lines)


_OBLIGATION_CATEGORIES = {
    exceptions_module.NO_PAYMENT_NOT_YET_DUE,
    exceptions_module.NO_PAYMENT_OVERDUE,
    exceptions_module.PARTIAL_PAYMENT_BALANCE,
}


def _filter_exceptions_to_month(
    rows: list[exceptions_module.ExceptionRow],
    month: str,
    obligations_by_invoice: dict[str, ledger.Obligation],
) -> list[exceptions_module.ExceptionRow]:
    """Bank-line exceptions (unmatched/ambiguous/possible/combo) belong
    to the month their bank transaction happened in. Obligation
    exceptions (no payment / partial balance) belong to the month the
    invoice was ISSUED in, same as ledger.csv - not the month of its
    due date, so an exception row for one of this month's invoices
    always shows up in this month's pack even if that invoice isn't
    due until later."""
    filtered: list[exceptions_module.ExceptionRow] = []
    for row in rows:
        if row.category in _OBLIGATION_CATEGORIES:
            obligation = obligations_by_invoice.get(row.invoice_numbers[0]) if row.invoice_numbers else None
            if obligation is not None and _month_matches(obligation.issue_date, month):
                filtered.append(row)
        elif row.date is not None and _month_matches(row.date, month):
            filtered.append(row)
    return filtered


def build_pack(month: str, out_dir: Path, today: date) -> Path:
    answer_key_entries: list[dict] = json.loads(reconcile_config.ANSWER_KEY_PATH.read_text())

    bank_lines = match.load_bank_statement(reconcile_config.BANK_STATEMENT_PATH)
    payables = ledger.load_payable_obligations(reconcile_config.ANSWER_KEY_PATH)
    receivables = ledger.load_receivable_obligations(reconcile_config.SALES_INVOICES_PATH)
    obligations = payables + receivables
    decisions = match.reconcile(bank_lines, obligations)
    obligations_by_invoice = {ob.invoice_number: ob for ob in obligations}

    statuses = validation_statuses(answer_key_entries)
    rows = build_ledger_rows(answer_key_entries, month, statuses, obligations_by_invoice)

    all_exceptions = exceptions_module.build_exceptions(decisions, obligations, today)
    month_exceptions = _filter_exceptions_to_month(all_exceptions, month, obligations_by_invoice)

    tracker = ReceivablesTracker.from_csv(reconcile_config.SALES_INVOICES_PATH)
    for ob in receivables:
        for _bank_line_id, pay_date, amount in ob.payment_events:
            tracker.mark_payment(ob.invoice_number, amount, pay_date)
    aging_summary = aging.aging_summary(tracker, today)

    pack_dir = out_dir / month
    pack_dir.mkdir(parents=True, exist_ok=True)

    write_ledger_csv(rows, pack_dir / "ledger.csv")
    copy_documents(rows, pack_dir / "documents")
    exceptions_module.write_exceptions_csv(month_exceptions, pack_dir / "exceptions.csv")
    summary_text = build_summary_md(month, rows, month_exceptions, aging_summary)
    (pack_dir / "summary.md").write_text(summary_text)

    return pack_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the month-end accountant pack.")
    parser.add_argument("--month", required=True, help="YYYY-MM, e.g. 2026-09")
    parser.add_argument("--out", required=True, help="Output directory, e.g. data/packs/")
    parser.add_argument("--today", default=config.DEFAULT_TODAY, help="ISO date for aging/overdue sections")
    args = parser.parse_args(argv)

    pack_dir = build_pack(args.month, Path(args.out), date.fromisoformat(args.today))
    print(f"Pack written to {pack_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
