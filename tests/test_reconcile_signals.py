"""Tests for each of src/reconcile/match.py's four scoring signals on
its own: amount, reference, name, date. No API calls - plain
deterministic code per CLAUDE.md."""

from __future__ import annotations

from datetime import date

from src.reconcile import config
from src.reconcile.match import _amount_signal, _date_signal, _name_signal, _reference_signal


# --- amount ---------------------------------------------------------------


def test_amount_full_within_tolerance():
    points, label = _amount_signal(100.00, 100.005)
    assert label == "full"
    assert points == config.AMOUNT_FULL_POINTS


def test_amount_partial_when_less_than_outstanding():
    points, label = _amount_signal(50.0, 100.0)
    assert label == "partial"
    assert points == config.AMOUNT_PARTIAL_POINTS


def test_amount_mismatch_when_more_than_outstanding():
    points, label = _amount_signal(150.0, 100.0)
    assert label is None
    assert points == 0.0


def test_amount_mismatch_when_already_fully_paid():
    points, label = _amount_signal(10.0, 0.0)
    assert label is None


# --- reference --------------------------------------------------------------


def test_reference_exact_tolerates_case_spaces_dashes():
    points, label = _reference_signal("ADB/2026/07701", "PAGO FRA adb 2026 07701")
    assert label == "exact"
    assert points == config.REFERENCE_EXACT_POINTS


def test_reference_none_when_absent():
    points, label = _reference_signal("ADB/2026/07701", "TRANSFERENCIA ADOBE")
    assert label == "none"
    assert points == 0.0


def test_reference_fuzzy_for_near_miss():
    # One character off from the real invoice number - close enough to
    # be a typo, not an unrelated reference.
    points, label = _reference_signal("SFF-00021", "PAGO FACTURA SFF-00022 GRACIAS")
    assert label == "fuzzy"
    assert points == config.REFERENCE_FUZZY_POINTS


# --- name -------------------------------------------------------------------


def test_name_matches_full_canonical_name():
    points, ratio = _name_signal("Botiga Natura Barcelona", "BOTIGA NATURA BARCELONA")
    assert ratio == 100.0
    assert points == config.NAME_MAX_POINTS


def test_name_rewards_shared_words_even_with_missing_ones():
    # Bank text keeps only ONE word of a multi-word name - should still
    # score as a real (if partial) signal, not zero.
    points, ratio = _name_signal("Energia Costa Brava, S.L.", "TRANSFERENCIA ENERGIA")
    assert ratio >= config.NAME_FLOOR_RATIO
    assert points > 0.0


def test_name_floors_coincidental_similarity_to_zero():
    points, ratio = _name_signal("Impremta Girona, S.L.", "COMISSIONS BANCARIES TRIMESTRALS")
    assert ratio < config.NAME_FLOOR_RATIO
    assert points == 0.0


# --- date --------------------------------------------------------------------


def test_date_in_window_of_due_date():
    points, label = _date_signal(date(2026, 8, 28), date(2026, 8, 15), date(2026, 8, 30))
    assert label == "in_window"
    assert points == config.DATE_IN_WINDOW_POINTS


def test_date_outside_window_but_still_after_issue():
    # Paid well after the invoice was issued, but nowhere near its due
    # date - plausible (on/after issue) but not "on time".
    points, label = _date_signal(date(2026, 6, 1), date(2026, 1, 1), date(2026, 1, 15))
    assert label == "outside_window"
    assert points == config.DATE_PLAUSIBLE_OUTSIDE_WINDOW_POINTS


def test_date_no_due_date_is_ok_as_long_as_on_or_after_issue():
    points, label = _date_signal(date(2026, 7, 28), date(2026, 7, 20), None)
    assert label == "no_due_date"
    assert points == config.DATE_NO_DUE_DATE_POINTS


def test_date_before_issue_is_implausible():
    points, label = _date_signal(date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1))
    assert label == "implausible"
    assert points == 0.0
