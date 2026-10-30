"""Drafts reminder text for an overdue invoice, using the Claude API.

Per CLAUDE.md, the LLM's only job here is drafting the wording. Which
invoice needs a reminder and at which stage is schedule.py's job
(plain code); this module just turns that decision into text.

IMPORTANT: this module never sends anything. It only writes a .md
draft file to disk for a human to read and send themselves — see
CLAUDE.md's safety rules. It must never import an email-sending
library or call anything that transmits a message; tests/test_draft.py
scans this file's source to enforce that.

Caching: keyed on invoice number, stage, model, and DRAFT_PROMPT_VERSION
*and* on the two facts most likely to change between calls for the same
invoice/stage — amount_outstanding and the due date — so a later partial
payment can't leave a stale cached draft quoting the wrong amount.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from .config import CACHE_DIR, DRAFT_MODEL, DRAFT_PROMPT_VERSION, DRAFTS_DIR
from .tracker import Invoice

STAGE_TONE = {
    1: "friendly and brief — a simple, polite nudge that the invoice is now due.",
    2: "firm but polite — make clear payment is now a week overdue and ask for "
    "a specific action or response.",
    3: "a final notice — still professional and courteous, but serious in tone, "
    "making clear this is the last reminder before the matter is escalated "
    "internally.",
}

STAGE_LABELS = {1: "First reminder", 2: "Second reminder", 3: "Final notice"}


class DraftError(Exception):
    """Raised when a draft can't be produced at all (e.g. no API key)."""


class DraftContent(BaseModel):
    subject: str
    body: str


@dataclass
class DraftResult:
    invoice_id: str
    stage: int
    path: Path
    needs_review: bool
    reason: str | None = None


def _format_amount(amount: float) -> str:
    return f"{amount:,.2f}"


def _system_prompt(language: str) -> str:
    return "\n".join(
        [
            "You draft short payment-reminder emails for a small design "
            "studio's bookkeeping, in plain, professional business "
            f"language, written in {language}.",
            "",
            "You are given the exact facts for one invoice: customer "
            "name, invoice number, amount outstanding, currency, due "
            "date, days overdue, and which reminder stage this is.",
            "",
            "Use ONLY the facts you are given. Never invent, estimate, "
            "or assume any other figure, fee, interest charge, bank "
            "detail, or legal claim that isn't in the facts provided. "
            "Never threaten legal action.",
            "",
            "The invoice number and the amount outstanding must both "
            "appear in the email body, written exactly as given.",
            "",
            "Call the draft_reminder tool with your answer, and nothing "
            "else.",
        ]
    )


def _user_prompt(invoice: Invoice, stage: int, days_overdue: int) -> str:
    return "\n".join(
        [
            f"Customer name: {invoice.customer_name}",
            f"Invoice number: {invoice.invoice_number}",
            f"Amount outstanding: {_format_amount(invoice.amount_outstanding)} {invoice.currency}",
            f"Due date: {invoice.due_date.isoformat()}",
            f"Days overdue: {days_overdue}",
            f"Reminder stage: {stage} ({STAGE_LABELS[stage]})",
            f"Tone for this stage: {STAGE_TONE[stage]}",
        ]
    )


_TOOL_DEFINITION = {
    "name": "draft_reminder",
    "description": "The subject and body text for one payment-reminder email.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["subject", "body"],
    },
}


def _cache_path(invoice: Invoice, stage: int, model: str) -> Path:
    key = hashlib.sha256(
        invoice.invoice_number.encode()
        + b"\x00"
        + str(stage).encode()
        + b"\x00"
        + model.encode()
        + b"\x00"
        + DRAFT_PROMPT_VERSION.encode()
        + b"\x00"
        + _format_amount(invoice.amount_outstanding).encode()
        + b"\x00"
        + invoice.due_date.isoformat().encode()
    ).hexdigest()
    return CACHE_DIR / f"draft_{key}.json"


def is_cached(invoice: Invoice, stage: int, model: str | None = None) -> bool:
    """Check the cache without making an API call or needing a client/API key."""
    model = model or DRAFT_MODEL
    return _cache_path(invoice, stage, model).exists()


def _default_client() -> anthropic.Anthropic:
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise DraftError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    return anthropic.Anthropic(api_key=api_key)


def _call_model(
    client: anthropic.Anthropic,
    system_prompt: str,
    user_prompt: str,
    model: str,
) -> tuple[dict, "anthropic.types.Usage"]:
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        tools=[_TOOL_DEFINITION],
        tool_choice={"type": "tool", "name": "draft_reminder"},
        messages=[{"role": "user", "content": user_prompt}],
    )
    usage = response.usage
    for block in response.content:
        if block.type == "tool_use":
            return block.input, usage
    raise DraftError("Claude's response did not include a tool call.")


def _contains_required_facts(body: str, invoice: Invoice) -> bool:
    return invoice.invoice_number in body and _format_amount(invoice.amount_outstanding) in body


def _write_draft_file(
    invoice: Invoice,
    stage: int,
    content: DraftContent,
    *,
    needs_review: bool,
    drafts_dir: Path,
) -> Path:
    status_line = "Status: DRAFT - NOT SENT"
    if needs_review:
        status_line += " - NEEDS REVIEW (could not confirm exact figures; check before sending)"

    header = "\n".join(
        [
            f"To: {invoice.customer_name}",
            f"Subject: {content.subject}",
            f"Stage: {stage} ({STAGE_LABELS[stage]})",
            f"Invoice: {invoice.invoice_number}",
            status_line,
        ]
    )
    text = f"{header}\n\n{content.body}\n"

    drafts_dir.mkdir(parents=True, exist_ok=True)
    path = drafts_dir / f"{invoice.invoice_number}_stage{stage}.md"
    path.write_text(text, encoding="utf-8")
    return path


def draft_reminder(
    invoice: Invoice,
    stage: int,
    *,
    today: date | None = None,
    client: anthropic.Anthropic | None = None,
    model: str | None = None,
    drafts_dir: Path | None = None,
    on_usage: Callable[[int, int], None] | None = None,
) -> DraftResult:
    """Draft one reminder email for one invoice at one stage, and write
    it to a .md file in data/drafts/. Returns a DraftResult describing
    where it was written and whether it needs human review because the
    automated fact check couldn't confirm the invoice number and
    outstanding amount both appear in the draft."""
    model = model or DRAFT_MODEL
    today = today or date.today()
    drafts_dir = drafts_dir or DRAFTS_DIR
    language = invoice.language or "English"
    days_overdue = (today - invoice.due_date).days

    cache_path = _cache_path(invoice, stage, model)
    if cache_path.exists():
        raw = json.loads(cache_path.read_text())
        content = DraftContent.model_validate(raw)
        needs_review = not _contains_required_facts(content.body, invoice)
        path = _write_draft_file(
            invoice, stage, content, needs_review=needs_review, drafts_dir=drafts_dir
        )
        return DraftResult(invoice.invoice_number, stage, path, needs_review)

    client = client or _default_client()
    system_prompt = _system_prompt(language)
    user_prompt = _user_prompt(invoice, stage, days_overdue)

    raw, usage = _call_model(client, system_prompt, user_prompt, model)
    if on_usage:
        on_usage(usage.input_tokens, usage.output_tokens)

    try:
        content = DraftContent.model_validate(raw)
    except ValidationError as error:
        raise DraftError(
            f"Claude's response for invoice {invoice.invoice_number!r} did not "
            f"match the expected schema: {error}"
        ) from error

    needs_review = False
    reason = None
    if not _contains_required_facts(content.body, invoice):
        raw, usage = _call_model(client, system_prompt, user_prompt, model)
        if on_usage:
            on_usage(usage.input_tokens, usage.output_tokens)
        try:
            content = DraftContent.model_validate(raw)
        except ValidationError as error:
            raise DraftError(
                f"Claude's retried response for invoice {invoice.invoice_number!r} "
                f"did not match the expected schema: {error}"
            ) from error
        if not _contains_required_facts(content.body, invoice):
            needs_review = True
            reason = "Draft body is missing the exact invoice number and/or outstanding amount."

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(content.model_dump(), indent=2))

    path = _write_draft_file(
        invoice, stage, content, needs_review=needs_review, drafts_dir=drafts_dir
    )
    return DraftResult(invoice.invoice_number, stage, path, needs_review, reason)
