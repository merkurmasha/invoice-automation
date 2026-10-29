"""Builds the deterministic list of synthetic supplier-invoice "jobs".

A job is the single source of truth for one invoice file: the PDF
renderer and the answer-key builder both read from the same job, so the
rendered PDF and the recorded "correct" answer can never drift apart —
except where a job deliberately asks for a trap (a wrong printed total,
a missing due date, a renamed supplier, ...), in which case the job
records both the printed (wrong) values and the true values.

Everything here is generated from a fixed random seed, so re-running the
generator produces byte-for-byte identical invoice numbers and amounts.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.synthetic.suppliers import SUPPLIERS

SEED = 42
MONTHS_2026 = [7, 8, 9, 10]  # July - October 2026
VAT_RATE = 0.21

CURRENCY_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£"}
VAT_LABEL = {"en": "VAT", "es": "IVA", "ca": "IVA"}


@dataclass
class LineItem:
    description: str
    qty: float
    unit_price: float

    @property
    def line_total(self) -> float:
        return round(self.qty * self.unit_price, 2)


@dataclass
class InvoiceJob:
    file_stem: str
    supplier_id: str
    supplier_canonical: str
    supplier_as_printed: str
    supplier_country: str
    supplier_address: str
    supplier_tax_id: str
    supplier_iban: str
    invoice_number: str
    issue_date: date
    due_date: date | None
    currency: str
    line_items: list[LineItem]
    net: float
    vat_rate: float
    vat: float
    printed_total: float
    printed_total_is_consistent: bool
    document_type: str
    language: str
    category: str
    trap: str | None
    layout_seed: int
    is_photo_source: bool = field(default=False)


def _round(x: float) -> float:
    return round(x + 0.0, 2)


def _invoice_number(supplier_id: str, seq: int, year: int, month: int) -> str:
    patterns = {
        "notion": f"NL-{year}-{seq:05d}",
        "adobe": f"ADB/{year}/{seq:05d}",
        "figma": f"FIG-{seq:06d}",
        "coworking": f"BWH-{year}{month:02d}-{seq:03d}",
        "electricity": f"F-{year}-{seq:06d}",
        "internet": f"FC/{year}/{month:02d}/{seq:04d}",
        "freelancer": f"{year}/{seq:03d}",
        "printer": f"IG-{seq:05d}",
        "nordic": f"NDT-{year}-{seq:04d}",
        "studiofonts": f"SFF-{seq:05d}",
        "pixelco": f"PCD-{year}/{seq:04d}",
        "cloudhost": f"CH-{seq:06d}",
        "courier": f"MG-{seq:05d}",
        "insurance": f"ACB-{year}-{seq:04d}",
        "furniture": f"MOB-{seq:04d}",
        "catering": f"CC-{seq:05d}",
        "officesupplies": f"TPG-{seq:04d}",
        "travel": f"VB-{year}-{seq:04d}",
        "accounting": f"AFP-{seq:04d}",
    }
    return patterns[supplier_id]


def _line_items(supplier_id: str, month: int, rng: random.Random) -> list[LineItem]:
    jitter = lambda base, pct: _round(base * (1 + rng.uniform(-pct, pct)))
    items: dict[str, list[LineItem]] = {
        "notion": [LineItem("Notion Team plan - monthly (10 seats)", 10, jitter(10.00, 0.0))],
        "adobe": [LineItem("Creative Cloud All Apps - monthly (3 seats)", 3, 55.99)],
        "figma": [LineItem("Figma Professional - monthly (5 seats)", 5, 15.00)],
        "coworking": [LineItem(f"Dedicated desk - {month:02d}/2026 (2 desks)", 2, jitter(199.00, 0.03))],
        "electricity": [
            LineItem(f"Electricity supply - {month:02d}/2026", 1, jitter(134.50, 0.15)),
            LineItem("Standing charge", 1, 12.30),
        ],
        "internet": [LineItem(f"Fibra 600Mb - {month:02d}/2026", 1, 59.90)],
        "freelancer": [LineItem("Serveis de fotografia de producte", 1, jitter(350.00, 0.1))],
        "printer": [
            LineItem("Targetes de visita x1000", 1, 85.00),
            LineItem("Flyers A5 x500", 1, 120.00),
        ],
        "nordic": [LineItem("Design Tools Pro - annual licence", 1, 499.00)],
        "studiofonts": [LineItem("Font Foundry subscription - annual", 1, 299.00)],
        "pixelco": [LineItem("UI design subcontracting - hours", 20, 45.00)],
        "cloudhost": [LineItem("Hosting pla Pro - mensual", 1, 29.00)],
        "courier": [LineItem("Enviament urgent Girona-Barcelona", 3, 18.50)],
        "insurance": [LineItem("Assegurança responsabilitat civil - trimestral", 1, 210.00)],
        "furniture": [LineItem("Cadira ergonòmica", 2, 249.00)],
        "catering": [LineItem("Reunió amb client - cafè i pastes", 1, 48.50)],
        "officesupplies": [
            LineItem("Tòner HP compatible", 4, 24.90),
            LineItem("Paper A4 (paquet de 5)", 2, 14.00),
        ],
        "travel": [LineItem("Bitllet AVE Barcelona-Madrid", 2, 95.00)],
        "accounting": [LineItem("Assessorament fiscal trimestral", 1, 180.00)],
    }
    return items[supplier_id]


def build_jobs() -> list[InvoiceJob]:
    rng = random.Random(SEED)
    jobs: list[InvoiceJob] = []
    seq_counters: dict[str, int] = {}

    def next_seq(supplier_id: str, base: int) -> int:
        seq_counters.setdefault(supplier_id, base)
        seq_counters[supplier_id] += 1
        return seq_counters[supplier_id]

    def make_job(
        supplier_id: str,
        month: int,
        day: int,
        currency: str,
        due_in_days: int | None,
        base_seq: int,
        document_type: str = "invoice",
        supplier_as_printed: str | None = None,
        trap: str | None = None,
        maths_offset: float = 0.0,
        file_suffix: str = "",
        invoice_number_override: str | None = None,
        sign: float = 1.0,
    ) -> InvoiceJob:
        supplier = SUPPLIERS[supplier_id]
        issue_date = date(2026, month, day)
        due_date = issue_date + timedelta(days=due_in_days) if due_in_days is not None else None
        items = _line_items(supplier_id, month, rng)
        if sign < 0:
            items = [LineItem(li.description, li.qty, _round(li.unit_price * sign)) for li in items]
        net = _round(sum(li.line_total for li in items))
        vat_rate = 0.0 if trap == "reverse_charge" else VAT_RATE
        vat = _round(net * vat_rate)
        correct_total = _round(net + vat)
        printed_total = _round(correct_total + maths_offset)
        is_consistent = maths_offset == 0.0
        seq = next_seq(supplier_id, base_seq)
        invoice_number = invoice_number_override or _invoice_number(supplier_id, seq, 2026, month)
        stem = f"{supplier_id}_{issue_date.isoformat()}{file_suffix}"
        job = InvoiceJob(
            file_stem=stem,
            supplier_id=supplier_id,
            supplier_canonical=supplier.canonical_name,
            supplier_as_printed=supplier_as_printed or supplier.canonical_name,
            supplier_country=supplier.country,
            supplier_address=supplier.address,
            supplier_tax_id=supplier.tax_id,
            supplier_iban=supplier.iban,
            invoice_number=invoice_number,
            issue_date=issue_date,
            due_date=due_date,
            currency=currency,
            line_items=items,
            net=net,
            vat_rate=vat_rate,
            vat=vat,
            printed_total=printed_total,
            printed_total_is_consistent=is_consistent,
            document_type=document_type,
            language=supplier.language,
            category=supplier.category,
            trap=trap,
            layout_seed=rng.randint(0, 1_000_000),
        )
        jobs.append(job)
        return job

    # --- Recurring monthly suppliers (July - October 2026) -----------------
    notion_variants = [
        "Notion Labs Inc",
        "NOTION LABS",
        "Notion Labs, Inc",
        None,  # canonical, untagged
    ]
    for i, month in enumerate(MONTHS_2026):
        variant = notion_variants[i]
        make_job(
            "notion", month, 3, "EUR", 30, base_seq=4400,
            supplier_as_printed=variant,
            trap="name_variant" if variant else None,
        )

    for i, month in enumerate(MONTHS_2026):
        variant = "ADOBE SYSTEMS SOFTWARE IRELAND LTD" if month == 9 else None
        make_job(
            "adobe", month, 5, "EUR", 30, base_seq=7700,
            supplier_as_printed=variant,
            trap="name_variant" if variant else None,
        )

    for month in MONTHS_2026:
        make_job("coworking", month, 1, "EUR", 30, base_seq=1100)

    electricity_dup_month = 8
    for month in MONTHS_2026:
        maths = -8.47 if month == 7 else 0.0
        make_job(
            "electricity", month, 10, "EUR", 21, base_seq=9900,
            trap="maths_error" if maths else None,
            maths_offset=maths,
        )
    # exact duplicate: the August electricity invoice is re-sent unchanged.
    original_electricity_aug = next(
        j for j in jobs if j.supplier_id == "electricity" and j.issue_date.month == electricity_dup_month
    )
    original_electricity_aug.trap = "duplicate_exact"
    dup = InvoiceJob(**{**original_electricity_aug.__dict__, "file_stem": original_electricity_aug.file_stem + "_dup"})
    jobs.append(dup)

    for month in MONTHS_2026:
        maths = 6.12 if month == 7 else 0.0
        make_job(
            "internet", month, 15, "EUR", 15, base_seq=3300,
            trap="maths_error" if maths else None,
            maths_offset=maths,
        )

    # near duplicate: September coworking invoice resent with a different total.
    original_coworking_sep = next(
        j for j in jobs if j.supplier_id == "coworking" and j.issue_date.month == 9
    )
    near_dup = InvoiceJob(**{**original_coworking_sep.__dict__})
    near_dup.file_stem = original_coworking_sep.file_stem + "_near"
    # Same supplier and invoice number, but a different (internally
    # consistent) amount - e.g. a corrected resend with one more desk billed.
    near_dup.net = _round(original_coworking_sep.net + 45.00)
    near_dup.vat = _round(near_dup.net * near_dup.vat_rate)
    near_dup.printed_total = _round(near_dup.net + near_dup.vat)
    near_dup.printed_total_is_consistent = True
    near_dup.trap = "duplicate_near"
    jobs.append(near_dup)

    # --- One-off / low-frequency suppliers ----------------------------------
    make_job("figma", 7, 12, "USD", 30, base_seq=2200, trap="maths_error", maths_offset=3.5)
    make_job("figma", 9, 12, "USD", 30, base_seq=2200)

    make_job("freelancer", 7, 20, "EUR", None, base_seq=10, trap="no_due_date")
    make_job("freelancer", 9, 22, "EUR", 15, base_seq=10)

    make_job("printer", 8, 18, "EUR", 20, base_seq=500)
    make_job("printer", 10, 6, "EUR", 20, base_seq=500)

    make_job("nordic", 8, 1, "EUR", 30, base_seq=60, trap="reverse_charge")
    make_job("studiofonts", 9, 9, "EUR", 30, base_seq=20)
    make_job("pixelco", 9, 25, "GBP", 30, base_seq=15)

    make_job("cloudhost", 7, 8, "EUR", 15, base_seq=80)
    make_job("courier", 8, 14, "EUR", 10, base_seq=40)
    make_job("insurance", 7, 30, "EUR", 30, base_seq=5)
    make_job("furniture", 8, 25, "EUR", 20, base_seq=12)
    make_job("catering", 9, 18, "EUR", 15, base_seq=70)
    make_job("officesupplies", 10, 2, "EUR", 15, base_seq=90)
    make_job("travel", 10, 20, "EUR", None, base_seq=8, trap="no_due_date")
    make_job("accounting", 10, 10, "EUR", 30, base_seq=6)

    # --- Credit note ---------------------------------------------------------
    make_job(
        "adobe", 10, 15, "EUR", None, base_seq=7700,
        document_type="credit_note",
        trap="credit_note",
        invoice_number_override=f"ADB/2026/CN{seq_counters['adobe']:05d}",
        sign=-1.0,
    )

    # Mark 6 straightforward invoices as the source for degraded phone photos.
    photo_stems = {
        "notion_2026-08-03",
        "coworking_2026-07-01",
        "internet_2026-10-15",
        "freelancer_2026-07-20",
        "pixelco_2026-09-25",
        "studiofonts_2026-09-09",
    }
    for j in jobs:
        if j.file_stem in photo_stems:
            j.is_photo_source = True

    return jobs
