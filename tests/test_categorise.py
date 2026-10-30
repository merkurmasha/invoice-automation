"""Tests for src/suppliers/categorise.py. Per CLAUDE.md, no real Claude
API calls — a fake client returns canned responses, same pattern as
tests/test_extract.py.
"""

from __future__ import annotations

import pytest

from src.suppliers import categorise as categorise_module

_TEST_CATEGORIES = [
    {"code": "software_subscriptions", "name": "Software & Subscriptions", "description": "SaaS tools."},
    {"code": "other", "name": "Other", "description": "Anything that doesn't fit."},
]

VALID_RAW = {
    "category_code": "software_subscriptions",
    "confidence": 0.95,
    "reason": "Notion is a SaaS productivity tool.",
}

LOW_CONFIDENCE_RAW = {
    "category_code": "other",
    "confidence": 0.3,
    "reason": "Not enough information to tell what this expense is for.",
}

# Missing the required "reason" field — fails schema validation.
INVALID_RAW = {k: v for k, v in VALID_RAW.items() if k != "reason"}


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, tool_input: dict) -> None:
        self.input = tool_input


class _FakeUsage:
    def __init__(self, input_tokens: int = 300, output_tokens: int = 60) -> None:
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
        self._client.last_kwargs = kwargs
        item = self._client.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _FakeResponse(item)


class FakeClient:
    """Stands in for anthropic.Anthropic: returns queued responses in order."""

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.last_kwargs: dict = {}
        self.messages = _FakeMessages(self)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point the cache at a throwaway directory so tests never touch the
    real data/cache/ and never see leftovers from another test."""
    monkeypatch.setattr(categorise_module, "CACHE_DIR", tmp_path / "cache")


def test_valid_response_parsed_correctly():
    client = FakeClient([VALID_RAW])

    result = categorise_module.categorise(
        "Notion Labs, Inc.", "Monthly subscription", client=client, categories=_TEST_CATEGORIES
    )

    assert isinstance(result, categorise_module.CategoryResult)
    assert result.category_code == "software_subscriptions"
    assert result.confidence == 0.95
    assert client.calls == 1


def test_invalid_response_triggers_retry():
    client = FakeClient([INVALID_RAW, VALID_RAW])

    result = categorise_module.categorise(
        "Notion Labs, Inc.", "Monthly subscription", client=client, categories=_TEST_CATEGORIES
    )

    assert result.category_code == "software_subscriptions"
    assert client.calls == 2


def test_invalid_response_twice_raises_clear_error():
    client = FakeClient([INVALID_RAW, INVALID_RAW])

    with pytest.raises(categorise_module.CategorisationError):
        categorise_module.categorise(
            "Notion Labs, Inc.", "Monthly subscription", client=client, categories=_TEST_CATEGORIES
        )

    assert client.calls == 2


def test_cache_hit_avoids_second_api_call():
    first_client = FakeClient([VALID_RAW])
    first_result = categorise_module.categorise(
        "Notion Labs, Inc.", "Monthly subscription", client=first_client, categories=_TEST_CATEGORIES
    )
    assert first_client.calls == 1

    # No responses queued: if categorise() called the API again, this
    # would raise IndexError instead of returning a result.
    second_client = FakeClient([])
    second_result = categorise_module.categorise(
        "Notion Labs, Inc.", "Monthly subscription", client=second_client, categories=_TEST_CATEGORIES
    )

    assert second_client.calls == 0
    assert second_result == first_result


def test_below_confidence_threshold_needs_review():
    client = FakeClient([LOW_CONFIDENCE_RAW])

    result = categorise_module.categorise(
        "Mystery Supplier", None, client=client, categories=_TEST_CATEGORIES
    )

    assert result.needs_review() is True


def test_above_confidence_threshold_does_not_need_review():
    client = FakeClient([VALID_RAW])

    result = categorise_module.categorise(
        "Notion Labs, Inc.", "Monthly subscription", client=client, categories=_TEST_CATEGORIES
    )

    assert result.needs_review() is False


def test_missing_description_falls_back_to_supplier_name_only():
    client = FakeClient([VALID_RAW])

    categorise_module.categorise("Notion Labs, Inc.", None, client=client, categories=_TEST_CATEGORIES)

    sent_text = client.last_kwargs["messages"][0]["content"]
    assert "no line description available" in sent_text
    assert "Supplier: Notion Labs, Inc." in sent_text


def test_description_used_when_given():
    client = FakeClient([VALID_RAW])

    categorise_module.categorise(
        "Notion Labs, Inc.", "Monthly workspace subscription", client=client, categories=_TEST_CATEGORIES
    )

    sent_text = client.last_kwargs["messages"][0]["content"]
    assert "Monthly workspace subscription" in sent_text


def test_different_descriptions_do_not_share_a_cache_entry():
    first_client = FakeClient([VALID_RAW])
    categorise_module.categorise(
        "Notion Labs, Inc.", "Monthly subscription", client=first_client, categories=_TEST_CATEGORIES
    )
    assert first_client.calls == 1

    second_client = FakeClient([VALID_RAW])
    categorise_module.categorise(
        "Notion Labs, Inc.", "Annual subscription", client=second_client, categories=_TEST_CATEGORIES
    )
    assert second_client.calls == 1


def test_on_usage_called_once_per_real_api_call():
    client = FakeClient([VALID_RAW])
    seen = []

    categorise_module.categorise(
        "Notion Labs, Inc.",
        "Monthly subscription",
        client=client,
        categories=_TEST_CATEGORIES,
        on_usage=lambda i, o: seen.append((i, o)),
    )

    assert seen == [(300, 60)]  # _FakeUsage()'s defaults


def test_on_usage_not_called_on_cache_hit():
    first_client = FakeClient([VALID_RAW])
    categorise_module.categorise(
        "Notion Labs, Inc.", "Monthly subscription", client=first_client, categories=_TEST_CATEGORIES
    )

    seen = []
    second_client = FakeClient([])
    categorise_module.categorise(
        "Notion Labs, Inc.",
        "Monthly subscription",
        client=second_client,
        categories=_TEST_CATEGORIES,
        on_usage=lambda i, o: seen.append((i, o)),
    )

    assert seen == []


def test_is_cached_false_before_categorising_true_after():
    assert categorise_module.is_cached("Notion Labs, Inc.", "Monthly subscription") is False

    client = FakeClient([VALID_RAW])
    categorise_module.categorise(
        "Notion Labs, Inc.", "Monthly subscription", client=client, categories=_TEST_CATEGORIES
    )

    assert categorise_module.is_cached("Notion Labs, Inc.", "Monthly subscription") is True


def test_real_chart_loads_and_only_offers_its_own_codes():
    categories = categorise_module.load_chart()
    codes = {c["code"] for c in categories}

    assert "other" in codes
    assert "software_subscriptions" in codes
    tool_definition = categorise_module._tool_definition(categories)
    assert set(tool_definition["input_schema"]["properties"]["category_code"]["enum"]) == codes
