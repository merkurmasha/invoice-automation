"""The shape of one extracted invoice/receipt/credit note.

This is the contract the Claude API's answer must satisfy. Pydantic
validates it for us: if the API returns something that doesn't fit
(wrong type, a date that isn't ISO format, a missing field), creating
the model raises a ValidationError instead of letting bad data through.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"
    RECEIPT = "receipt"


class FieldConfidence(BaseModel):
    """How confident the model is in each extracted field, 0 (guess) to 1 (certain)."""

    supplier: float = Field(ge=0.0, le=1.0)
    invoice_number: float = Field(ge=0.0, le=1.0)
    issue_date: float = Field(ge=0.0, le=1.0)
    due_date: float = Field(ge=0.0, le=1.0)
    currency: float = Field(ge=0.0, le=1.0)
    net: float = Field(ge=0.0, le=1.0)
    vat: float = Field(ge=0.0, le=1.0)
    total: float = Field(ge=0.0, le=1.0)
    document_type: float = Field(ge=0.0, le=1.0)
    language: float = Field(ge=0.0, le=1.0)


class ExtractedInvoice(BaseModel):
    """One document's extracted data. Every data field may be null if it
    wasn't found on the document — extraction never guesses."""

    supplier: str | None = None
    invoice_number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    # Amounts are exactly as printed: negative for credit notes, and left
    # inconsistent if the document's own numbers don't add up.
    net: float | None = None
    vat: float | None = None
    total: float | None = None
    document_type: DocumentType | None = None
    language: str | None = None
    confidence: FieldConfidence
