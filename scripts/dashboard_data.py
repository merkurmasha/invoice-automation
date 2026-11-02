"""Assembles every number the dashboard shows, by calling the project's
existing deterministic modules — no new pipeline logic, no LLM call,
no network access, per CLAUDE.md. See scripts/build_dashboard.py for
the CLI and scripts/dashboard_html.py for turning this module's output
into the page itself.

Scoping convention, chosen to match how src/pack/build.py already
presents things (rather than invent a new rule):

  - "Spend by category" and the review queue are scoped to `month`,
    like ledger.csv's "Top categories" and summary.md's "N invoice(s)
    this month failed validation".
  - Receivables aging is the WHOLE book, not just `month` — summary.md
    already labels its own aging table "(whole book, not just this
    month)", so the dashboard keeps that.
  - Bank reconciliation runs over the WHOLE statement — there's no
    month-filtered reconcile() anywhere in src/reconcile/; src.reconcile.run's
    own CLI reconciles the whole statement every time, so the dashboard
    does the same.

COMPANY_NAME is the one new constant this phase adds (the fictional
company name from CLAUDE.md); everything else is read from existing
data/config.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from src.pack import build as pack_build
from src.receivables import aging
from src.receivables.config import STAGE_OFFSETS_DAYS
from src.receivables.draft import STAGE_LABELS
from src.receivables.schedule import ReminderDue, reminders_due
from src.receivables.tracker import STATUS_PAID, ReceivablesTracker
from src.reconcile import config as reconcile_config
from src.reconcile import ledger, match

from . import eval_summary

COMPANY_NAME = "Costa Brava Studio S.L."

# Bank-line decision categories that count as "matched" without a human
# having to do anything further (match.py applies these automatically).
_MATCHED_CATEGORIES = {"auto", "partial", "combo"}


def _month_label(month: str) -> str:
    year, month_num = month.split("-")
    month_name = date(int(year), int(month_num), 1).strftime("%B")
    return f"{month_name} {year}"


def _month_matches(d: date, month: str) -> bool:
    return f"{d.year:04d}-{d.month:02d}" == month


def _reconcile_everything() -> tuple[list[match.MatchDecision], list[ledger.Obligation], list[match.BankLine]]:
    """Runs the real matcher over the whole bank statement against both
    ledgers, exactly like src.reconcile.run.main() does. Returns the
    decisions, the (now payment-mutated) obligations list, and the raw
    bank lines (so the caller can report the statement's actual date
    range without re-reading the file)."""
    bank_lines = match.load_bank_statement(reconcile_config.BANK_STATEMENT_PATH)
    payables = ledger.load_payable_obligations(reconcile_config.ANSWER_KEY_PATH)
    receivables = ledger.load_receivable_obligations(reconcile_config.SALES_INVOICES_PATH)
    obligations = payables + receivables
    decisions = match.reconcile(bank_lines, obligations)
    return decisions, obligations, bank_lines


def _tracker_after_reconciliation(receivables: list[ledger.Obligation]) -> ReceivablesTracker:
    """A fresh ReceivablesTracker with every payment the matcher found
    for a receivable replayed onto it, same as src/pack/build.build_pack()
    and src/reconcile/run.py do."""
    tracker = ReceivablesTracker.from_csv(reconcile_config.SALES_INVOICES_PATH)
    for obligation in receivables:
        for _bank_line_id, pay_date, amount in obligation.payment_events:
            tracker.mark_payment(obligation.invoice_number, amount, pay_date)
    return tracker


def _spend_by_category(answer_key_entries: list[dict], month: str, statuses: dict[str, str]) -> list[dict]:
    obligations_by_invoice: dict[str, ledger.Obligation] = {}  # not needed for paid_status here
    rows = pack_build.build_ledger_rows(answer_key_entries, month, statuses, obligations_by_invoice)
    totals: dict[tuple[str, str], float] = {}
    for row in rows:
        key = (row.category, row.currency)
        totals[key] = round(totals.get(key, 0.0) + row.total, 2)
    return [
        {"category": category, "currency": currency, "total": total}
        for (category, currency), total in sorted(totals.items(), key=lambda kv: (-abs(kv[1]), kv[0]))
    ]


def _total_spend(answer_key_entries: list[dict], month: str, statuses: dict[str, str]) -> list[dict]:
    obligations_by_invoice: dict[str, ledger.Obligation] = {}
    rows = pack_build.build_ledger_rows(answer_key_entries, month, statuses, obligations_by_invoice)
    totals: dict[str, float] = {}
    for row in rows:
        totals[row.currency] = round(totals.get(row.currency, 0.0) + row.total, 2)
    return [{"currency": currency, "total": total} for currency, total in sorted(totals.items())]


def _review_queue(answer_key_entries: list[dict], month: str) -> list[dict]:
    results = pack_build.validation_results(answer_key_entries)
    seen: set[str] = set()
    queue: list[dict] = []
    for entry in answer_key_entries:
        invoice_number = entry["invoice_number"]
        if invoice_number in seen:
            continue
        seen.add(invoice_number)
        if not _month_matches(date.fromisoformat(entry["issue_date"]), month):
            continue
        result = results.get(invoice_number)
        if result is None or result.status != "review":
            continue
        queue.append(
            {
                "invoice_number": invoice_number,
                "supplier": entry["supplier"],
                "issue_date": entry["issue_date"],
                "summary": result.summary,
                "issues": [asdict(issue) for issue in result.issues],
            }
        )
    queue.sort(key=lambda item: item["invoice_number"])
    return queue


def _reminder_stage_legend() -> list[dict]:
    """The real reminder-stage thresholds, read straight from
    src/receivables/config.py (STAGE_OFFSETS_DAYS) and
    src/receivables/draft.py (STAGE_LABELS) — never hand-typed here, so
    the legend can't silently drift out of sync with the actual
    scheduling rule in src/receivables/schedule.py."""
    return [
        {"stage": stage, "label": STAGE_LABELS[stage], "days_after_due": STAGE_OFFSETS_DAYS[stage]}
        for stage in sorted(STAGE_OFFSETS_DAYS)
    ]


def _reminder_for(invoice_number: str, reminders: list[ReminderDue]) -> dict | None:
    for reminder in reminders:
        if reminder.invoice_id == invoice_number:
            return {
                "stage": reminder.stage,
                "stage_label": STAGE_LABELS[reminder.stage],
                "days_overdue": reminder.days_overdue,
            }
    return None


def _receivables_aging(tracker: ReceivablesTracker, today: date, nonexistent_log_path) -> dict:
    summary = aging.aging_summary(tracker, today)
    buckets = [
        {"bucket": bucket, "count": summary[bucket]["count"], "outstanding": summary[bucket]["outstanding"]}
        for bucket in aging.BUCKETS
    ]

    # A log path that is guaranteed not to exist, so this always reflects
    # a clean "nothing drafted yet" demo state, never whatever is sitting
    # in a developer's local, gitignored data/reminder_log.csv.
    reminders = reminders_due(tracker, today, log_path=nonexistent_log_path)

    overdue: list[dict] = []
    for invoice in tracker.invoices.values():
        if invoice.status == STATUS_PAID:
            continue
        bucket = aging.aging_bucket(invoice.due_date, today)
        if bucket == aging.CURRENT:
            continue
        reminder = _reminder_for(invoice.invoice_number, reminders)
        overdue.append(
            {
                "invoice_number": invoice.invoice_number,
                "customer_name": invoice.customer_name,
                "currency": invoice.currency,
                "due_date": invoice.due_date.isoformat(),
                "days_overdue": (today - invoice.due_date).days,
                "amount_outstanding": invoice.amount_outstanding,
                "bucket": bucket,
                "reminder": reminder,
            }
        )
    overdue.sort(key=lambda item: -item["days_overdue"])

    return {"buckets": buckets, "overdue_invoices": overdue, "reminder_stage_legend": _reminder_stage_legend()}


def _open_receivables_total(aging_data: dict) -> float:
    return round(sum(bucket["outstanding"] for bucket in aging_data["buckets"]), 2)


def _reconciliation_summary(decisions: list[match.MatchDecision]) -> dict:
    tally: dict[str, int] = {}
    for decision in decisions:
        tally[decision.category] = tally.get(decision.category, 0) + 1

    matched_count = sum(count for category, count in tally.items() if category in _MATCHED_CATEGORIES)
    total = len(decisions)
    needs_review = [d for d in decisions if d.category not in _MATCHED_CATEGORIES]
    needs_review.sort(key=lambda d: (d.bank_line.txn_date, d.bank_line.line_id))

    return {
        "total_lines": total,
        "matched_count": matched_count,
        "needs_review_count": len(needs_review),
        "match_rate_pct": round(100 * matched_count / total, 1) if total else 0.0,
        "by_category": tally,
        "needs_review_items": [
            {
                "bank_date": d.bank_line.txn_date.isoformat(),
                "description": d.bank_line.description,
                "amount": d.bank_line.amount,
                "category": d.category,
                "invoice_numbers": d.invoice_numbers,
                "reason": d.reason,
            }
            for d in needs_review
        ],
    }


def build_dashboard_data(month: str, today: date, nonexistent_log_path) -> dict:
    """The single entry point: everything the HTML renderer needs, as
    one plain dict (so tests can assert on the numbers directly,
    independent of how the HTML is written)."""
    answer_key_entries: list[dict] = json.loads(reconcile_config.ANSWER_KEY_PATH.read_text())
    statuses = pack_build.validation_statuses(answer_key_entries)

    decisions, obligations, bank_lines = _reconcile_everything()
    receivables = [ob for ob in obligations if ob.kind == ledger.RECEIVABLE]
    tracker = _tracker_after_reconciliation(receivables)
    bank_statement_through = max(line.txn_date for line in bank_lines).isoformat()

    aging_data = _receivables_aging(tracker, today, nonexistent_log_path)
    spend_by_category = _spend_by_category(answer_key_entries, month, statuses)
    total_spend = _total_spend(answer_key_entries, month, statuses)
    review_queue = _review_queue(answer_key_entries, month)
    reconciliation = _reconciliation_summary(decisions)
    accuracy = eval_summary.load_accuracy_strip()

    return {
        "company": COMPANY_NAME,
        "month": month,
        "month_label": _month_label(month),
        "today": today.isoformat(),
        "bank_statement_through": bank_statement_through,
        "headline": {
            "total_spend": total_spend,
            "open_receivables": _open_receivables_total(aging_data),
            "review_queue_count": len(review_queue),
            "reconciliation_match_rate_pct": reconciliation["match_rate_pct"],
        },
        "spend_by_category": spend_by_category,
        "receivables_aging": aging_data,
        "review_queue": review_queue,
        "reconciliation": reconciliation,
        "accuracy": accuracy,
    }
