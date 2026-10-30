"""CLI for the receivables module.

    python -m src.receivables.run --today 2026-10-28

Always prints the aging summary and the reminders that are due. Only
drafts them (and only then calls the Claude API) when --draft is
passed, and even then asks for a "yes" after showing how many API
calls that will make — nothing is drafted, and nothing is ever sent,
without that confirmation. See CLAUDE.md's safety rules.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import aging, draft, schedule
from .config import DRAFT_MODEL, REMINDER_LOG_PATH, SALES_INVOICES_PATH
from .tracker import ReceivablesTracker


def _print_aging_summary(tracker: ReceivablesTracker, today: date) -> None:
    summary = aging.aging_summary(tracker, today)
    print(f"Aging summary as of {today.isoformat()} (paid invoices excluded):")
    for bucket in aging.BUCKETS:
        row = summary[bucket]
        print(f"  {bucket:>8}: {row['count']:>2} invoice(s), outstanding {row['outstanding']:.2f}")
    print()


def _print_reminders_due(due: list[schedule.ReminderDue], tracker: ReceivablesTracker) -> None:
    if not due:
        print("No reminders due today.")
        return
    print(f"{len(due)} reminder(s) due today:")
    for item in due:
        invoice = tracker.invoices[item.invoice_id]
        print(
            f"  - {item.invoice_id} ({invoice.customer_name}): stage {item.stage}, "
            f"{item.days_overdue} day(s) overdue, outstanding {invoice.amount_outstanding:.2f} "
            f"{invoice.currency}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Receivables aging, scheduling and reminders.")
    parser.add_argument("--today", required=True, help="ISO date, e.g. 2026-10-28")
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Actually draft today's due reminders (calls the Claude API).",
    )
    parser.add_argument("--csv", default=str(SALES_INVOICES_PATH), help="Path to sales invoices CSV")
    parser.add_argument("--log-path", default=str(REMINDER_LOG_PATH), help="Path to the reminder log")
    args = parser.parse_args(argv)

    today = date.fromisoformat(args.today)
    tracker = ReceivablesTracker.from_csv(args.csv)

    _print_aging_summary(tracker, today)

    due = schedule.reminders_due(tracker, today, log_path=args.log_path)
    _print_reminders_due(due, tracker)

    if not due:
        return 0

    if not args.draft:
        print("\nRun again with --draft to generate these as draft files (data/drafts/).")
        return 0

    uncached = [
        item
        for item in due
        if not draft.is_cached(tracker.invoices[item.invoice_id], item.stage, DRAFT_MODEL)
    ]
    print()
    if uncached:
        print(f"{len(uncached)} of {len(due)} reminder(s) need a live API call to model '{DRAFT_MODEL}':")
        for item in uncached:
            print(f"  - {item.invoice_id} stage {item.stage}")
    else:
        print(f"All {len(due)} reminder(s) are already cached — no API calls needed.")
    print()
    reply = input('Type "yes" to continue: ').strip().lower()
    if reply != "yes":
        print("Aborted — no drafts written.")
        return 1

    print()
    for item in due:
        invoice = tracker.invoices[item.invoice_id]
        result = draft.draft_reminder(invoice, item.stage, today=today)
        schedule.record_drafted(item.invoice_id, item.stage, today, log_path=args.log_path)
        flag = " [NEEDS REVIEW]" if result.needs_review else ""
        print(f"  - wrote {result.path}{flag}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
