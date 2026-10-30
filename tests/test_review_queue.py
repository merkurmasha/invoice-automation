"""Tests for src/suppliers/review_queue.py. Pure file I/O, no API calls,
always against a throwaway tmp_path file."""

from __future__ import annotations

import pytest

from src.suppliers import review_queue


def test_list_open_items_empty_when_file_does_not_exist(tmp_path):
    assert review_queue.list_open_items(tmp_path / "missing.csv") == []


def test_add_item_appends_and_list_reads_it_back(tmp_path):
    path = tmp_path / "review_queue.csv"

    review_queue.add_item(path, "new_supplier", "invoices/foo.pdf", "no match found", on_date="2026-10-30")

    items = review_queue.list_open_items(path)
    assert len(items) == 1
    assert items[0].item_type == "new_supplier"
    assert items[0].file == "invoices/foo.pdf"
    assert items[0].reason == "no match found"
    assert items[0].date == "2026-10-30"


def test_multiple_items_append_in_order(tmp_path):
    path = tmp_path / "review_queue.csv"

    review_queue.add_item(path, "new_supplier", "a.pdf", "reason a", on_date="2026-10-30")
    review_queue.add_item(path, "possible_match", "b.pdf", "reason b", on_date="2026-10-30")
    review_queue.add_item(path, "low_confidence_category", "c.pdf", "reason c", on_date="2026-10-30")

    items = review_queue.list_open_items(path)
    assert [i.item_type for i in items] == ["new_supplier", "possible_match", "low_confidence_category"]


def test_unknown_item_type_raises():
    with pytest.raises(review_queue.InvalidItemType):
        review_queue.add_item("/tmp/unused.csv", "not_a_real_type", "a.pdf", "reason")


def test_defaults_to_today_when_no_date_given(tmp_path):
    import datetime

    path = tmp_path / "review_queue.csv"
    review_queue.add_item(path, "validation_issue", "a.pdf", "reason")

    items = review_queue.list_open_items(path)
    assert items[0].date == datetime.date.today().isoformat()
