"""Tests for scripts/process_invoice.py. Per CLAUDE.md, no real Claude
API calls — a fake client returns canned responses in call order
(extraction first, then categorisation), same pattern as
tests/test_extract.py and tests/test_categorise.py.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from scripts import process_invoice as process_invoice_module
from src.extract import extract as extract_module
from src.suppliers import categorise as categorise_module
from src.suppliers.master import FIELDNAMES

VALID_EXTRACT_RAW = {
    "supplier": "Notion Labs, Inc.",
    "invoice_number": "NL-2026-04404",
    "issue_date": "2026-10-03",
    "due_date": "2026-11-02",
    "currency": "EUR",
    "net": 100.0,
    "vat": 21.0,
    "total": 121.0,
    "document_type": "invoice",
    "language": "en",
    "confidence": {
        "supplier": 0.98,
        "invoice_number": 0.97,
        "issue_date": 0.95,
        "due_date": 0.95,
        "currency": 0.99,
        "net": 0.9,
        "vat": 0.9,
        "total": 0.9,
        "document_type": 0.99,
        "language": 0.9,
    },
}

MISSING_SUPPLIER_EXTRACT_RAW = {**VALID_EXTRACT_RAW, "supplier": None, "confidence": {**VALID_EXTRACT_RAW["confidence"], "supplier": 0.0}}

HIGH_CONFIDENCE_CATEGORY_RAW = {
    "category_code": "software_subscriptions",
    "confidence": 0.95,
    "reason": "Notion is a SaaS productivity tool.",
}

LOW_CONFIDENCE_CATEGORY_RAW = {
    "category_code": "other",
    "confidence": 0.3,
    "reason": "Not enough information to tell what this expense is for.",
}


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, tool_input: dict) -> None:
        self.input = tool_input


class _FakeUsage:
    def __init__(self) -> None:
        self.input_tokens = 100
        self.output_tokens = 50


class _FakeResponse:
    def __init__(self, tool_input: dict) -> None:
        self.content = [_FakeToolUseBlock(tool_input)]
        self.usage = _FakeUsage()


class _FakeMessages:
    def __init__(self, client: "FakeClient") -> None:
        self._client = client

    def create(self, **kwargs):
        self._client.calls += 1
        item = self._client.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _FakeResponse(item)


class FakeClient:
    """Stands in for anthropic.Anthropic: returns queued responses in
    order — the extraction call first, then the categorisation call."""

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.messages = _FakeMessages(self)


@pytest.fixture(autouse=True)
def isolated_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_module, "CACHE_DIR", tmp_path / "extract_cache")
    monkeypatch.setattr(categorise_module, "CACHE_DIR", tmp_path / "categorise_cache")


@pytest.fixture
def sample_file(tmp_path) -> Path:
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"%PDF-1.4 fake invoice content")
    return path


def _seed_supplier_master(path: Path, canonical_name: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "supplier_id": "SUP-00000001",
                "canonical_name": canonical_name,
                "aliases": "",
                "country": "IE",
                "review_flag": "false",
                "first_seen": "2026-01-01",
                "last_seen": "2026-01-01",
            }
        )


def test_known_supplier_high_confidence_category_passes(sample_file, tmp_path):
    supplier_master = tmp_path / "suppliers.csv"
    _seed_supplier_master(supplier_master, "Notion Labs, Inc.")
    client = FakeClient([VALID_EXTRACT_RAW, HIGH_CONFIDENCE_CATEGORY_RAW])

    result = process_invoice_module.process_invoice(
        sample_file,
        client=client,
        today=date(2026, 10, 20),
        duplicate_cache_path=tmp_path / "seen_invoices.json",
        supplier_master_path=supplier_master,
    )

    assert result["status"] == "pass"
    assert result["review_reasons"] == []
    assert result["validation"]["status"] == "pass"
    assert result["supplier_match"]["status"] == "exact"
    assert result["category"]["category_code"] == "software_subscriptions"
    assert result["standardised_filename"] == "2026-10-03_Notion_Labs_Inc_NL_2026_04404.pdf"
    assert result["drive_subfolder"] == "2026/10/Notion_Labs_Inc"


def test_brand_new_supplier_is_flagged_for_review(sample_file, tmp_path):
    client = FakeClient([VALID_EXTRACT_RAW, HIGH_CONFIDENCE_CATEGORY_RAW])

    result = process_invoice_module.process_invoice(
        sample_file,
        client=client,
        today=date(2026, 10, 20),
        duplicate_cache_path=tmp_path / "seen_invoices.json",
        supplier_master_path=tmp_path / "suppliers.csv",
    )

    assert result["status"] == "review"
    assert any("supplier match" in reason for reason in result["review_reasons"])
    assert result["supplier_match"]["status"] == "new"


def test_low_confidence_category_is_flagged_for_review(sample_file, tmp_path):
    supplier_master = tmp_path / "suppliers.csv"
    _seed_supplier_master(supplier_master, "Notion Labs, Inc.")
    client = FakeClient([VALID_EXTRACT_RAW, LOW_CONFIDENCE_CATEGORY_RAW])

    result = process_invoice_module.process_invoice(
        sample_file,
        client=client,
        today=date(2026, 10, 20),
        duplicate_cache_path=tmp_path / "seen_invoices.json",
        supplier_master_path=supplier_master,
    )

    assert result["status"] == "review"
    assert any("category" in reason for reason in result["review_reasons"])


def test_duplicate_invoice_is_flagged_for_review(sample_file, tmp_path):
    supplier_master = tmp_path / "suppliers.csv"
    _seed_supplier_master(supplier_master, "Notion Labs, Inc.")
    duplicate_cache = tmp_path / "seen_invoices.json"

    first_client = FakeClient([VALID_EXTRACT_RAW, HIGH_CONFIDENCE_CATEGORY_RAW])
    process_invoice_module.process_invoice(
        sample_file,
        client=first_client,
        today=date(2026, 10, 20),
        duplicate_cache_path=duplicate_cache,
        supplier_master_path=supplier_master,
    )

    # A second file with identical extracted content (a different
    # source file, e.g. re-scanned) hits the same cache key for
    # extraction, so only the categorisation call is queued here.
    second_client = FakeClient([HIGH_CONFIDENCE_CATEGORY_RAW])
    result = process_invoice_module.process_invoice(
        sample_file,
        client=second_client,
        today=date(2026, 10, 20),
        duplicate_cache_path=duplicate_cache,
        supplier_master_path=supplier_master,
    )

    assert result["status"] == "review"
    assert result["validation"]["status"] == "review"
    assert any(issue["code"] == "DUPLICATE" for issue in result["validation"]["issues"])


def test_missing_supplier_skips_matching_and_categorising(sample_file, tmp_path):
    client = FakeClient([MISSING_SUPPLIER_EXTRACT_RAW])

    result = process_invoice_module.process_invoice(
        sample_file,
        client=client,
        today=date(2026, 10, 20),
        duplicate_cache_path=tmp_path / "seen_invoices.json",
        supplier_master_path=tmp_path / "suppliers.csv",
    )

    assert result["status"] == "review"
    assert result["supplier_match"] is None
    assert result["category"] is None
    assert "no supplier name extracted" in result["review_reasons"]
    assert client.calls == 1


def test_extraction_error_is_reported_not_raised(tmp_path):
    missing_file = tmp_path / "does_not_exist.pdf"

    result = process_invoice_module.process_invoice(
        missing_file,
        client=FakeClient([]),
        today=date(2026, 10, 20),
        duplicate_cache_path=tmp_path / "seen_invoices.json",
        supplier_master_path=tmp_path / "suppliers.csv",
    )

    assert result["status"] == "error"
    assert "extraction failed" in result["error"]


def test_main_prints_one_json_object_and_exit_code_matches_status(sample_file, tmp_path, monkeypatch, capsys):
    supplier_master = tmp_path / "suppliers.csv"
    _seed_supplier_master(supplier_master, "Notion Labs, Inc.")
    monkeypatch.setattr(extract_module, "_default_client", lambda: FakeClient([VALID_EXTRACT_RAW]))
    monkeypatch.setattr(
        categorise_module, "_default_client", lambda: FakeClient([HIGH_CONFIDENCE_CATEGORY_RAW])
    )

    exit_code = process_invoice_module.main(
        [
            str(sample_file),
            "--today",
            "2026-10-20",
            "--duplicate-cache-path",
            str(tmp_path / "seen_invoices.json"),
            "--supplier-master-path",
            str(supplier_master),
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert '"status": "pass"' in out
