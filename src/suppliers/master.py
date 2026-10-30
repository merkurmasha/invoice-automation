"""Match a printed supplier name to an existing supplier, or create a new
one. Plain deterministic code — no LLM involved, see CLAUDE.md.

Matching happens in two steps:

1. Exact match after normalize_supplier_name() — cosmetic variants of
   the *same* printed name ("Notion Labs Inc" vs "NOTION LABS" vs
   "Notion Labs, Inc."). See normalise.py's docstring.
2. Fuzzy match (rapidfuzz) against every known supplier's canonical
   name and aliases, for genuinely different-looking printings of the
   same real company (e.g. "Adobe Inc." vs "ADOBE SYSTEMS SOFTWARE
   IRELAND LTD") — the case normalize_supplier_name() deliberately
   leaves alone, and that phase 3 flagged as phase 4/5's job.
     - score >= merge_threshold (default 90): merge, and record the
       printed name as a new alias.
     - review_threshold (default 80) <= score < merge_threshold:
       reported as a "possible match" for a human to confirm — never
       merged automatically.
     - score < review_threshold: a new supplier, flagged for review.

This module never touches the review queue itself (see
review_queue.py) — it only returns a MatchResult describing what
happened. Deciding whether that result is worth a review-queue entry is
the caller's job (see evals/run_supplier_eval.py), which keeps this
module simple to test in isolation.
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from rapidfuzz import fuzz

from .normalise import normalize_supplier_name

FIELDNAMES = [
    "supplier_id",
    "canonical_name",
    "aliases",
    "country",
    "review_flag",
    "first_seen",
    "last_seen",
]

# Aliases are stored as one CSV cell, separated by this character (none
# of the supplier names in this project contain it).
ALIAS_SEPARATOR = "|"

DEFAULT_MERGE_THRESHOLD = 90.0
DEFAULT_REVIEW_THRESHOLD = 80.0


@dataclass
class Supplier:
    supplier_id: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    country: str | None = None
    review_flag: bool = False
    first_seen: str | None = None
    last_seen: str | None = None

    def all_names(self) -> list[str]:
        return [self.canonical_name, *self.aliases]

    def to_row(self) -> dict:
        return {
            "supplier_id": self.supplier_id,
            "canonical_name": self.canonical_name,
            "aliases": ALIAS_SEPARATOR.join(self.aliases),
            "country": self.country or "",
            "review_flag": "true" if self.review_flag else "false",
            "first_seen": self.first_seen or "",
            "last_seen": self.last_seen or "",
        }

    @classmethod
    def from_row(cls, row: dict) -> "Supplier":
        aliases = [a for a in row["aliases"].split(ALIAS_SEPARATOR) if a]
        return cls(
            supplier_id=row["supplier_id"],
            canonical_name=row["canonical_name"],
            aliases=aliases,
            country=row["country"] or None,
            review_flag=row["review_flag"].strip().lower() == "true",
            first_seen=row["first_seen"] or None,
            last_seen=row["last_seen"] or None,
        )


@dataclass(frozen=True)
class MatchResult:
    supplier_id: str
    canonical_name: str
    # "exact": same printed name after normalising — matched an existing supplier.
    # "fuzzy_merge": different printing, fuzzy score >= merge_threshold — matched an existing supplier.
    # "possible_match": fuzzy score in [review_threshold, merge_threshold) — a NEW
    #     supplier was created (see match_or_create), and matched_against names
    #     the existing supplier a human should check it against.
    # "new": no candidate scored >= review_threshold — a new supplier was created.
    status: str
    score: float | None
    matched_against: str | None = None


class SupplierMaster:
    """Backed by a CSV file at `path` (columns: FIELDNAMES above). Tests
    and the eval harness must point this at a temporary file — never
    data/suppliers.csv."""

    def __init__(
        self,
        path: str | Path,
        *,
        merge_threshold: float = DEFAULT_MERGE_THRESHOLD,
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
        scorer: Callable[[str, str], float] = fuzz.WRatio,
    ) -> None:
        if review_threshold > merge_threshold:
            raise ValueError("review_threshold cannot be above merge_threshold")
        self.path = Path(path)
        self.merge_threshold = merge_threshold
        self.review_threshold = review_threshold
        self._scorer = scorer
        self.suppliers: list[Supplier] = self._load()

    def _load(self) -> list[Supplier]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as handle:
            return [Supplier.from_row(row) for row in csv.DictReader(handle)]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            for supplier in self.suppliers:
                writer.writerow(supplier.to_row())

    def _best_fuzzy_match(
        self, printed_name: str
    ) -> tuple[Supplier | None, float, str | None]:
        # Score against NORMALISED names, not the raw printed strings.
        # Comparing raw strings lets a fuzzy scorer's substring/partial
        # heuristics fire on coincidental overlap (e.g. a shared "&" or
        # a generic word) between two genuinely unrelated suppliers —
        # found by running this against the real synthetic dataset,
        # where it merged "Assessoria Fiscal Puig & Associats" (an
        # accountant) with "Pixel & Co Design Ltd" (a design studio).
        # Normalising first strips exactly the cosmetic noise
        # (casing, punctuation, legal suffixes) that normalize_supplier_name()
        # already handles, leaving the fuzzy scorer to do the one job
        # it's actually needed for: different-looking printings of the
        # *same* legal name, like "Adobe Inc." vs "ADOBE SYSTEMS
        # SOFTWARE IRELAND LTD".
        normalized_printed = normalize_supplier_name(printed_name)
        best_supplier: Supplier | None = None
        best_score = 0.0
        best_name: str | None = None
        for supplier in self.suppliers:
            for candidate in supplier.all_names():
                score = self._scorer(normalized_printed, normalize_supplier_name(candidate))
                if score > best_score:
                    best_supplier, best_score, best_name = supplier, score, candidate
        return best_supplier, best_score, best_name

    def match_or_create(
        self,
        printed_name: str,
        *,
        seen_on: str | None = None,
        country: str | None = None,
    ) -> MatchResult:
        seen_on = seen_on or date.today().isoformat()
        normalized = normalize_supplier_name(printed_name)

        for supplier in self.suppliers:
            if any(
                normalize_supplier_name(name) == normalized
                for name in supplier.all_names()
            ):
                self._touch(supplier, printed_name, seen_on, country)
                return MatchResult(
                    supplier.supplier_id, supplier.canonical_name, "exact", 100.0
                )

        best_supplier, best_score, best_name = self._best_fuzzy_match(printed_name)

        if best_supplier is not None and best_score >= self.merge_threshold:
            self._touch(best_supplier, printed_name, seen_on, country)
            return MatchResult(
                best_supplier.supplier_id,
                best_supplier.canonical_name,
                "fuzzy_merge",
                best_score,
                matched_against=best_name,
            )

        # Below merge_threshold: never merge, full stop. This printed name
        # always gets its own new supplier record — otherwise a
        # "possible match" with no record of its own would have nowhere
        # to live, and reusing the *other* supplier's id here (an
        # earlier version of this code did) quietly behaves like a
        # merge to any caller that just reads supplier_id off the
        # result, without ever touching this supplier's own row.
        new_supplier = Supplier(
            supplier_id=f"SUP-{uuid.uuid4().hex[:8]}",
            canonical_name=printed_name,
            aliases=[],
            country=country,
            review_flag=True,
            first_seen=seen_on,
            last_seen=seen_on,
        )
        self.suppliers.append(new_supplier)
        self.save()

        if best_supplier is not None and best_score >= self.review_threshold:
            # Flagged for a human to confirm whether this is actually
            # the same supplier as best_supplier — not merged.
            return MatchResult(
                new_supplier.supplier_id,
                new_supplier.canonical_name,
                "possible_match",
                best_score,
                matched_against=best_supplier.canonical_name,
            )

        return MatchResult(new_supplier.supplier_id, new_supplier.canonical_name, "new", None)

    def _touch(
        self,
        supplier: Supplier,
        printed_name: str,
        seen_on: str,
        country: str | None,
    ) -> None:
        if printed_name != supplier.canonical_name and printed_name not in supplier.aliases:
            supplier.aliases.append(printed_name)
        if country and not supplier.country:
            supplier.country = country
        if supplier.first_seen is None or seen_on < supplier.first_seen:
            supplier.first_seen = seen_on
        if supplier.last_seen is None or seen_on > supplier.last_seen:
            supplier.last_seen = seen_on
        self.save()
