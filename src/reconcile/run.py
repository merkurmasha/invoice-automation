"""CLI for bank reconciliation.

    python -m src.reconcile.run --today 2026-10-28

Runs the matcher (match.py) over the bank statement against both
ledgers (supplier invoices from the answer key, sales invoices from
sales_invoices.csv), then:

  - prints the receivables aging summary BEFORE reconciliation (sales
    invoices as sales_invoices.csv alone describes them - nothing paid),
  - replays every payment the matcher found for a sales invoice onto a
    real src.receivables.tracker.ReceivablesTracker via its existing
    mark_payment() - this only ever touches an in-memory copy loaded
    fresh from the CSV, never the committed file,
  - prints the aging summary AFTER, so the effect of reconciliation on
    what receivables actually still need chasing is visible,
  - writes every exception (unmatched/ambiguous/possible/no-payment/
    partial) to a CSV for a human to review.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from src.receivables import aging
from src.receivables.tracker import ReceivablesTracker

from . import config, exceptions, ledger, match

DEFAULT_EXCEPTIONS_PATH = config.PROJECT_ROOT / "data" / "reconcile" / "exceptions.csv"


def _print_aging(label: str, tracker: ReceivablesTracker, today: date) -> None:
    summary = aging.aging_summary(tracker, today)
    print(f"{label} (as of {today.isoformat()}):")
    for bucket in aging.BUCKETS:
        row = summary[bucket]
        print(f"  {bucket:>8}: {row['count']:>2} invoice(s), outstanding {row['outstanding']:.2f}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile the bank statement against both ledgers.")
    parser.add_argument("--today", required=True, help="ISO date, e.g. 2026-10-28")
    parser.add_argument(
        "--exceptions-out", default=str(DEFAULT_EXCEPTIONS_PATH), help="Where to write exceptions.csv"
    )
    args = parser.parse_args(argv)
    today = date.fromisoformat(args.today)

    tracker_before = ReceivablesTracker.from_csv(config.SALES_INVOICES_PATH)
    _print_aging("Receivables aging BEFORE reconciliation", tracker_before, today)

    bank_lines = match.load_bank_statement(config.BANK_STATEMENT_PATH)
    payables = ledger.load_payable_obligations(config.ANSWER_KEY_PATH)
    receivables = ledger.load_receivable_obligations(config.SALES_INVOICES_PATH)
    obligations = payables + receivables

    decisions = match.reconcile(bank_lines, obligations)

    tracker_after = ReceivablesTracker.from_csv(config.SALES_INVOICES_PATH)
    for ob in receivables:
        for _bank_line_id, pay_date, amount in ob.payment_events:
            tracker_after.mark_payment(ob.invoice_number, amount, pay_date)
    _print_aging("Receivables aging AFTER reconciliation", tracker_after, today)

    tally: dict[str, int] = {}
    for decision in decisions:
        tally[decision.category] = tally.get(decision.category, 0) + 1
    print("Bank line outcomes:")
    for category in sorted(tally):
        print(f"  {category:>10}: {tally[category]}")
    print()

    rows = exceptions.build_exceptions(decisions, obligations, today)
    exceptions.write_exceptions_csv(rows, args.exceptions_out)
    print(f"{len(rows)} exception row(s) written to {args.exceptions_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
