"""Normalise supplier names so differently-printed versions of the same
company compare equal.

Real invoices print a supplier's name inconsistently — different
capitalisation, trailing commas, or a legal suffix (Inc, Ltd, S.L.,
SARL, GmbH...) that may or may not be present. normalize_supplier_name()
strips that cosmetic variation down to a comparable key.

This is deliberately simple string cleanup, not fuzzy matching — it
only unifies different printings of the *same* legal name (e.g. "Notion
Labs Inc" vs "NOTION LABS"). It will not match a genuinely different
legal name for the same real-world company (e.g. a local subsidiary).
Phase 4 (reconciliation across the ledger) is expected to import this
function and layer fuzzy matching (rapidfuzz) on top for that case.
"""

from __future__ import annotations

import re

# Suffix tokens are checked after lowercasing and stripping punctuation,
# so "S.L." and "SARL" become the single tokens "sl" and "sarl" here.
_LEGAL_SUFFIXES = {"inc", "ltd", "llc", "sl", "sa", "sarl", "gmbh", "corp"}

# Drop anything that isn't a letter/digit/underscore, whitespace, or "&"
# (kept because it can be a meaningful part of a name, e.g. "Pixel & Co").
_PUNCTUATION_RE = re.compile(r"[^\w\s&]", re.UNICODE)


def normalize_supplier_name(name: str) -> str:
    """Return a lowercase, punctuation-free, legal-suffix-free key for a
    supplier name, so that e.g. "Notion Labs, Inc." and "NOTION LABS"
    normalise to the same string."""
    text = _PUNCTUATION_RE.sub("", name.lower())
    tokens = text.split()
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)
