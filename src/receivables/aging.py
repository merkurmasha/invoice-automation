"""Aging buckets for outstanding sales invoices.

Plain deterministic code per CLAUDE.md. "today" is always passed in by
the caller — never read from the system clock in here — so the same
call always produces the same answer and tests don't depend on when
they happen to run.
"""

from __future__ import annotations

from datetime import date

from .tracker import STATUS_PAID, ReceivablesTracker

CURRENT = "current"
BUCKET_1_30 = "1-30"
BUCKET_31_60 = "31-60"
BUCKET_60_PLUS = "60+"

BUCKETS = (CURRENT, BUCKET_1_30, BUCKET_31_60, BUCKET_60_PLUS)


def aging_bucket(due_date: date, today: date) -> str:
    """Which aging bucket an invoice falls into, given its due date and
    "today". Due today (or not yet due) counts as current; from there
    the overdue bucket boundaries are inclusive of their upper day
    (e.g. exactly 30 days late is still "1-30", 31 days late is the
    first day of "31-60")."""
    days_overdue = (today - due_date).days
    if days_overdue <= 0:
        return CURRENT
    if days_overdue <= 30:
        return BUCKET_1_30
    if days_overdue <= 60:
        return BUCKET_31_60
    return BUCKET_60_PLUS


def aging_summary(tracker: ReceivablesTracker, today: date) -> dict[str, dict[str, float]]:
    """Count and outstanding amount per aging bucket, across every
    invoice in the tracker that isn't fully paid."""
    summary = {bucket: {"count": 0, "outstanding": 0.0} for bucket in BUCKETS}
    for invoice in tracker.invoices.values():
        if invoice.status == STATUS_PAID:
            continue
        bucket = aging_bucket(invoice.due_date, today)
        summary[bucket]["count"] += 1
        summary[bucket]["outstanding"] = round(
            summary[bucket]["outstanding"] + invoice.amount_outstanding, 2
        )
    return summary
