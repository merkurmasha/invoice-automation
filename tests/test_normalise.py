"""Tests for src/suppliers/normalise.py. No API calls — pure string logic."""

from __future__ import annotations

from src.suppliers.normalise import normalize_supplier_name


def test_strips_inc_suffix_variants():
    assert normalize_supplier_name("Notion Labs Inc") == "notion labs"
    assert normalize_supplier_name("NOTION LABS") == "notion labs"
    assert normalize_supplier_name("Notion Labs, Inc") == "notion labs"
    assert normalize_supplier_name("Notion Labs, Inc.") == "notion labs"


def test_strips_sl_suffix_from_dotted_abbreviation():
    assert normalize_supplier_name("Barcelona Working Hub, S.L.") == "barcelona working hub"
    assert normalize_supplier_name("BARCELONA WORKING HUB SL") == "barcelona working hub"


def test_strips_sarl_and_gmbh():
    assert normalize_supplier_name("Studio Fonts France SARL") == "studio fonts france"
    assert normalize_supplier_name("Nordic Design Tools GmbH") == "nordic design tools"


def test_keeps_internal_word_that_looks_like_a_suffix():
    # "Co" sits in the middle of the name here, not at the end, so it
    # must not be stripped the way a trailing "Ltd" is.
    assert normalize_supplier_name("Pixel & Co Design Ltd") == "pixel & co design"


def test_different_suppliers_stay_different():
    assert normalize_supplier_name("Adobe Inc.") != normalize_supplier_name("Figma, Inc.")


def test_accented_characters_are_preserved_consistently():
    assert normalize_supplier_name("Café Central") == normalize_supplier_name("CAFÉ CENTRAL")
