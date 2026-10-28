"""Builds the answer_key.json structure: one entry per generated file
(every invoice PDF, plus one entry per degraded phone photo), recording
the ground truth an extraction step should be able to read back out.
"""
from __future__ import annotations

from src.synthetic.jobs import InvoiceJob


def _base_entry(job: InvoiceJob, file_path: str) -> dict:
    entry = {
        "file": file_path,
        "supplier": job.supplier_canonical,
        "supplier_as_printed": job.supplier_as_printed,
        "invoice_number": job.invoice_number,
        "issue_date": job.issue_date.isoformat(),
        "due_date": job.due_date.isoformat() if job.due_date else None,
        "currency": job.currency,
        "net": job.net,
        "vat": job.vat,
        "total": job.printed_total,
        "document_type": job.document_type,
        "language": job.language,
        "expected_category": job.category,
        "trap": job.trap,
    }
    if not job.printed_total_is_consistent:
        entry["printed_total_is_consistent"] = False
    return entry


def build_answer_key(jobs: list[InvoiceJob]) -> list[dict]:
    entries = [_base_entry(job, f"invoices/{job.file_stem}.pdf") for job in jobs]
    entries += [
        _base_entry(job, f"photos/{job.file_stem}.jpg") for job in jobs if job.is_photo_source
    ]
    return entries
