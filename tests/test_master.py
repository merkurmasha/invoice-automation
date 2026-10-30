"""Tests for src/suppliers/master.py. No API calls — pure deterministic
matching logic. Every test uses a throwaway CSV path (tmp_path), never
data/suppliers.csv.
"""

from __future__ import annotations

from src.suppliers.master import SupplierMaster


def _master(tmp_path, **kwargs):
    return SupplierMaster(tmp_path / "suppliers.csv", **kwargs)


def test_name_variants_collapse_to_same_supplier(tmp_path):
    master = _master(tmp_path)

    first = master.match_or_create("Notion Labs, Inc.")
    second = master.match_or_create("NOTION LABS")
    third = master.match_or_create("Notion Labs Inc")
    fourth = master.match_or_create("Notion Labs, Inc")

    assert first.status == "new"
    assert second.status == "exact"
    assert third.status == "exact"
    assert fourth.status == "exact"
    assert {first.supplier_id, second.supplier_id, third.supplier_id, fourth.supplier_id} == {
        first.supplier_id
    }
    assert len(master.suppliers) == 1


def test_different_suppliers_with_similar_names_stay_separate(tmp_path):
    # A realistic near-miss pair from data/synthetic/answer_key.json: two
    # genuinely different suppliers (electricity vs. insurance) that
    # happen to share "Costa Brava" in their printed names.
    master = _master(tmp_path)

    energia = master.match_or_create("Energia Costa Brava, S.L.")
    assegurances = master.match_or_create("Assegurances Costa Brava, S.L.")

    assert energia.status == "new"
    assert assegurances.status in {"new", "possible_match"}
    assert energia.supplier_id != assegurances.supplier_id
    assert len(master.suppliers) == 2


def test_fuzzy_score_at_merge_threshold_merges(tmp_path):
    master = _master(tmp_path, scorer=lambda a, b: 90.0)

    first = master.match_or_create("Adobe Inc.")
    second = master.match_or_create("Adobe Systems Software Ireland Ltd")

    assert second.status == "fuzzy_merge"
    assert second.supplier_id == first.supplier_id
    assert "Adobe Systems Software Ireland Ltd" in master.suppliers[0].aliases


def test_fuzzy_score_just_below_merge_threshold_is_possible_match_not_merged(tmp_path):
    master = _master(tmp_path, scorer=lambda a, b: 89.0)

    first = master.match_or_create("Adobe Inc.")
    second = master.match_or_create("Adobe Systems Software Ireland Ltd")

    assert second.status == "possible_match"
    # Never merged: a distinct supplier record, not a share of the first's id.
    assert second.supplier_id != first.supplier_id
    assert second.matched_against == "Adobe Inc."
    assert len(master.suppliers) == 2
    assert "Adobe Systems Software Ireland Ltd" not in master.suppliers[0].aliases


def test_fuzzy_score_at_review_threshold_is_possible_match(tmp_path):
    master = _master(tmp_path, scorer=lambda a, b: 80.0)

    first = master.match_or_create("Adobe Inc.")
    second = master.match_or_create("Some Other Supplier")

    assert second.status == "possible_match"
    assert second.supplier_id != first.supplier_id
    assert len(master.suppliers) == 2


def test_fuzzy_score_just_below_review_threshold_creates_new_supplier(tmp_path):
    master = _master(tmp_path, scorer=lambda a, b: 79.0)

    master.match_or_create("Adobe Inc.")
    second = master.match_or_create("Some Other Supplier")

    assert second.status == "new"
    assert len(master.suppliers) == 2
    assert master.suppliers[1].review_flag is True


def test_new_supplier_gets_review_flag(tmp_path):
    master = _master(tmp_path)

    result = master.match_or_create("Brand New Supplier S.L.")

    assert result.status == "new"
    created = next(s for s in master.suppliers if s.supplier_id == result.supplier_id)
    assert created.review_flag is True


def test_alias_recorded_on_exact_match(tmp_path):
    master = _master(tmp_path)
    master.match_or_create("Notion Labs, Inc.")

    master.match_or_create("NOTION LABS")

    assert master.suppliers[0].aliases == ["NOTION LABS"]


def test_alias_recorded_on_fuzzy_merge(tmp_path):
    master = _master(tmp_path, scorer=lambda a, b: 95.0)
    master.match_or_create("Adobe Inc.")

    master.match_or_create("Adobe Systems Software Ireland Ltd")

    assert master.suppliers[0].aliases == ["Adobe Systems Software Ireland Ltd"]


def test_never_merges_below_threshold_even_with_many_candidates(tmp_path):
    # A constant scorer of 85 (review_threshold <= 85 < merge_threshold)
    # means every name after the first scores as a "possible match"
    # against an existing supplier, but must still get its own new
    # record — never merged into that candidate's id.
    master = _master(tmp_path, scorer=lambda a, b: 85.0)
    first = master.match_or_create("Supplier One")
    assert first.status == "new"

    seen_ids = {first.supplier_id}
    for count, name in enumerate(["Supplier Two", "Supplier Three", "Supplier Four"], start=2):
        result = master.match_or_create(name)
        assert result.status == "possible_match"
        assert result.supplier_id not in seen_ids
        seen_ids.add(result.supplier_id)
        assert len(master.suppliers) == count


def test_master_persists_and_reloads_from_disk(tmp_path):
    path = tmp_path / "suppliers.csv"
    first_master = SupplierMaster(path)
    first_master.match_or_create("Figma, Inc.")

    second_master = SupplierMaster(path)
    result = second_master.match_or_create("FIGMA INC")

    assert result.status == "exact"
    assert len(second_master.suppliers) == 1
