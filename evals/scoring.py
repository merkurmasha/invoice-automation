"""Pure scoring functions for the eval harness.

Nothing here touches the Claude API, the extraction cache, or the
filesystem — every function takes already-extracted data (an
ExtractedInvoice plus a list of validation Issues) and an answer-key
entry, and returns plain data. That's what makes these functions cheap
to unit test with hand-built fixtures instead of real extractions.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.extract.schema import ExtractedInvoice
from src.validate.checks import Issue

# ---------------------------------------------------------------------------
# Field-level accuracy
# ---------------------------------------------------------------------------

FIELDS = [
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

AMOUNT_FIELDS = {"net", "vat", "total"}
DATE_FIELDS = {"issue_date", "due_date"}
AMOUNT_TOLERANCE = 0.01


def expected_value(answer: dict, field: str):
    # The extraction prompt asks Claude to copy the supplier name exactly
    # as printed, so that's the fair ground truth — not the cleaned-up
    # canonical "supplier" name the answer key also carries for
    # duplicate/reconciliation purposes.
    if field == "supplier":
        return answer["supplier_as_printed"]
    return answer[field]


def actual_value(extracted: ExtractedInvoice, field: str):
    value = getattr(extracted, field)
    if value is None:
        return None
    if field == "document_type":
        return value.value
    if field in DATE_FIELDS:
        return value.isoformat()
    return value


def fields_match(expected, actual, field: str) -> bool:
    """Null-vs-null counts as correct; null vs a value never does."""
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    if field in AMOUNT_FIELDS:
        return abs(float(expected) - float(actual)) <= AMOUNT_TOLERANCE
    return expected == actual


@dataclass(frozen=True)
class FieldScore:
    file: str
    field: str
    expected: object
    actual: object
    confidence: float
    correct: bool
    doc_kind: str  # "pdf" or "photo"
    language: str | None
    currency: str | None


def score_fields(answer: dict, extracted: ExtractedInvoice, doc_kind: str) -> list[FieldScore]:
    """Score every FIELDS entry for one document against its answer-key
    entry. `doc_kind` is "pdf" or "photo", used later for the accuracy
    breakdown by document type."""
    scores = []
    for field in FIELDS:
        expected = expected_value(answer, field)
        actual = actual_value(extracted, field)
        scores.append(
            FieldScore(
                file=answer["file"],
                field=field,
                expected=expected,
                actual=actual,
                confidence=getattr(extracted.confidence, field),
                correct=fields_match(expected, actual, field),
                doc_kind=doc_kind,
                language=answer.get("language"),
                currency=answer.get("currency"),
            )
        )
    return scores


def accuracy_breakdown(scores: list[FieldScore], key_fn) -> dict[str, tuple[int, int]]:
    """Group scores by key_fn(score) and return {key: (correct, total)}."""
    tally: dict[str, list[int]] = {}
    for score in scores:
        key = key_fn(score)
        bucket = tally.setdefault(key, [0, 0])
        bucket[1] += 1
        if score.correct:
            bucket[0] += 1
    return {key: (correct, total) for key, (correct, total) in tally.items()}


def overall_accuracy(scores: list[FieldScore]) -> tuple[int, int]:
    correct = sum(1 for s in scores if s.correct)
    return correct, len(scores)


def field_mismatches(scores: list[FieldScore]) -> list[FieldScore]:
    return [s for s in scores if not s.correct]


def lowest_confidence_correct(scores: list[FieldScore], n: int = 5) -> list[FieldScore]:
    correct = [s for s in scores if s.correct]
    return sorted(correct, key=lambda s: s.confidence)[:n]


def high_confidence_wrong(scores: list[FieldScore], threshold: float = 0.90) -> list[FieldScore]:
    return [s for s in scores if not s.correct and s.confidence > threshold]


def compare_to_source(photo_extracted: ExtractedInvoice, pdf_extracted: ExtractedInvoice) -> list[tuple[str, bool]]:
    """Compare a photo's extraction to its source PDF's extraction,
    field by field — not against the answer key, since this measures
    extraction consistency across the two renderings of one document."""
    results = []
    for field in FIELDS:
        a = actual_value(photo_extracted, field)
        b = actual_value(pdf_extracted, field)
        results.append((field, fields_match(a, b, field)))
    return results


# ---------------------------------------------------------------------------
# Validation / trap scoring
# ---------------------------------------------------------------------------

# One expected outcome per trap type the synthetic generator produces,
# defined in one place so it's easy to read and sanity-check before a run.
# A trap value that shows up in the answer key but isn't a key here makes
# evaluate_trap() raise, rather than silently score it as a miss.
TRAP_EXPECTATIONS: dict[str | None, str] = {
    "maths_error": "must include MATH_MISMATCH",
    "no_due_date": "must include MISSING_DUE_DATE",
    "duplicate_exact": "must include DUPLICATE",
    "duplicate_near": "must include AMOUNT_CONFLICT",
    "credit_note": (
        "must NOT include MATH_MISMATCH or a negative-amount issue "
        "(CREDIT_NOTE_NOT_NEGATIVE / INVOICE_NEGATIVE_TOTAL) — "
        "MISSING_DUE_DATE alone is acceptable"
    ),
    "reverse_charge": "must NOT include any error (a LOW_CONFIDENCE warning alone is a soft flag)",
    "name_variant": "must NOT include any error (a LOW_CONFIDENCE warning alone is a soft flag)",
    None: "must NOT include any error (a LOW_CONFIDENCE warning alone is a soft flag)",
}

# These three trap values are "clean documents" for false-flag purposes:
# nothing about them should ever trip a validation error.
_CLEAN_TRAPS = {None, "reverse_charge", "name_variant"}

_CREDIT_NOTE_FORBIDDEN_CODES = {
    "MATH_MISMATCH",
    "CREDIT_NOTE_NOT_NEGATIVE",
    "INVOICE_NEGATIVE_TOTAL",
}


@dataclass(frozen=True)
class TrapResult:
    file: str
    trap: str | None
    caught: bool
    is_false_flag: bool
    has_soft_flag: bool
    error_codes: frozenset[str]
    note: str


def evaluate_trap(file_name: str, trap: str | None, issues: list[Issue]) -> TrapResult:
    if trap not in TRAP_EXPECTATIONS:
        raise ValueError(
            f"{file_name}: unknown trap type {trap!r} — add it to "
            "TRAP_EXPECTATIONS in evals/scoring.py instead of guessing "
            "how it should score."
        )

    error_codes = frozenset(i.code for i in issues if i.severity == "error")
    all_codes = frozenset(i.code for i in issues)
    has_soft_flag = "LOW_CONFIDENCE" in {i.code for i in issues if i.severity == "warning"}

    if trap == "maths_error":
        caught = "MATH_MISMATCH" in error_codes
    elif trap == "no_due_date":
        caught = "MISSING_DUE_DATE" in all_codes
    elif trap == "duplicate_exact":
        caught = "DUPLICATE" in error_codes
    elif trap == "duplicate_near":
        caught = "AMOUNT_CONFLICT" in error_codes
    elif trap == "credit_note":
        caught = not (all_codes & _CREDIT_NOTE_FORBIDDEN_CODES)
    else:  # reverse_charge, name_variant, None
        caught = not error_codes

    is_false_flag = trap in _CLEAN_TRAPS and bool(error_codes)
    note = f"expected: {TRAP_EXPECTATIONS[trap]}; got issues={sorted(all_codes) or 'none'}"
    return TrapResult(
        file=file_name,
        trap=trap,
        caught=caught,
        is_false_flag=is_false_flag,
        has_soft_flag=has_soft_flag,
        error_codes=error_codes,
        note=note,
    )


def trap_misses(trap_results: list[TrapResult]) -> list[TrapResult]:
    return [t for t in trap_results if not t.caught]


def false_flags(trap_results: list[TrapResult]) -> tuple[list[TrapResult], dict[str, int]]:
    flagged = [t for t in trap_results if t.is_false_flag]
    tally: dict[str, int] = {}
    for result in flagged:
        for code in result.error_codes:
            tally[code] = tally.get(code, 0) + 1
    return flagged, tally


def soft_flag_count(trap_results: list[TrapResult]) -> int:
    return sum(1 for t in trap_results if t.has_soft_flag)
