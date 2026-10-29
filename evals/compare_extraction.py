"""Manually check extraction accuracy against the synthetic answer key.

Unlike extract.py's tests, this script DOES call the real Claude API —
that's the whole point, it's checking how good real extractions are.
Per CLAUDE.md, it never runs on its own: it prints how many calls it's
about to make and waits for you to type "yes" first.

Run it yourself with:
    python evals/compare_extraction.py
"""

from __future__ import annotations

import json
import math

from src.extract.config import PROJECT_ROOT
from src.extract.extract import ExtractionError, extract_invoice

DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
ANSWER_KEY_PATH = DATA_DIR / "answer_key.json"

# One of each: clean English PDF, clean Spanish PDF, clean Catalan PDF,
# a maths-error trap, a no-due-date trap, and a phone photo JPG.
SAMPLE_FILES = [
    "invoices/adobe_2026-08-05.pdf",
    "invoices/coworking_2026-07-01.pdf",
    "invoices/printer_2026-08-18.pdf",
    "invoices/electricity_2026-07-10.pdf",
    "invoices/travel_2026-10-20.pdf",
    "photos/pixelco_2026-09-25.jpg",
]

COMPARE_FIELDS = [
    "supplier",
    "invoice_number",
    "issue_date",
    "due_date",
    "currency",
    "net",
    "vat",
    "total",
    "document_type",
    "language",
]


def _expected_value(answer: dict, field: str):
    # The extraction prompt asks for the supplier name exactly as
    # printed, so that's the fair ground truth to compare against —
    # not the cleaned-up canonical "supplier" name in the answer key.
    if field == "supplier":
        return answer["supplier_as_printed"]
    return answer[field]


def _actual_value(result, field: str):
    value = getattr(result, field)
    if value is None:
        return None
    if field == "document_type":
        return value.value
    return str(value) if field in ("issue_date", "due_date") else value


def _values_match(expected, actual) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(expected, actual, abs_tol=0.005)
    return expected == actual


def main() -> int:
    answers_by_file = {entry["file"]: entry for entry in json.loads(
        ANSWER_KEY_PATH.read_text()
    )}

    print(f"This will make up to {len(SAMPLE_FILES)} Claude API calls")
    print("(fewer if any of these files are already cached):\n")
    for name in SAMPLE_FILES:
        print(f"  - {name}")
    print()

    reply = input('Type "yes" to continue: ').strip().lower()
    if reply != "yes":
        print("Aborted — no API calls made.")
        return 1

    rows = []
    for name in SAMPLE_FILES:
        path = DATA_DIR / name
        answer = answers_by_file[name]
        print(f"\nExtracting {name} ...")
        try:
            result = extract_invoice(path)
        except ExtractionError as error:
            print(f"  Error: {error}")
            continue

        for field in COMPARE_FIELDS:
            expected = _expected_value(answer, field)
            actual = _actual_value(result, field)
            confidence = getattr(result.confidence, field)
            match = _values_match(expected, actual)
            rows.append((name, field, expected, actual, confidence, match))

    header = f"{'file':<32} {'field':<15} {'expected':<22} {'actual':<22} {'conf':<6} {'match'}"
    print("\n" + header)
    print("-" * len(header))
    mismatches = 0
    for name, field, expected, actual, confidence, match in rows:
        if not match:
            mismatches += 1
        marker = "OK" if match else "MISMATCH"
        print(
            f"{name:<32} {field:<15} {str(expected):<22} {str(actual):<22} "
            f"{confidence:<6.2f} {marker}"
        )

    print(f"\n{mismatches} mismatch(es) out of {len(rows)} fields compared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
