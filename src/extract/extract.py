"""Turn one invoice/receipt file (PDF or JPG) into structured data.

extract_invoice() sends the file to the Claude API and asks it to call a
tool with the extracted fields. Using a tool call (instead of asking for
free-form JSON) means Claude's answer always arrives as a structured
dict we can validate against ExtractedInvoice, rather than text we'd
have to parse ourselves.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Callable

import anthropic
from dotenv import load_dotenv
from pydantic import ValidationError

from .config import CACHE_DIR, MODEL_NAME
from .schema import ExtractedInvoice

SYSTEM_PROMPT = """\
You are an exact-data-extraction assistant for invoices, credit notes, \
and receipts. Extract only what is printed on the document, following \
these rules strictly:

- If a field is missing, unreadable, or not present on the document, \
return null for it. Never guess or infer a value.
- Copy numbers exactly as printed. Never calculate, correct, or "fix" a \
figure, even if net + vat does not equal the printed total.
- Report the supplier name exactly as printed on the document, \
including its capitalisation and punctuation.
- Dates must be in ISO format (YYYY-MM-DD).
- document_type must be one of: invoice, credit_note, receipt.
- For a credit note, net/vat/total should be negative numbers if the \
document itself shows them as a reduction.
- language is the two-letter ISO 639-1 code of the document's language \
(e.g. en, es, ca).
- For every field, also give a confidence score between 0.0 (not \
confident) and 1.0 (fully confident) in the value you extracted — or in \
the fact that it is genuinely absent, if you returned null.

Call the extract_invoice_data tool with your answer, and nothing else.\
"""

_CONFIDENCE_FIELDS = [
    "supplier",
    "invoice_number",
    "issue_date",
    "due_date",
    "currency",
    "net",
    "vat",
    "total",
    "document_type",
    "language",
]

TOOL_DEFINITION = {
    "name": "extract_invoice_data",
    "description": "Structured data extracted from an invoice, credit note, or receipt.",
    "input_schema": {
        "type": "object",
        "properties": {
            "supplier": {"type": ["string", "null"]},
            "invoice_number": {"type": ["string", "null"]},
            "issue_date": {
                "type": ["string", "null"],
                "description": "ISO format YYYY-MM-DD",
            },
            "due_date": {
                "type": ["string", "null"],
                "description": "ISO format YYYY-MM-DD",
            },
            "currency": {
                "type": ["string", "null"],
                "description": "ISO 4217 currency code, e.g. EUR",
            },
            "net": {"type": ["number", "null"]},
            "vat": {"type": ["number", "null"]},
            "total": {"type": ["number", "null"]},
            "document_type": {
                "type": ["string", "null"],
                "enum": ["invoice", "credit_note", "receipt", None],
            },
            "language": {
                "type": ["string", "null"],
                "description": "ISO 639-1 two-letter code",
            },
            "confidence": {
                "type": "object",
                "properties": {
                    field: {"type": "number", "minimum": 0, "maximum": 1}
                    for field in _CONFIDENCE_FIELDS
                },
                "required": _CONFIDENCE_FIELDS,
            },
        },
        "required": [*_CONFIDENCE_FIELDS, "confidence"],
    },
}


class ExtractionError(Exception):
    """Raised when extraction can't produce a valid result."""


def _cache_path(file_bytes: bytes, model: str) -> Path:
    # Keying on file contents + model name means a changed file, or a
    # different model, naturally misses the cache instead of reusing a
    # stale result.
    key = hashlib.sha256(file_bytes + model.encode()).hexdigest()
    return CACHE_DIR / f"{key}.json"


def is_cached(path: str | Path, model: str | None = None) -> bool:
    """Check whether this file + model already has a cached extraction,
    without making an API call or needing a client/API key."""
    model = model or MODEL_NAME
    file_bytes = Path(path).read_bytes()
    return _cache_path(file_bytes, model).exists()


def _default_client() -> anthropic.Anthropic:
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ExtractionError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file."
        )
    return anthropic.Anthropic(api_key=api_key)


def _content_blocks_for(path: Path, file_bytes: bytes) -> list[dict]:
    suffix = path.suffix.lower()
    encoded = base64.standard_b64encode(file_bytes).decode()
    if suffix == ".pdf":
        return [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": encoded,
                },
            }
        ]
    if suffix in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif suffix == ".png":
        media_type = "image/png"
    else:
        raise ExtractionError(f"Unsupported file type: {suffix}")
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": encoded,
            },
        }
    ]


def _pdf_pages_to_image_blocks(path: Path) -> list[dict]:
    """Fall back for models that reject PDF documents: render each page
    to a PNG with pymupdf and send those as images instead."""
    import pymupdf

    blocks = []
    doc = pymupdf.open(path)
    try:
        for page in doc:
            pixmap = page.get_pixmap(dpi=200)
            encoded = base64.standard_b64encode(pixmap.tobytes("png")).decode()
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": encoded,
                    },
                }
            )
    finally:
        doc.close()
    return blocks


def _call_model(
    client: anthropic.Anthropic, content_blocks: list[dict], model: str
) -> tuple[dict, "anthropic.types.Usage"]:
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[TOOL_DEFINITION],
        tool_choice={"type": "tool", "name": "extract_invoice_data"},
        messages=[
            {
                "role": "user",
                "content": [
                    *content_blocks,
                    {
                        "type": "text",
                        "text": "Extract the invoice data from this document.",
                    },
                ],
            }
        ],
    )

    usage = response.usage
    print(
        f"Tokens used — input: {usage.input_tokens}, output: {usage.output_tokens}"
    )

    for block in response.content:
        if block.type == "tool_use":
            return block.input, usage
    raise ExtractionError("Claude's response did not include a tool call.")


def extract_invoice(
    path: str | Path,
    client: anthropic.Anthropic | None = None,
    model: str | None = None,
    on_usage: Callable[[int, int], None] | None = None,
) -> ExtractedInvoice:
    """Extract one document. `model` defaults to MODEL_NAME in config.py —
    pass it explicitly to use a different model without touching that
    default. `on_usage(input_tokens, output_tokens)`, if given, is called
    once per real API call made (never on a cache hit), so a caller can
    total up token usage across a batch of extractions."""
    model = model or MODEL_NAME
    path = Path(path)
    if not path.exists():
        raise ExtractionError(f"File not found: {path}")

    file_bytes = path.read_bytes()
    cache_path = _cache_path(file_bytes, model)
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        return ExtractedInvoice.model_validate(cached)

    client = client or _default_client()
    content_blocks = _content_blocks_for(path, file_bytes)

    try:
        raw, usage = _call_model(client, content_blocks, model)
    except anthropic.APIStatusError as error:
        if path.suffix.lower() == ".pdf" and error.status_code == 400:
            print(
                "Claude rejected this PDF directly — rendering its pages "
                "as images with pymupdf instead."
            )
            content_blocks = _pdf_pages_to_image_blocks(path)
            raw, usage = _call_model(client, content_blocks, model)
        else:
            raise
    if on_usage:
        on_usage(usage.input_tokens, usage.output_tokens)

    try:
        parsed = ExtractedInvoice.model_validate(raw)
    except ValidationError:
        raw, usage = _call_model(client, content_blocks, model)
        if on_usage:
            on_usage(usage.input_tokens, usage.output_tokens)
        try:
            parsed = ExtractedInvoice.model_validate(raw)
        except ValidationError as second_error:
            raise ExtractionError(
                f"Claude's response for {path.name} did not match the "
                f"expected schema, even after retrying once: {second_error}"
            ) from second_error

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(raw, indent=2))
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract structured data from an invoice, receipt, or credit note."
    )
    parser.add_argument("path", help="Path to a PDF or JPG file")
    args = parser.parse_args(argv)

    try:
        result = extract_invoice(args.path)
    except ExtractionError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
