"""Settings for the validation module. Constants only — no logic here."""

from src.extract.config import CONFIDENCE_THRESHOLD

# How far net + vat is allowed to drift from the printed total before
# it's flagged as a maths error. Covers float rounding, not real errors.
AMOUNT_TOLERANCE = 0.01

# Fields every invoice must have to be usable downstream. due_date is
# deliberately not here — a missing due_date is only a warning.
REQUIRED_FIELDS = ["supplier", "invoice_number", "issue_date", "currency", "total"]

__all__ = ["AMOUNT_TOLERANCE", "CONFIDENCE_THRESHOLD", "REQUIRED_FIELDS"]
