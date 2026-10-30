"""Settings for the bank-reconciliation module.

Styled the same way as the other modules' config.py files (one place for
every tunable number), kept as its own file so this phase never edits
src/receivables/ or src/suppliers/ to add its settings.

Everything here is plain deterministic code per CLAUDE.md — reconciling
a bank line against an invoice needs no LLM call at all.

--- How the match score is built -----------------------------------------

Every bank line is scored against every still-open invoice it could
plausibly be paying, using four independent signals. Each signal
contributes points; the points are added up into one 0-100 score:

  - amount:    the bank line's amount is within AMOUNT_TOLERANCE of the
               invoice's remaining balance ("full"), or less than it
               ("partial"). A bank line for MORE than an invoice's
               remaining balance never scores that invoice at all - a
               single payment can't overpay one invoice and still count
               as "matching" it (see match.py's combo-matching for the
               "one payment covers several invoices" case instead).
  - reference: the invoice number appears in the bank line's reference
               text, tolerating case/spaces/dashes ("exact"), or is a
               close fuzzy match ("fuzzy") for typos/partial references.
  - name:      the supplier/customer name fuzzy-matches the reference
               text (rapidfuzz, reusing src/suppliers/normalise.py).
  - date:      the payment date is on or after the invoice's issue date,
               and close to its due date.

A bank line with an exact reference and the right amount auto-matches
even with no name text at all (REFERENCE_EXACT + AMOUNT_FULL +
DATE_IN_WINDOW = 85 = AUTO_MATCH_THRESHOLD) - a specific invoice number
appearing verbatim is strong evidence on its own. But amount + a decent
name match, with NO reference number, tops out at 65 - deliberately
below AUTO_MATCH_THRESHOLD, so a recurring bill at a fixed amount with
no invoice number in the bank text always gets a human's eyes on it
before being treated as settled (see match.py's PARTIAL_AMOUNT_POINTS
docstring for why partial payments are always surfaced too, regardless
of score).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The bank account this statement is for is EUR-only - no FX conversion
# is in scope, so invoices in another currency are never matching
# candidates (the generator deliberately never pays them; see
# src/synthetic/sales_bank.py's UNPAID_SUPPLIER_STEMS comment).
BANK_CURRENCY = "EUR"

BANK_STATEMENT_PATH = PROJECT_ROOT / "data" / "synthetic" / "bank" / "statement.csv"
ANSWER_KEY_PATH = PROJECT_ROOT / "data" / "synthetic" / "answer_key.json"
SALES_INVOICES_PATH = PROJECT_ROOT / "data" / "synthetic" / "sales_invoices.csv"

# Two amounts are "the same" within one cent.
AMOUNT_TOLERANCE = 0.01

# Score bands.
AUTO_MATCH_THRESHOLD = 85.0
POSSIBLE_MATCH_THRESHOLD = 60.0

# If the best and second-best candidate for one bank line are within
# this many points of each other (and both clear POSSIBLE_MATCH_THRESHOLD),
# neither is matched - the line goes to exceptions as "ambiguous"
# instead of guessing which one is right.
AMBIGUITY_MARGIN = 3.0

# --- Signal point values ---------------------------------------------------

AMOUNT_FULL_POINTS = 40.0
AMOUNT_PARTIAL_POINTS = 28.0

REFERENCE_EXACT_POINTS = 30.0
REFERENCE_FUZZY_POINTS = 15.0
# rapidfuzz partial_ratio (0-100) above this counts as a fuzzy reference match.
REFERENCE_FUZZY_THRESHOLD = 85.0

NAME_MAX_POINTS = 40.0
# rapidfuzz token_set_ratio below this counts as noise, not a signal -
# two genuinely unrelated short strings often still score 20-45 on pure
# chance (shared short words, letters), so a floor is needed to stop
# that noise from nudging an unrelated invoice into "partial" or
# "possible" territory just because its amount happened to fit too.
NAME_FLOOR_RATIO = 48.0

DATE_IN_WINDOW_POINTS = 15.0
DATE_PLAUSIBLE_OUTSIDE_WINDOW_POINTS = 6.0
DATE_NO_DUE_DATE_POINTS = 15.0
DATE_IMPLAUSIBLE_POINTS = 0.0

# How many days either side of the due date still count as "on time"
# for the date signal. Wide enough to cover suppliers who auto-charge
# on the issue date itself, up to ~30 days before a NET-30 due date.
DATE_WINDOW_DAYS = 35

# Combo matching ("one payment covers several invoices"): how many open
# invoices for the same counterparty we're willing to try summing
# together to explain one bank line. Kept small on purpose - a bank line
# that happens to equal the sum of a dozen unrelated invoices is a
# coincidence, not a combo payment.
MAX_COMBO_SIZE = 3
