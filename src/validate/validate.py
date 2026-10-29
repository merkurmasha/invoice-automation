"""Run every validation check on one extracted invoice and decide
whether it can go straight through ("pass") or needs a human to look
at it ("review").

Runnable as:
    python -m src.validate.validate <path-to-extracted-json>
Exit codes: 0 = pass, 2 = review, 1 = couldn't even run the checks
(bad file, bad JSON, doesn't match the extraction schema). n8n will
branch on these exit codes later.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from src.extract.schema import ExtractedInvoice

from .checks import (
    Issue,
    check_dates,
    check_document_type,
    check_low_confidence,
    check_maths,
    check_required_fields,
)
from .duplicates import DuplicateDetector

# Codes that mean "this invoice relates to one we've already seen", as
# opposed to "this particular reading of the invoice is untrustworthy".
_DUPLICATE_CODES = {"DUPLICATE", "AMOUNT_CONFLICT"}


@dataclass(frozen=True)
class ValidationResult:
    status: str  # "pass" or "review"
    issues: list[Issue]
    summary: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "issues": [asdict(issue) for issue in self.issues],
            "summary": self.summary,
        }


def validate_invoice(
    extracted: ExtractedInvoice, detector: DuplicateDetector, today: date
) -> ValidationResult:
    """Run all checks and return a combined result.

    Design choice: if an invoice has an error that ISN'T about being a
    duplicate (e.g. a maths mismatch, a missing required field), we
    don't add it to the duplicate detector's memory. Why: that error
    usually means this particular reading of the document is
    unreliable — maybe the extraction misread a number. If we
    remembered it anyway, the *correct* version of the same invoice
    (re-scanned, or re-extracted after a fix) would later get flagged
    as an AMOUNT_CONFLICT against the bad data, blocking the good copy
    for no good reason. Leaving it unregistered means the first
    trustworthy reading of that invoice is the one that establishes
    what "already seen" means.
    """
    issues: list[Issue] = []
    issues += check_required_fields(extracted)
    issues += check_maths(extracted)
    issues += check_low_confidence(extracted)
    issues += check_dates(extracted, today)
    issues += check_document_type(extracted)
    issues += detector.check(extracted)

    has_untrustworthy_error = any(
        issue.severity == "error" and issue.code not in _DUPLICATE_CODES
        for issue in issues
    )
    if not has_untrustworthy_error:
        detector.register(extracted)

    status = "review" if issues else "pass"
    summary = _summarize(status, issues)
    return ValidationResult(status=status, issues=issues, summary=summary)


def _summarize(status: str, issues: list[Issue]) -> str:
    if status == "pass":
        return "No issues found."
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    parts = []
    if error_count:
        parts.append(f"{error_count} error{'s' if error_count != 1 else ''}")
    if warning_count:
        parts.append(f"{warning_count} warning{'s' if warning_count != 1 else ''}")
    return "Needs review: " + " and ".join(parts) + "."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an extracted invoice JSON file against the extraction schema."
    )
    parser.add_argument("path", help="Path to a JSON file in the extraction schema")
    args = parser.parse_args(argv)

    try:
        text = Path(args.path).read_text()
    except OSError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        extracted = ExtractedInvoice.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as error:
        print(f"Error: {args.path} is not valid extracted-invoice JSON: {error}", file=sys.stderr)
        return 1

    detector = DuplicateDetector()
    detector.load()
    result = validate_invoice(extracted, detector, today=date.today())
    detector.save()

    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == "pass" else 2


if __name__ == "__main__":
    sys.exit(main())
