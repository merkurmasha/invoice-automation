"""Tests for src/extract/extract.py.

Per CLAUDE.md, tests never call the real Claude API — every test here
uses a fake client that returns canned responses, so these tests cost
nothing and run offline.
"""

from __future__ import annotations

import json

import pytest

from src.extract import extract as extract_module
from src.extract.schema import ExtractedInvoice

VALID_RAW = {
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

NULL_FIELDS_RAW = {
    **VALID_RAW,
    "due_date": None,
    "currency": None,
    "confidence": {**VALID_RAW["confidence"], "due_date": 0.0, "currency": 0.0},
}

CREDIT_NOTE_RAW = {
    **VALID_RAW,
    "invoice_number": "ADB/2026/CN07704",
    "net": -167.97,
    "vat": -35.27,
    "total": -203.24,
    "document_type": "credit_note",
}

# Missing the required "confidence" object — fails schema validation.
INVALID_RAW = {k: v for k, v in VALID_RAW.items() if k != "confidence"}


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, tool_input: dict) -> None:
        self.input = tool_input


class _FakeUsage:
    def __init__(self, input_tokens: int = 100, output_tokens: int = 50) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


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
    """Stands in for anthropic.Anthropic: returns queued responses in order."""

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.messages = _FakeMessages(self)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point the cache at a throwaway directory so tests never touch the
    real data/cache/ and never see leftovers from another test."""
    monkeypatch.setattr(extract_module, "CACHE_DIR", tmp_path / "cache")


@pytest.fixture
def sample_file(tmp_path):
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"%PDF-1.4 fake invoice content")
    return path


def test_valid_response_parsed_correctly(sample_file):
    client = FakeClient([VALID_RAW])

    result = extract_module.extract_invoice(sample_file, client=client)

    assert isinstance(result, ExtractedInvoice)
    assert result.supplier == "Notion Labs, Inc."
    assert result.invoice_number == "NL-2026-04404"
    assert str(result.issue_date) == "2026-10-03"
    assert result.total == 121.0
    assert result.confidence.supplier == 0.98
    assert client.calls == 1


def test_null_fields_allowed(sample_file):
    client = FakeClient([NULL_FIELDS_RAW])

    result = extract_module.extract_invoice(sample_file, client=client)

    assert result.due_date is None
    assert result.currency is None
    assert result.supplier == "Notion Labs, Inc."


def test_invalid_response_triggers_retry(sample_file):
    client = FakeClient([INVALID_RAW, VALID_RAW])

    result = extract_module.extract_invoice(sample_file, client=client)

    assert result.invoice_number == "NL-2026-04404"
    assert client.calls == 2


def test_invalid_response_twice_raises_clear_error(sample_file):
    client = FakeClient([INVALID_RAW, INVALID_RAW])

    with pytest.raises(extract_module.ExtractionError):
        extract_module.extract_invoice(sample_file, client=client)

    assert client.calls == 2


def test_cache_hit_avoids_second_api_call(sample_file):
    first_client = FakeClient([VALID_RAW])
    first_result = extract_module.extract_invoice(sample_file, client=first_client)
    assert first_client.calls == 1

    # No responses queued: if extract_invoice called the API again, this
    # would raise IndexError instead of returning a result.
    second_client = FakeClient([])
    second_result = extract_module.extract_invoice(sample_file, client=second_client)

    assert second_client.calls == 0
    assert second_result == first_result


def test_credit_note_keeps_negative_amounts(sample_file):
    client = FakeClient([CREDIT_NOTE_RAW])

    result = extract_module.extract_invoice(sample_file, client=client)

    assert result.document_type.value == "credit_note"
    assert result.net == -167.97
    assert result.vat == -35.27
    assert result.total == -203.24


def test_different_models_do_not_share_a_cache_entry(sample_file):
    first_client = FakeClient([VALID_RAW])
    extract_module.extract_invoice(sample_file, client=first_client, model="model-a")
    assert first_client.calls == 1

    # Same file, different model: must be a cache miss, not a collision
    # with model-a's cached result.
    second_client = FakeClient([VALID_RAW])
    extract_module.extract_invoice(sample_file, client=second_client, model="model-b")
    assert second_client.calls == 1


def test_on_usage_called_once_per_real_api_call(sample_file):
    client = FakeClient([VALID_RAW])
    seen = []

    extract_module.extract_invoice(
        sample_file, client=client, on_usage=lambda i, o: seen.append((i, o))
    )

    assert seen == [(100, 50)]  # _FakeUsage()'s defaults


def test_on_usage_not_called_on_cache_hit(sample_file):
    first_client = FakeClient([VALID_RAW])
    extract_module.extract_invoice(sample_file, client=first_client)

    seen = []
    second_client = FakeClient([])
    extract_module.extract_invoice(
        sample_file, client=second_client, on_usage=lambda i, o: seen.append((i, o))
    )

    assert seen == []


def test_is_cached_false_before_extraction_true_after(sample_file):
    assert extract_module.is_cached(sample_file) is False

    client = FakeClient([VALID_RAW])
    extract_module.extract_invoice(sample_file, client=client)

    assert extract_module.is_cached(sample_file) is True
    # A different model is a different cache key, still uncached.
    assert extract_module.is_cached(sample_file, model="some-other-model") is False
