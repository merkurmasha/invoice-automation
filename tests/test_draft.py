"""Tests for src/receivables/draft.py. Per CLAUDE.md, no real Claude
API calls — a fake client returns canned responses, same pattern as
tests/test_categorise.py. Also includes the no-send source scan: this
module must never be able to transmit anything."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from src.receivables import draft as draft_module
from src.receivables import schedule as schedule_module
from src.receivables.tracker import Invoice

VALID_BODY = (
    "Dear Test Customer,\n\nThis is a reminder that invoice INV-1 for "
    "121.00 EUR is now overdue. Please arrange payment at your "
    "convenience.\n\nBest regards,\nCosta Brava Studio S.L."
)
VALID_RAW = {"subject": "Payment reminder: invoice INV-1", "body": VALID_BODY}

MISSING_FACTS_BODY = "Dear Test Customer,\n\nYour invoice is overdue. Please pay soon."
MISSING_FACTS_RAW = {"subject": "Payment reminder", "body": MISSING_FACTS_BODY}

FORBIDDEN_TERMS_BODY = (
    "Dear Test Customer,\n\nInvoice INV-1 for 121.00 EUR remains unpaid. "
    "If this is not settled soon we may pursue legal action and refer "
    "the matter to collection.\n\nRegards"
)
FORBIDDEN_TERMS_RAW = {"subject": "Final notice: invoice INV-1", "body": FORBIDDEN_TERMS_BODY}


class _FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, tool_input: dict) -> None:
        self.input = tool_input


class _FakeUsage:
    def __init__(self, input_tokens: int = 200, output_tokens: int = 100) -> None:
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


def _invoice() -> Invoice:
    return Invoice(
        invoice_number="INV-1",
        customer_name="Test Customer",
        issue_date=date(2026, 9, 1),
        due_date=date(2026, 10, 1),
        currency="EUR",
        net=100.0,
        vat=21.0,
        total=121.0,
    )


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Point the cache and the default reminder log at throwaway paths
    so tests never touch the real data/cache/ or
    data/reminder_log.csv. Tests that care about reminder-log content
    still pass their own log_path explicitly."""
    monkeypatch.setattr(draft_module, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(draft_module, "REMINDER_LOG_PATH", tmp_path / "unused_reminder_log.csv")


def test_valid_draft_is_written_with_expected_header(tmp_path):
    client = FakeClient([VALID_RAW])
    invoice = _invoice()

    result = draft_module.draft_reminder(
        invoice, 1, today=date(2026, 10, 15), client=client, drafts_dir=tmp_path / "drafts"
    )

    assert result.needs_review is False
    assert client.calls == 1
    text = result.path.read_text()
    assert "To: Test Customer" in text
    assert "Stage: 1" in text
    assert "Invoice: INV-1" in text
    assert "Status: DRAFT - NOT SENT" in text
    assert "NEEDS REVIEW" not in text
    assert "INV-1" in text
    assert "121.00" in text


def test_missing_facts_triggers_one_retry_then_succeeds(tmp_path):
    client = FakeClient([MISSING_FACTS_RAW, VALID_RAW])
    invoice = _invoice()

    result = draft_module.draft_reminder(
        invoice, 2, today=date(2026, 10, 15), client=client, drafts_dir=tmp_path / "drafts"
    )

    assert client.calls == 2
    assert result.needs_review is False


def test_missing_facts_after_retry_is_flagged_for_human_review(tmp_path):
    client = FakeClient([MISSING_FACTS_RAW, MISSING_FACTS_RAW])
    invoice = _invoice()

    result = draft_module.draft_reminder(
        invoice, 3, today=date(2026, 10, 15), client=client, drafts_dir=tmp_path / "drafts"
    )

    assert client.calls == 2
    assert result.needs_review is True
    text = result.path.read_text()
    assert "NEEDS REVIEW" in text


def test_second_call_is_served_from_cache_without_a_client(tmp_path):
    client = FakeClient([VALID_RAW])
    invoice = _invoice()
    drafts_dir = tmp_path / "drafts"

    draft_module.draft_reminder(invoice, 1, today=date(2026, 10, 15), client=client, drafts_dir=drafts_dir)
    assert draft_module.is_cached(invoice, 1)

    # No client passed this time — if this weren't a cache hit it would
    # try to build a real anthropic.Anthropic() and fail without an API key.
    result = draft_module.draft_reminder(invoice, 1, today=date(2026, 10, 16), drafts_dir=drafts_dir)

    assert client.calls == 1
    assert result.needs_review is False


def test_cache_key_changes_when_outstanding_amount_changes(tmp_path):
    invoice = _invoice()
    client = FakeClient([VALID_RAW])
    draft_module.draft_reminder(
        invoice, 1, today=date(2026, 10, 15), client=client, drafts_dir=tmp_path / "drafts"
    )
    assert draft_module.is_cached(invoice, 1)

    invoice.amount_paid = 50.0  # outstanding is now different
    assert not draft_module.is_cached(invoice, 1)


def test_cache_key_changes_when_the_reminder_log_shows_an_earlier_stage(tmp_path):
    invoice = _invoice()
    client = FakeClient([VALID_RAW])
    empty_log = tmp_path / "empty_log.csv"  # nothing logged yet

    draft_module.draft_reminder(
        invoice, 2, today=date(2026, 10, 15), client=client, log_path=empty_log,
        drafts_dir=tmp_path / "drafts",
    )
    assert draft_module.is_cached(invoice, 2, log_path=empty_log)

    log_with_stage_1 = tmp_path / "log_with_stage_1.csv"
    schedule_module.record_drafted("INV-1", 1, date(2026, 10, 1), log_path=log_with_stage_1)
    # Same invoice/stage, but the log now shows an earlier reminder was
    # already sent — that's a different prompt, so it must be a cache miss.
    assert not draft_module.is_cached(invoice, 2, log_path=log_with_stage_1)


# --- Fix 1: previous_reminders_sent is read from the reminder log and ---
# --- flows into the prompt; stage 3's tone no longer implies an      ---
# --- internal escalation process.                                    ---


def test_stage_three_tone_no_longer_implies_an_internal_escalation():
    tone = draft_module.STAGE_TONE[3].lower()
    assert "escalated internally" not in tone
    assert "do not mention" in tone
    assert "escalation" in tone  # named only as something to avoid


def test_previous_reminders_sent_helper_reads_the_log_correctly(tmp_path):
    invoice = _invoice()
    log_path = tmp_path / "reminder_log.csv"
    schedule_module.record_drafted("INV-1", 1, date(2026, 10, 1), log_path=log_path)

    # Stage 2 comes after the logged stage 1 -> true.
    assert draft_module._previous_reminders_sent(invoice, 2, log_path) is True
    # Stage 1 itself isn't "earlier than stage 1" -> false.
    assert draft_module._previous_reminders_sent(invoice, 1, log_path) is False
    # A different invoice's log entries don't count.
    other_invoice = _invoice()
    other_invoice.invoice_number = "INV-2"
    assert draft_module._previous_reminders_sent(other_invoice, 2, log_path) is False


def test_previous_reminders_sent_true_reaches_the_prompt(tmp_path):
    client = FakeClient([VALID_RAW])
    invoice = _invoice()
    log_path = tmp_path / "reminder_log.csv"
    schedule_module.record_drafted("INV-1", 1, date(2026, 10, 1), log_path=log_path)
    schedule_module.record_drafted("INV-1", 2, date(2026, 10, 8), log_path=log_path)

    draft_module.draft_reminder(
        invoice, 3, today=date(2026, 10, 15), client=client, log_path=log_path,
        drafts_dir=tmp_path / "drafts",
    )

    user_message = client.last_kwargs["messages"][0]["content"]
    assert "Previous reminders already sent for this invoice: yes" in user_message


def test_previous_reminders_sent_false_reaches_the_prompt(tmp_path):
    client = FakeClient([VALID_RAW])
    invoice = _invoice()
    log_path = tmp_path / "empty_reminder_log.csv"  # nothing logged yet

    draft_module.draft_reminder(
        invoice, 1, today=date(2026, 10, 15), client=client, log_path=log_path,
        drafts_dir=tmp_path / "drafts",
    )

    user_message = client.last_kwargs["messages"][0]["content"]
    assert "Previous reminders already sent for this invoice: no" in user_message


# --- Fix 2: a plain-code check flags escalation/legal/cost wording. ---


def test_forbidden_terms_found_detects_english_and_catalan_spanish_terms():
    body = "Es traslladarà a via judicial amb un recàrrec per interès de demora."

    found = draft_module._forbidden_terms_found(body)

    assert "judicial" in found
    assert "recàrrec" in found
    assert "interès" in found


def test_forbidden_terms_in_draft_body_flag_for_review(tmp_path):
    client = FakeClient([FORBIDDEN_TERMS_RAW, FORBIDDEN_TERMS_RAW])
    invoice = _invoice()

    result = draft_module.draft_reminder(
        invoice, 3, today=date(2026, 10, 15), client=client, drafts_dir=tmp_path / "drafts"
    )

    assert client.calls == 2  # still retries once, same as the missing-facts check
    assert result.needs_review is True
    assert "forbidden term" in result.reason
    assert "legal" in result.reason
    text = result.path.read_text()
    assert "NEEDS REVIEW" in text


def test_forbidden_terms_trigger_retry_then_succeed(tmp_path):
    client = FakeClient([FORBIDDEN_TERMS_RAW, VALID_RAW])
    invoice = _invoice()

    result = draft_module.draft_reminder(
        invoice, 3, today=date(2026, 10, 15), client=client, drafts_dir=tmp_path / "drafts"
    )

    assert client.calls == 2
    assert result.needs_review is False


# --- No-send source scan -----------------------------------------------

_FORBIDDEN_PATTERNS = [
    r"\bsmtplib\b",
    r"\bsmtp\b",
    r"\bsendgrid\b",
    r"\byagmail\b",
    r"\bimaplib\b",
    r"import\s+email\b",
    r"send_message\s*\(",
    r"\.send\s*\(",
    r"gmail.*\.send",
]


def test_draft_module_source_never_sends_anything():
    source = Path(draft_module.__file__).read_text().lower()
    for pattern in _FORBIDDEN_PATTERNS:
        assert not re.search(pattern, source, re.IGNORECASE), (
            f"draft.py source matched a forbidden send-like pattern: {pattern!r}"
        )
