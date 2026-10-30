"""Categorise one expense line into this project's chart of accounts,
using the Claude API.

Matching a supplier to a canonical identity (master.py) is plain
deterministic code. Deciding *which expense category* a supplier/line
belongs to is a judgement call plain code can't make reliably — that's
the one job this module hands to the LLM, per CLAUDE.md. categorise()
asks Claude to call a tool (like extract.py does) so the answer always
arrives as structured data, never free text to parse.

Results are cached on disk the same way extraction is (see
src/suppliers/config.py): a cache key is a hash of the supplier name,
the line description, the model, and CATEGORISE_PROMPT_VERSION, so a
changed prompt or model naturally misses the cache instead of reusing
a stale category.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable

import anthropic
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from .config import (
    CACHE_DIR,
    CATEGORISE_MODEL,
    CATEGORISE_PROMPT_VERSION,
    CATEGORY_CONFIDENCE_THRESHOLD,
)

CHART_PATH = Path(__file__).resolve().parents[2] / "config" / "chart_of_accounts.yaml"

_NO_DESCRIPTION_TEXT = "(no line description available — use the supplier name only)"


class CategorisationError(Exception):
    """Raised when categorisation can't produce a valid result."""


class CategoryResult(BaseModel):
    category_code: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str

    def needs_review(self, threshold: float = CATEGORY_CONFIDENCE_THRESHOLD) -> bool:
        return self.confidence < threshold


def load_chart(path: Path | None = None) -> list[dict]:
    path = path or CHART_PATH
    data = yaml.safe_load(path.read_text())
    return data["categories"]


def _system_prompt(categories: list[dict]) -> str:
    lines = [
        "You are an expense-categorisation assistant for a small design "
        "studio's bookkeeping. You are given a supplier name and a short "
        "description of one expense line, plus a fixed chart of "
        "accounts.",
        "",
        "Choose exactly one category code from this list — never invent "
        "a code that isn't here:",
        "",
    ]
    for category in categories:
        lines.append(f"- {category['code']}: {category['name']} — {category['description']}")
    lines.extend(
        [
            "",
            'If you are not sure which category fits, return "other" '
            "with a low confidence score rather than guessing at a "
            "specific category.",
            "Give a confidence score between 0.0 (not confident) and "
            "1.0 (fully confident), and a one-sentence reason for your "
            "choice.",
            "Call the categorise_expense tool with your answer, and "
            "nothing else.",
        ]
    )
    return "\n".join(lines)


def _tool_definition(categories: list[dict]) -> dict:
    codes = [category["code"] for category in categories]
    return {
        "name": "categorise_expense",
        "description": "The chart-of-accounts category for one expense line.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category_code": {"type": "string", "enum": codes},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"},
            },
            "required": ["category_code", "confidence", "reason"],
        },
    }


def _cache_path(supplier: str, description: str, model: str) -> Path:
    key = hashlib.sha256(
        supplier.encode()
        + b"\x00"
        + description.encode()
        + model.encode()
        + CATEGORISE_PROMPT_VERSION.encode()
    ).hexdigest()
    return CACHE_DIR / f"categorise_{key}.json"


def is_cached(supplier: str, line_description: str | None, model: str | None = None) -> bool:
    """Check the cache without making an API call or needing a client/API key."""
    model = model or CATEGORISE_MODEL
    description = line_description or _NO_DESCRIPTION_TEXT
    return _cache_path(supplier, description, model).exists()


def _default_client() -> anthropic.Anthropic:
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise CategorisationError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file."
        )
    return anthropic.Anthropic(api_key=api_key)


def _call_model(
    client: anthropic.Anthropic,
    system_prompt: str,
    tool_definition: dict,
    supplier: str,
    description: str,
    model: str,
) -> tuple[dict, "anthropic.types.Usage"]:
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=system_prompt,
        tools=[tool_definition],
        tool_choice={"type": "tool", "name": "categorise_expense"},
        messages=[
            {
                "role": "user",
                "content": f"Supplier: {supplier}\nLine description: {description}",
            }
        ],
    )
    usage = response.usage
    for block in response.content:
        if block.type == "tool_use":
            return block.input, usage
    raise CategorisationError("Claude's response did not include a tool call.")


def categorise(
    supplier: str,
    line_description: str | None = None,
    *,
    client: anthropic.Anthropic | None = None,
    model: str | None = None,
    categories: list[dict] | None = None,
    on_usage: Callable[[int, int], None] | None = None,
) -> CategoryResult:
    """Categorise one expense line. `line_description` may be None when
    no line-item text is available — the prompt then tells Claude to
    rely on the supplier name alone, rather than silently repeating the
    supplier name as if it were a description."""
    model = model or CATEGORISE_MODEL
    categories = categories or load_chart()
    description = line_description or _NO_DESCRIPTION_TEXT

    cache_path = _cache_path(supplier, description, model)
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        return CategoryResult.model_validate(cached)

    client = client or _default_client()
    system_prompt = _system_prompt(categories)
    tool_definition = _tool_definition(categories)

    raw, usage = _call_model(client, system_prompt, tool_definition, supplier, description, model)
    if on_usage:
        on_usage(usage.input_tokens, usage.output_tokens)

    try:
        parsed = CategoryResult.model_validate(raw)
    except ValidationError:
        raw, usage = _call_model(
            client, system_prompt, tool_definition, supplier, description, model
        )
        if on_usage:
            on_usage(usage.input_tokens, usage.output_tokens)
        try:
            parsed = CategoryResult.model_validate(raw)
        except ValidationError as second_error:
            raise CategorisationError(
                f"Claude's response for supplier {supplier!r} did not match "
                f"the expected schema, even after retrying once: {second_error}"
            ) from second_error

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(raw, indent=2))
    return parsed
