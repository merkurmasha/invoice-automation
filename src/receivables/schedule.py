"""Decides which invoices need a reminder drafted today.

Plain deterministic code per CLAUDE.md — no LLM involved (drafting the
actual text is draft.py's job). Stage due dates are a fixed offset from
each invoice's due date: stage 1 on the due date, stage 2 a week later,
stage 3 two weeks later (src/receivables/config.py:STAGE_OFFSETS_DAYS).

The "latest missed stage only" rule: if an invoice is 20 days overdue
and nothing has been drafted yet, stages 1 AND 2 are also "due" by now
(their dates have passed) — but sending three reminders at once would
be confusing and spammy. So only the latest stage whose date has
arrived, and that hasn't already been drafted, is reported as due.
Earlier stages are simply superseded; they're never drafted, because
by the time this runs again the latest-due stage will be the same one
or a later one, not an earlier one.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .config import REMINDER_LOG_PATH, STAGE_OFFSETS_DAYS
from .tracker import STATUS_PAID, ReceivablesTracker

LOG_FIELDNAMES = ["invoice_id", "stage", "drafted_on"]


@dataclass(frozen=True)
class ReminderDue:
    invoice_id: str
    stage: int
    stage_date: date
    days_overdue: int


def stage_date(due_date: date, stage: int) -> date:
    return due_date + timedelta(days=STAGE_OFFSETS_DAYS[stage])


def load_drafted_stages(log_path: str | Path = REMINDER_LOG_PATH) -> dict[str, set[int]]:
    """invoice_id -> the set of stages already drafted, read from the
    reminder log. Returns an empty mapping if the log doesn't exist yet
    (nothing has ever been drafted)."""
    path = Path(log_path)
    if not path.exists():
        return {}
    drafted: dict[str, set[int]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            drafted.setdefault(row["invoice_id"], set()).add(int(row["stage"]))
    return drafted


def record_drafted(
    invoice_id: str,
    stage: int,
    on_date: date,
    log_path: str | Path = REMINDER_LOG_PATH,
) -> None:
    """Append one (invoice, stage) record to the reminder log so it's
    never drafted again."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "invoice_id": invoice_id,
                "stage": stage,
                "drafted_on": on_date.isoformat(),
            }
        )


def reminders_due(
    tracker: ReceivablesTracker,
    today: date,
    log_path: str | Path = REMINDER_LOG_PATH,
) -> list[ReminderDue]:
    """Which invoices need a reminder drafted today, and at which
    stage. Paid invoices are skipped. At most one stage per invoice is
    returned: the latest stage whose date has arrived that hasn't
    already been drafted (see module docstring)."""
    drafted = load_drafted_stages(log_path)
    due: list[ReminderDue] = []

    for invoice in tracker.invoices.values():
        if invoice.status == STATUS_PAID:
            continue

        already_drafted = drafted.get(invoice.invoice_number, set())
        eligible_stages = [
            stage
            for stage in sorted(STAGE_OFFSETS_DAYS)
            if today >= stage_date(invoice.due_date, stage) and stage not in already_drafted
        ]
        if not eligible_stages:
            continue

        stage = max(eligible_stages)
        due.append(
            ReminderDue(
                invoice_id=invoice.invoice_number,
                stage=stage,
                stage_date=stage_date(invoice.due_date, stage),
                days_overdue=(today - invoice.due_date).days,
            )
        )

    return due
