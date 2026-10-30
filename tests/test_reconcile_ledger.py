"""Tests for src/reconcile/ledger.py: loading, dedup rules, and credit
notes. Uses the committed data/synthetic/ files (read-only - this
module never writes to them)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.reconcile import config
from src.reconcile.ledger import load_credit_notes, load_payable_obligations, load_receivable_obligations

ANSWER_KEY_ENTRIES = json.loads(Path(config.ANSWER_KEY_PATH).read_text())


def test_loading_leaves_the_committed_files_untouched():
    before = config.ANSWER_KEY_PATH.read_text()
    load_payable_obligations(config.ANSWER_KEY_PATH)
    assert config.ANSWER_KEY_PATH.read_text() == before


def test_duplicate_exact_and_duplicate_near_collapse_to_one_obligation():
    obligations = load_payable_obligations(config.ANSWER_KEY_PATH)
    by_number = {ob.invoice_number: ob for ob in obligations}

    # F-2026-009902 appears twice in the answer key with the SAME total
    # (duplicate_exact) - still only one obligation.
    assert sum(1 for ob in obligations if ob.invoice_number == "F-2026-009902") == 1
    assert by_number["F-2026-009902"].total == 198.39

    # BWH-202609-1103 appears twice with DIFFERENT totals (duplicate_near:
    # a bad near-duplicate reading) - the FIRST one seen wins, matching
    # the real pipeline's duplicate detector never letting a conflicting
    # second reading overwrite the real invoice.
    assert sum(1 for ob in obligations if ob.invoice_number == "BWH-202609-1103") == 1
    assert by_number["BWH-202609-1103"].total == 470.06


def test_photo_capture_of_an_already_listed_invoice_is_not_a_second_obligation():
    obligations = load_payable_obligations(config.ANSWER_KEY_PATH)
    # SFF-00021 is listed once under invoices/ and once under photos/ -
    # same real invoice, so only one obligation should exist.
    assert sum(1 for ob in obligations if ob.invoice_number == "SFF-00021") == 1


def test_credit_notes_are_never_loaded_as_a_payable_obligation():
    obligations = load_payable_obligations(config.ANSWER_KEY_PATH)
    assert all(ob.invoice_number != "ADB/2026/CN07704" for ob in obligations)


def test_credit_notes_keep_their_negative_sign():
    credit_notes = load_credit_notes(config.ANSWER_KEY_PATH)
    assert len(credit_notes) == 1
    note = credit_notes[0]
    assert note["invoice_number"] == "ADB/2026/CN07704"
    assert note["total"] < 0
    assert note["net"] < 0
    assert note["vat"] < 0


def test_receivables_load_with_no_payments_applied_yet():
    obligations = load_receivable_obligations(config.SALES_INVOICES_PATH)
    assert len(obligations) == 12
    first = next(ob for ob in obligations if ob.invoice_number == "CBS-2026-0001")
    assert first.amount_paid == 0.0
    assert first.amount_outstanding == first.total
    assert first.due_date == date(2026, 11, 5)
