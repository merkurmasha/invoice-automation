"""n8n wrapper: turn one invoice/receipt file into one intake decision.

    .venv/bin/python -m scripts.process_invoice <path-to-file> [--today YYYY-MM-DD] [--n8n]

Runs, in order: extraction (src.extract.extract.extract_invoice),
validation against the REAL intake duplicate cache
(data/cache/seen_invoices.json — DuplicateDetector's own default path,
the same one the rest of the pipeline uses, never the eval harness's
throwaway copy), supplier matching against the real supplier master
(data/suppliers.csv), and categorisation. Prints exactly one JSON
object to stdout and exits:

    0 — pass: safe for n8n to file automatically
    2 — review: a human should look at it (missing data, a new/unclear
        supplier, a low-confidence category, or a validation issue)
    1 — error: couldn't even run (bad file, missing API key, ...)

With --n8n, "review" also exits 0 — n8n's Execute Command node treats
any non-zero exit as a node failure, so this flag is for the intake
workflow, which parses the printed status itself to route "review" to
its review branch. "error" still exits non-zero either way.

Per CLAUDE.md, extraction and categorisation are the only two LLM calls
here. Duplicate detection, supplier matching, and the standardised
filename/subfolder naming are all plain code reusing the real pipeline
modules as-is — this file adds no new pipeline logic of its own.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from src.extract.extract import ExtractionError, extract_invoice
from src.extract.schema import ExtractedInvoice
from src.suppliers.categorise import CategorisationError, categorise
from src.suppliers.master import SupplierMaster
from src.validate.duplicates import DuplicateDetector
from src.validate.validate import validate_invoice

from .paths import SUPPLIER_MASTER_PATH

if TYPE_CHECKING:
    import anthropic

STATUS_PASS = "pass"
STATUS_REVIEW = "review"
STATUS_ERROR = "error"


def _safe_name(text: str) -> str:
    # Same scheme as src/pack/build.py's _safe_name — kept as its own
    # copy rather than imported, since pack/build.py isn't this
    # module's dependency and phase 8 doesn't touch that file.
    keep = "".join(ch if ch.isalnum() else "_" for ch in text)
    while "__" in keep:
        keep = keep.replace("__", "_")
    return keep.strip("_")


def _standardised_filename(
    extracted: ExtractedInvoice, supplier_name: str, original_path: Path
) -> str | None:
    if extracted.issue_date is None or extracted.invoice_number is None:
        return None
    return (
        f"{extracted.issue_date.isoformat()}_{_safe_name(supplier_name)}_"
        f"{_safe_name(extracted.invoice_number)}{original_path.suffix.lower()}"
    )


def _drive_subfolder(extracted: ExtractedInvoice, supplier_name: str) -> str | None:
    if extracted.issue_date is None:
        return None
    issue_date = extracted.issue_date
    return f"{issue_date.year:04d}/{issue_date.month:02d}/{_safe_name(supplier_name)}"


def process_invoice(
    path: str | Path,
    *,
    client: "anthropic.Anthropic | None" = None,
    today: date | None = None,
    duplicate_cache_path: str | Path | None = None,
    supplier_master_path: str | Path | None = None,
) -> dict:
    """Run the full intake pipeline for one file and return the dict
    main() prints as JSON. Kept separate from main() so tests can call
    it directly with a fake `client` — CLAUDE.md's testing rule means
    tests must never reach the real Claude API."""
    path = Path(path)
    today = today or date.today()
    result: dict = {"file": str(path)}

    try:
        extracted = extract_invoice(path, client=client)
    except ExtractionError as error:
        result["status"] = STATUS_ERROR
        result["error"] = f"extraction failed: {error}"
        return result

    result["extraction"] = extracted.model_dump(mode="json")

    detector = (
        DuplicateDetector(cache_path=duplicate_cache_path)
        if duplicate_cache_path is not None
        else DuplicateDetector()
    )
    detector.load()
    validation = validate_invoice(extracted, detector, today=today)
    detector.save()
    result["validation"] = validation.to_dict()

    reasons: list[str] = []
    if validation.status == "review":
        reasons.append("validation needs review")

    canonical_supplier_name: str | None = None
    if extracted.supplier:
        master = SupplierMaster(supplier_master_path or SUPPLIER_MASTER_PATH)
        supplier_match = master.match_or_create(extracted.supplier, seen_on=today.isoformat())
        canonical_supplier_name = supplier_match.canonical_name
        result["supplier_match"] = {
            "supplier_id": supplier_match.supplier_id,
            "canonical_name": supplier_match.canonical_name,
            "status": supplier_match.status,
            "score": supplier_match.score,
            "matched_against": supplier_match.matched_against,
        }
        if supplier_match.status in ("new", "possible_match"):
            reasons.append(f"supplier match: {supplier_match.status}")
    else:
        result["supplier_match"] = None
        reasons.append("no supplier name extracted")

    if canonical_supplier_name:
        try:
            category_result = categorise(canonical_supplier_name, client=client)
        except CategorisationError as error:
            result["status"] = STATUS_ERROR
            result["error"] = f"categorisation failed: {error}"
            return result
        result["category"] = category_result.model_dump()
        if category_result.needs_review():
            reasons.append("category: low confidence")
    else:
        result["category"] = None

    naming_supplier = canonical_supplier_name or extracted.supplier
    if naming_supplier:
        filename = _standardised_filename(extracted, naming_supplier, path)
        subfolder = _drive_subfolder(extracted, naming_supplier)
    else:
        filename = subfolder = None
    result["standardised_filename"] = filename
    result["drive_subfolder"] = subfolder
    if filename is None or subfolder is None:
        reasons.append("missing issue_date/invoice_number — can't name or file this document")

    result["review_reasons"] = reasons
    result["status"] = STATUS_REVIEW if reasons else STATUS_PASS
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one invoice/receipt file through extraction, validation, "
        "supplier matching, and categorisation."
    )
    parser.add_argument("path", help="Path to a PDF or JPG/PNG file")
    parser.add_argument(
        "--today", default=None, help="ISO date to validate against (default: today)"
    )
    parser.add_argument(
        "--duplicate-cache-path",
        default=None,
        help="Override the duplicate-detector cache path (default: data/cache/seen_invoices.json)",
    )
    parser.add_argument(
        "--supplier-master-path",
        default=None,
        help="Override the supplier master CSV path (default: data/suppliers.csv)",
    )
    parser.add_argument(
        "--n8n",
        action="store_true",
        help='Exit 0 for "review" as well as "pass" (n8n treats any non-zero '
        'exit as a node failure); "error" still exits non-zero.',
    )
    args = parser.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else None
    result = process_invoice(
        args.path,
        today=today,
        duplicate_cache_path=args.duplicate_cache_path,
        supplier_master_path=args.supplier_master_path,
    )

    print(json.dumps(result, indent=2))

    if result["status"] == STATUS_PASS:
        return 0
    if result["status"] == STATUS_REVIEW:
        return 0 if args.n8n else 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
