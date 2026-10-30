"""Matches bank statement lines to invoices.

Plain deterministic code per CLAUDE.md - no LLM call anywhere in this
file. See config.py's module docstring for how the 0-100 score is
built; this file implements that scoring and the decision rules on top
of it (auto-match / possible match / partial / combo / ambiguous /
unmatched).

Four independent signals, reused for every candidate:
  - amount    (_amount_signal)
  - reference (_reference_signal) - the invoice number in the bank text
  - name      (_name_signal) - fuzzy supplier/customer name, reusing
               src/suppliers/normalise.py
  - date      (_date_signal) - payment plausibility vs issue/due date

A bank line is scored against every open invoice of the matching kind
(negative amount -> payable, positive -> receivable) and currency
(config.BANK_CURRENCY only - no FX conversion). The best-scoring
candidate decides what happens to the line; see decide_bank_line()'s
docstring for the exact rules.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from pathlib import Path

from rapidfuzz import fuzz

from src.suppliers.normalise import normalize_supplier_name

from . import config
from .ledger import PAYABLE, RECEIVABLE, Obligation

_REFERENCE_NOISE_RE = re.compile(r"[^0-9a-zA-Z]")


@dataclass(frozen=True)
class BankLine:
    line_id: int
    txn_date: date
    description: str
    amount: float  # negative = outgoing (payable), positive = incoming (receivable)
    balance: float = 0.0


@dataclass(frozen=True)
class ScoreResult:
    score: float
    amount_label: str  # "full" or "partial"
    reference_label: str  # "exact" | "fuzzy" | "none"
    name_ratio: float  # 0-100 raw rapidfuzz ratio, for reporting
    date_label: str  # "in_window" | "outside_window" | "no_due_date" | "implausible"
    reason: str


@dataclass
class MatchDecision:
    category: str  # "auto" | "possible" | "partial" | "combo" | "ambiguous" | "unmatched"
    bank_line: BankLine
    invoice_numbers: list[str] = field(default_factory=list)
    score: float | None = None
    reason: str = ""
    applied: bool = False


def load_bank_statement(path: str | Path) -> list[BankLine]:
    lines: list[BankLine] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for i, row in enumerate(csv.DictReader(handle)):
            lines.append(
                BankLine(
                    line_id=i,
                    txn_date=date.fromisoformat(row["date"]),
                    description=row["description"],
                    amount=float(row["amount"]),
                    balance=float(row["balance"]) if row.get("balance") else 0.0,
                )
            )
    return lines


def _normalize_reference_text(text: str) -> str:
    return _REFERENCE_NOISE_RE.sub("", text).lower()


def _amount_signal(bank_amount_abs: float, outstanding: float) -> tuple[float, str | None]:
    """Returns (points, label). label is None when this bank line can't
    be explained by this one obligation alone (too big, or already paid)."""
    if outstanding <= 0:
        return 0.0, None
    if abs(bank_amount_abs - outstanding) <= config.AMOUNT_TOLERANCE:
        return config.AMOUNT_FULL_POINTS, "full"
    if bank_amount_abs < outstanding - config.AMOUNT_TOLERANCE:
        return config.AMOUNT_PARTIAL_POINTS, "partial"
    return 0.0, None


def _reference_signal(invoice_number: str, description: str) -> tuple[float, str]:
    norm_inv = _normalize_reference_text(invoice_number)
    norm_desc = _normalize_reference_text(description)
    if norm_inv and norm_inv in norm_desc:
        return config.REFERENCE_EXACT_POINTS, "exact"
    ratio = fuzz.partial_ratio(norm_inv, norm_desc) if norm_inv else 0.0
    if ratio >= config.REFERENCE_FUZZY_THRESHOLD:
        return config.REFERENCE_FUZZY_POINTS, "fuzzy"
    return 0.0, "none"


def _name_signal(counterparty: str, description: str) -> tuple[float, float]:
    """Returns (points, raw_ratio). Uses token_set_ratio, because bank
    reference text often keeps only SOME words of a multi-word name
    (e.g. "TRANSFERENCIA ENERGIA" for "Energia Costa Brava, S.L.") -
    token_set_ratio ignores word order and extra/missing words, so it
    rewards the words that ARE shared without being dragged down by
    the ones that aren't. Below NAME_FLOOR_RATIO the ratio is treated
    as coincidental noise, not a real signal, and scores zero."""
    ratio = fuzz.token_set_ratio(normalize_supplier_name(counterparty), normalize_supplier_name(description))
    if ratio < config.NAME_FLOOR_RATIO:
        return 0.0, ratio
    points = round(ratio / 100 * config.NAME_MAX_POINTS, 2)
    return points, ratio


def _date_signal(payment_date: date, issue_date: date, due_date: date | None) -> tuple[float, str]:
    if payment_date < issue_date:
        return config.DATE_IMPLAUSIBLE_POINTS, "implausible"
    if due_date is None:
        return config.DATE_NO_DUE_DATE_POINTS, "no_due_date"
    if abs((payment_date - due_date).days) <= config.DATE_WINDOW_DAYS:
        return config.DATE_IN_WINDOW_POINTS, "in_window"
    return config.DATE_PLAUSIBLE_OUTSIDE_WINDOW_POINTS, "outside_window"


def _build_reason(
    obligation: Obligation,
    line: BankLine,
    amount_label: str,
    reference_label: str,
    name_ratio: float,
    date_label: str,
    score: float,
) -> str:
    parts = []
    if amount_label == "full":
        parts.append(f"amount matches invoice {obligation.invoice_number} in full ({abs(line.amount):.2f})")
    else:
        parts.append(
            f"amount ({abs(line.amount):.2f}) is a partial payment toward invoice "
            f"{obligation.invoice_number} (outstanding {obligation.amount_outstanding:.2f})"
        )
    if reference_label == "exact":
        parts.append("the invoice number appears in the bank reference text")
    elif reference_label == "fuzzy":
        parts.append("the invoice number closely matches the bank reference text")
    if name_ratio >= 50:
        parts.append(f"the name matches the reference text ({name_ratio:.0f}% similarity)")
    if date_label == "in_window":
        parts.append("the payment date is close to the due date")
    elif date_label == "no_due_date":
        parts.append("there's no due date on file, but the payment is on/after the issue date")
    elif date_label == "outside_window":
        parts.append("the payment date is plausible but far from the due date")
    elif date_label == "implausible":
        parts.append("the payment date is BEFORE the invoice was issued, which is unusual")
    return f"Score {score:.0f}/100: " + "; ".join(parts) + "."


def score_candidate(line: BankLine, obligation: Obligation) -> ScoreResult | None:
    """Scores one bank line against one obligation. Returns None if this
    obligation can't be a single-invoice candidate for this line at all
    (amount too large, or the obligation is already fully paid)."""
    bank_amount_abs = round(abs(line.amount), 2)
    amount_points, amount_label = _amount_signal(bank_amount_abs, obligation.amount_outstanding)
    if amount_label is None:
        return None

    reference_points, reference_label = _reference_signal(obligation.invoice_number, line.description)
    name_points, name_ratio = _name_signal(obligation.counterparty, line.description)
    date_points, date_label = _date_signal(line.txn_date, obligation.issue_date, obligation.due_date)

    score = round(min(100.0, amount_points + reference_points + name_points + date_points), 2)
    reason = _build_reason(obligation, line, amount_label, reference_label, name_ratio, date_label, score)
    return ScoreResult(
        score=score,
        amount_label=amount_label,
        reference_label=reference_label,
        name_ratio=name_ratio,
        date_label=date_label,
        reason=reason,
    )


def _decide_single(line: BankLine, pool: list[Obligation]) -> MatchDecision | None:
    """Scores every obligation in `pool` against `line` and decides what
    to do with the single best candidate. Returns None if no candidate
    reaches POSSIBLE_MATCH_THRESHOLD at all (so the caller can fall back
    to combo-matching).

    Partial payments are always applied-and-reported (never silently
    "auto-matched") as long as they clear POSSIBLE_MATCH_THRESHOLD - a
    partial payment always leaves a balance a human should see, so it's
    never treated as fully resolved regardless of how confident the
    match is. Full-amount matches use the normal auto/possible bands.
    """
    scored = [(ob, score_candidate(line, ob)) for ob in pool]
    scored = [(ob, s) for ob, s in scored if s is not None]
    if not scored:
        return None
    scored.sort(key=lambda t: t[1].score, reverse=True)

    best_ob, best = scored[0]
    if best.score < config.POSSIBLE_MATCH_THRESHOLD:
        return None

    if len(scored) > 1:
        second_ob, second = scored[1]
        if second.score >= config.POSSIBLE_MATCH_THRESHOLD and (best.score - second.score) <= config.AMBIGUITY_MARGIN:
            return MatchDecision(
                category="ambiguous",
                bank_line=line,
                invoice_numbers=[best_ob.invoice_number, second_ob.invoice_number],
                score=best.score,
                reason=(
                    f"Two equally good candidates for this line: {best_ob.invoice_number} "
                    f"(score {best.score:.0f}) and {second_ob.invoice_number} (score {second.score:.0f}) "
                    "- not matched automatically, needs a human to pick."
                ),
                applied=False,
            )

    if best.amount_label == "partial":
        best_ob.apply_payment(abs(line.amount), line.line_id, line.txn_date)
        return MatchDecision(
            category="partial",
            bank_line=line,
            invoice_numbers=[best_ob.invoice_number],
            score=best.score,
            reason=best.reason,
            applied=True,
        )

    if best.score >= config.AUTO_MATCH_THRESHOLD:
        best_ob.apply_payment(abs(line.amount), line.line_id, line.txn_date)
        return MatchDecision(
            category="auto",
            bank_line=line,
            invoice_numbers=[best_ob.invoice_number],
            score=best.score,
            reason=best.reason,
            applied=True,
        )

    return MatchDecision(
        category="possible",
        bank_line=line,
        invoice_numbers=[best_ob.invoice_number],
        score=best.score,
        reason=best.reason,
        applied=False,
    )


def _decide_combo(line: BankLine, pool: list[Obligation]) -> MatchDecision | None:
    """Tries to explain one bank line as the sum of 2+ open invoices for
    the same counterparty (one payment covering several invoices).
    Always applied-and-reported, like a partial payment, since it's
    worth a human's attention even when confidently identified."""
    bank_amount_abs = round(abs(line.amount), 2)
    open_pool = [ob for ob in pool if ob.amount_outstanding > 0]

    found: list[tuple[list[Obligation], float]] = []
    for size in range(2, config.MAX_COMBO_SIZE + 1):
        for combo in combinations(open_pool, size):
            total = round(sum(ob.amount_outstanding for ob in combo), 2)
            if abs(total - bank_amount_abs) > config.AMOUNT_TOLERANCE:
                continue
            if not all(line.txn_date >= ob.issue_date for ob in combo):
                continue

            name_ratios = [
                fuzz.token_set_ratio(normalize_supplier_name(ob.counterparty), normalize_supplier_name(line.description))
                for ob in combo
            ]
            ref_hits = sum(
                1
                for ob in combo
                if _normalize_reference_text(ob.invoice_number) in _normalize_reference_text(line.description)
            )
            avg_name = sum(name_ratios) / len(name_ratios)
            combo_score = min(100.0, (avg_name / 100 * 60) + (ref_hits / size * 40))
            if combo_score >= config.POSSIBLE_MATCH_THRESHOLD:
                found.append((list(combo), combo_score))

    if not found:
        return None

    found.sort(key=lambda t: t[1], reverse=True)
    best_combo, best_score = found[0]

    if len(found) > 1:
        second_combo, second_score = found[1]
        if second_score >= config.POSSIBLE_MATCH_THRESHOLD and (best_score - second_score) <= config.AMBIGUITY_MARGIN:
            return MatchDecision(
                category="ambiguous",
                bank_line=line,
                invoice_numbers=[ob.invoice_number for ob in best_combo] + [ob.invoice_number for ob in second_combo],
                score=best_score,
                reason="Two equally good combinations of invoices sum to this payment - not matched automatically.",
                applied=False,
            )

    for ob in best_combo:
        ob.apply_payment(ob.amount_outstanding, line.line_id, line.txn_date)

    invoice_list = ", ".join(ob.invoice_number for ob in best_combo)
    reason = (
        f"Score {best_score:.0f}/100: this payment ({bank_amount_abs:.2f}) equals the sum of "
        f"{len(best_combo)} open invoices ({invoice_list})."
    )
    return MatchDecision(
        category="combo",
        bank_line=line,
        invoice_numbers=[ob.invoice_number for ob in best_combo],
        score=best_score,
        reason=reason,
        applied=True,
    )


def decide_bank_line(line: BankLine, obligations: list[Obligation]) -> MatchDecision:
    """Decides what one bank line matches, trying single-invoice matching
    first and falling back to combo-matching (several invoices summing
    to this one payment) if nothing single-invoice clears the possible
    threshold. Mutates the winning obligation(s)' amount_paid in place
    when a decision is applied (auto / partial / combo)."""
    kind = PAYABLE if line.amount < 0 else RECEIVABLE
    pool = [
        ob
        for ob in obligations
        if ob.kind == kind and ob.currency == config.BANK_CURRENCY and ob.amount_outstanding > 0
    ]

    decision = _decide_single(line, pool)
    if decision is not None:
        return decision

    decision = _decide_combo(line, pool)
    if decision is not None:
        return decision

    return MatchDecision(
        category="unmatched",
        bank_line=line,
        invoice_numbers=[],
        score=None,
        reason="No open invoice (or combination of invoices) explains this amount.",
        applied=False,
    )


def reconcile(bank_lines: list[BankLine], obligations: list[Obligation]) -> list[MatchDecision]:
    """Reconciles every bank line against `obligations`, in date order
    (so a recurring same-amount invoice is matched against the one that
    actually existed yet, and later invoices' payments never get
    consumed by an earlier line). Each bank line produces exactly one
    MatchDecision and is only ever used once - obligations are mutated
    in place as lines are matched, so later lines see updated balances.
    """
    ordered = sorted(bank_lines, key=lambda line: (line.txn_date, line.line_id))
    return [decide_bank_line(line, obligations) for line in ordered]
