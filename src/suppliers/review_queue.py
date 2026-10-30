"""An append-only log of things a human should look at: new suppliers,
possible supplier matches, low-confidence categorisations, and
validation issues.

This module has no "resolved" state — every row it can read back is an
open item. A human clears an item by removing its row from the CSV
file directly; nothing in this project does that automatically.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

FIELDNAMES = ["item_type", "file", "reason", "date"]

ITEM_TYPES = {
    "new_supplier",
    "possible_match",
    "low_confidence_category",
    "validation_issue",
}


class InvalidItemType(ValueError):
    pass


@dataclass(frozen=True)
class ReviewItem:
    item_type: str
    file: str
    reason: str
    date: str


def add_item(
    path: str | Path,
    item_type: str,
    file: str,
    reason: str,
    *,
    on_date: str | None = None,
) -> ReviewItem:
    if item_type not in ITEM_TYPES:
        raise InvalidItemType(
            f"Unknown review item type: {item_type!r}. Must be one of {sorted(ITEM_TYPES)}."
        )
    item = ReviewItem(
        item_type=item_type,
        file=file,
        reason=reason,
        date=on_date or date.today().isoformat(),
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "item_type": item.item_type,
                "file": item.file,
                "reason": item.reason,
                "date": item.date,
            }
        )
    return item


def list_open_items(path: str | Path) -> list[ReviewItem]:
    """Every row currently in the queue — see the module docstring for
    why there's no "open vs. closed" filtering here."""
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [ReviewItem(**row) for row in csv.DictReader(handle)]
