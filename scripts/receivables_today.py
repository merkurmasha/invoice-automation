"""n8n wrapper: draft today's due payment reminders as Gmail-ready text.

    .venv/bin/python -m scripts.receivables_today [--today YYYY-MM-DD] [--dry-run]

Runs the real receivables scheduler (src.receivables.schedule) for
`today`, and for every invoice it reports as due, drafts the reminder
text with src.receivables.draft (which, per CLAUDE.md, is the one LLM
call in this script — the decision of *which* invoice needs a reminder
and at which stage is schedule.py's plain deterministic code, reused
as-is). Prints exactly one JSON object to stdout, one entry per draft
with To/Subject/Body, and exits:

    0 — pass: nothing due, or every draft looks complete
    2 — review: at least one draft is missing a required fact or used
        a forbidden term (see src.receivables.draft.FORBIDDEN_REVIEW_TERMS)
    1 — error: couldn't draft at all (e.g. no API key)

This never sends anything. draft_reminder() only ever writes a .md file
under data/drafts/ (see that module's own no-send source-scan test) —
the n8n workflow that calls this script turns each entry below into a
Gmail "Create Draft" node, never "Send".

With --dry-run, the script still runs the full pipeline (drafting
included — this still costs a real Claude API call) and prints the
same JSON, but never appends to data/reminder_log.csv
(src.receivables.schedule.record_drafted — see that module's "latest
missed stage only" docstring for why that log exists). Without
--dry-run, a real run marks every drafted (invoice, stage) pair as
done *permanently*, not just for today — running the same day again
afterwards correctly reports nothing due, because that pair has
already been drafted. Use --dry-run to preview what's due, as many
times as you like, without consuming that record; see
docs/n8n-setup.md's "Resetting between demo runs" section if you need
to clear what's already been drafted, e.g. to replay a demo.

Note: `Invoice.customer_name` is the only identity this project's
synthetic sales_invoices.csv carries for a customer — there's no real
email address anywhere in this portfolio project's data. The "to"
field below is that customer name, not an address; docs/n8n-setup.md
explains how to map it to a real recipient in the Gmail node by hand.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from src.receivables import draft, schedule
from src.receivables.config import REMINDER_LOG_PATH, SALES_INVOICES_PATH
from src.receivables.tracker import ReceivablesTracker

if TYPE_CHECKING:
    import anthropic

STATUS_PASS = "pass"
STATUS_REVIEW = "review"
STATUS_ERROR = "error"


def _parse_draft_file(path: Path) -> tuple[str, str, str]:
    """Pulls To/Subject/body back out of the .md file draft_reminder()
    wrote — see draft.py's _write_draft_file for the exact format this
    mirrors. The header has no blank line inside it, so the first
    "\\n\\n" is always the header/body boundary, even if the body itself
    later contains blank lines between paragraphs."""
    text = path.read_text(encoding="utf-8")
    header, _, body = text.partition("\n\n")
    to_line = next((line for line in header.splitlines() if line.startswith("To: ")), "To: ")
    subject_line = next(
        (line for line in header.splitlines() if line.startswith("Subject: ")), "Subject: "
    )
    return to_line.removeprefix("To: "), subject_line.removeprefix("Subject: "), body.rstrip("\n")


def draft_due_reminders(
    today: date,
    *,
    csv_path: str | Path | None = None,
    log_path: str | Path | None = None,
    drafts_dir: str | Path | None = None,
    client: "anthropic.Anthropic | None" = None,
    dry_run: bool = False,
) -> dict:
    """Draft every reminder due today and return the dict main() prints
    as JSON. Kept separate from main() so tests can call it directly
    with a fake `client` — CLAUDE.md's testing rule means tests must
    never reach the real Claude API.

    dry_run=True runs everything (drafting included) but skips
    record_drafted(), so the reminder log isn't touched and a repeat
    call — same day or not — reports the same items due again."""
    csv_path = csv_path or SALES_INVOICES_PATH
    log_path = log_path or REMINDER_LOG_PATH

    tracker = ReceivablesTracker.from_csv(csv_path)
    due = schedule.reminders_due(tracker, today, log_path=log_path)

    drafts: list[dict] = []
    any_needs_review = False
    for item in due:
        invoice = tracker.invoices[item.invoice_id]
        try:
            result = draft.draft_reminder(
                invoice,
                item.stage,
                today=today,
                log_path=log_path,
                client=client,
                drafts_dir=Path(drafts_dir) if drafts_dir else None,
            )
        except draft.DraftError as error:
            return {
                "status": STATUS_ERROR,
                "today": today.isoformat(),
                "error": str(error),
                "drafts": [],
            }
        if not dry_run:
            schedule.record_drafted(item.invoice_id, item.stage, today, log_path=log_path)

        to_addr, subject, body = _parse_draft_file(result.path)
        any_needs_review = any_needs_review or result.needs_review
        drafts.append(
            {
                "invoice": result.invoice_id,
                "stage": result.stage,
                "to": to_addr,
                "subject": subject,
                "body": body,
                "needs_review": result.needs_review,
                "reason": result.reason,
                "path": str(result.path),
            }
        )

    return {
        "status": STATUS_REVIEW if any_needs_review else STATUS_PASS,
        "today": today.isoformat(),
        "due_count": len(due),
        "drafts": drafts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Draft today's due payment reminders as Gmail-draft-ready text."
    )
    parser.add_argument("--today", default=None, help="ISO date (default: today)")
    parser.add_argument("--csv", default=None, help="Path to sales invoices CSV")
    parser.add_argument("--log-path", default=None, help="Path to the reminder log")
    parser.add_argument("--drafts-dir", default=None, help="Where to write .md draft files")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Draft everything due and print the same JSON, but don't append to "
        "data/reminder_log.csv — use this to preview what's due, repeatedly, "
        "without marking any (invoice, stage) pair as drafted.",
    )
    args = parser.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else date.today()
    result = draft_due_reminders(
        today,
        csv_path=args.csv,
        log_path=args.log_path,
        drafts_dir=args.drafts_dir,
        dry_run=args.dry_run,
    )

    print(json.dumps(result, indent=2))

    if result["status"] == STATUS_PASS:
        return 0
    if result["status"] == STATUS_REVIEW:
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
