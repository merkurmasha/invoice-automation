"""Individual validation checks for one extracted invoice.

Each check function looks at one thing and returns a list of Issue
objects — empty if nothing is wrong. They're kept separate (rather than
one big function) so each rule can be tested and reasoned about on its
own, and so validate.py can just run the full list and collect results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from src.extract.schema import DocumentType, ExtractedInvoice

from .config import AMOUNT_TOLERANCE, CONFIDENCE_THRESHOLD, REQUIRED_FIELDS

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    """One thing a human should look at: a short code to filter/sort on,
    a severity, and a plain-English message for a review queue."""

    severity: Severity
    code: str
    message: str


def check_maths(extracted: ExtractedInvoice) -> list[Issue]:
    """net + vat must equal total, within AMOUNT_TOLERANCE.

    This works for credit notes too: their amounts are just negative,
    and the same addition still has to hold (-167.97 + -35.27 ==
    -203.24). If any of the three is missing we can't do the sum, so we
    skip silently — the required-fields check covers a missing total,
    and net/vat aren't required."""
    net, vat, total = extracted.net, extracted.vat, extracted.total
    if net is None or vat is None or total is None:
        return []
    if abs((net + vat) - total) > AMOUNT_TOLERANCE:
        return [
            Issue(
                "error",
                "MATH_MISMATCH",
                f"net ({net}) + vat ({vat}) = {net + vat:g}, but the "
                f"printed total is {total}.",
            )
        ]
    return []


def check_required_fields(extracted: ExtractedInvoice) -> list[Issue]:
    """Every field in REQUIRED_FIELDS must be present (error if not).
    due_date is handled separately as a warning, since we can still
    process an invoice without a stated due date."""
    issues = [
        Issue(
            "error",
            "MISSING_FIELD",
            f"Required field '{field_name}' is missing.",
        )
        for field_name in REQUIRED_FIELDS
        if getattr(extracted, field_name) is None
    ]
    if extracted.due_date is None:
        issues.append(
            Issue(
                "warning",
                "MISSING_DUE_DATE",
                "due_date is missing — confirm payment terms with the supplier.",
            )
        )
    return issues


def check_low_confidence(extracted: ExtractedInvoice) -> list[Issue]:
    """Flag any REQUIRED_FIELDS field whose extraction confidence is
    below CONFIDENCE_THRESHOLD, so a human double-checks the source
    document instead of trusting a shaky read."""
    issues = []
    for field_name in REQUIRED_FIELDS:
        score = getattr(extracted.confidence, field_name)
        if score < CONFIDENCE_THRESHOLD:
            issues.append(
                Issue(
                    "warning",
                    "LOW_CONFIDENCE",
                    f"Low confidence ({score:.2f}) on '{field_name}' — "
                    "worth checking against the source document.",
                )
            )
    return issues


def check_dates(extracted: ExtractedInvoice, today: date) -> list[Issue]:
    """due_date before issue_date is always wrong (error). An issue_date
    after `today` is suspicious but not necessarily wrong — a document
    could be post-dated — so it's only a warning. `today` is passed in
    by the caller rather than read from the system clock here, so this
    function stays deterministic and testable."""
    issues = []
    if extracted.due_date is not None and extracted.issue_date is not None:
        if extracted.due_date < extracted.issue_date:
            issues.append(
                Issue(
                    "error",
                    "DUE_BEFORE_ISSUE",
                    f"due_date ({extracted.due_date}) is before issue_date "
                    f"({extracted.issue_date}).",
                )
            )
    if extracted.issue_date is not None and extracted.issue_date > today:
        issues.append(
            Issue(
                "warning",
                "FUTURE_ISSUE_DATE",
                f"issue_date ({extracted.issue_date}) is after today ({today}).",
            )
        )
    return issues


def check_document_type(extracted: ExtractedInvoice) -> list[Issue]:
    """A credit note should reduce what's owed (negative total); an
    invoice shouldn't. Either mismatch is only a warning, not an error —
    the document type and the sign of the total could legitimately be
    extracted independently, so this flags it for a human rather than
    assuming one of the two readings is wrong."""
    doc_type, total = extracted.document_type, extracted.total
    if doc_type is None or total is None:
        return []
    if doc_type == DocumentType.CREDIT_NOTE and total >= 0:
        return [
            Issue(
                "warning",
                "CREDIT_NOTE_NOT_NEGATIVE",
                f"Document type is credit_note but total ({total}) is not negative.",
            )
        ]
    if doc_type == DocumentType.INVOICE and total < 0:
        return [
            Issue(
                "warning",
                "INVOICE_NEGATIVE_TOTAL",
                f"Document type is invoice but total ({total}) is negative.",
            )
        ]
    return []
