"""Remembers invoices we've already seen, so the same bill doesn't get
paid or booked twice.

State is kept in memory (a nested dict) and can be loaded from / saved
to a JSON file, so a long-running process (or separate CLI runs) share
the same memory of what's already been processed.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.extract.schema import ExtractedInvoice
from src.suppliers.normalise import normalize_supplier_name

from .checks import Issue
from .config import AMOUNT_TOLERANCE

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "seen_invoices.json"


class DuplicateDetector:
    """Keyed on (normalised supplier, invoice number). Same key + same
    total => DUPLICATE. Same key + a different total => AMOUNT_CONFLICT
    (someone printed two different totals under one invoice number)."""

    def __init__(self, cache_path: Path | str = DEFAULT_CACHE_PATH) -> None:
        self.cache_path = Path(cache_path)
        # supplier_key -> invoice_key -> total
        self._seen: dict[str, dict[str, float]] = {}

    def load(self) -> None:
        if self.cache_path.exists():
            self._seen = json.loads(self.cache_path.read_text())
        else:
            self._seen = {}

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._seen, indent=2, sort_keys=True))

    @staticmethod
    def _invoice_key(invoice_number: str) -> str:
        return invoice_number.strip().lower()

    def check(self, extracted: ExtractedInvoice) -> list[Issue]:
        """Look up this invoice against what's already been seen.
        Doesn't change state — call register() separately for that."""
        if extracted.supplier is None or extracted.invoice_number is None:
            return []
        supplier_key = normalize_supplier_name(extracted.supplier)
        invoice_key = self._invoice_key(extracted.invoice_number)
        previous_total = self._seen.get(supplier_key, {}).get(invoice_key)
        if previous_total is None:
            return []

        if extracted.total is not None and abs(previous_total - extracted.total) <= AMOUNT_TOLERANCE:
            return [
                Issue(
                    "error",
                    "DUPLICATE",
                    f"{extracted.supplier} invoice {extracted.invoice_number} "
                    f"for {extracted.total} has already been seen.",
                )
            ]
        return [
            Issue(
                "error",
                "AMOUNT_CONFLICT",
                f"{extracted.supplier} invoice {extracted.invoice_number} was "
                f"seen before with total {previous_total}, but this time it's "
                f"{extracted.total}.",
            )
        ]

    def register(self, extracted: ExtractedInvoice) -> None:
        """Remember this invoice so future calls to check() can compare
        against it. Requires supplier, invoice_number, and total."""
        if extracted.supplier is None or extracted.invoice_number is None or extracted.total is None:
            return
        supplier_key = normalize_supplier_name(extracted.supplier)
        invoice_key = self._invoice_key(extracted.invoice_number)
        self._seen.setdefault(supplier_key, {})[invoice_key] = extracted.total
