"""Generates a HELD-OUT evaluation set: ~12-14 documents with layouts,
date formats, and number formats genuinely different from
src/synthetic/pdf_render.py, so the v2 extraction prompt's accuracy can
be checked against documents it was never tuned against.

Run as:
    python -m src.synthetic.heldout [--out DIR]

Deterministic (fixed random seed + reportlab invariant=1), like the
main synthetic generator. Output goes to data/heldout/ (invoices/,
photos/, answer_key.json) - entirely separate from data/synthetic/, so
running this never touches the tuned dev set.

Per the task that built this module: the extraction prompt, schema,
validation logic, and PROMPT_VERSION are never touched here. Whatever
this set exposes about the prompt's real-world accuracy gets reported
as-is by evals/run_eval.py --dataset heldout.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import pymupdf
from PIL import Image, ImageEnhance
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from src.synthetic.suppliers import OUR_COMPANY, Company

SEED = 20260
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "heldout"

CURRENCY_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£"}

LABELS = {
    "en": {
        "invoice": "INVOICE",
        "credit_note": "CREDIT NOTE",
        "receipt": "RECEIPT",
        "bill_to": "BILL TO",
        "invoice_no": "Invoice #",
        "date": "Date",
        "due": "Due",
        "description": "Description",
        "qty": "Qty",
        "unit_price": "Unit price",
        "amount": "Amount",
        "net": "Net",
        "vat": "VAT",
        "total": "TOTAL",
        "tax_id": "Tax ID",
        "vat_included": "Prices shown include VAT.",
    },
    "es": {
        "invoice": "FACTURA",
        "credit_note": "FACTURA RECTIFICATIVA",
        "receipt": "RECIBO",
        "bill_to": "FACTURAR A",
        "invoice_no": "Nº factura",
        "date": "Fecha",
        "due": "Vencimiento",
        "description": "Descripción",
        "qty": "Cant.",
        "unit_price": "Precio unit.",
        "amount": "Importe",
        "net": "Base",
        "vat": "IVA",
        "total": "TOTAL",
        "tax_id": "NIF/CIF",
        "vat_included": "Precios con IVA incluido.",
    },
    "ca": {
        "invoice": "FACTURA",
        "credit_note": "FACTURA RECTIFICATIVA",
        "receipt": "REBUT",
        "bill_to": "FACTURAR A",
        "invoice_no": "Núm. factura",
        "date": "Data",
        "due": "Venciment",
        "description": "Descripció",
        "qty": "Quant.",
        "unit_price": "Preu unit.",
        "amount": "Import",
        "net": "Base",
        "vat": "IVA",
        "total": "TOTAL",
        "tax_id": "NIF",
        "vat_included": "Preus amb IVA inclòs.",
    },
}


def _fmt_money_default(amount: float, currency: str) -> str:
    symbol = CURRENCY_SYMBOL[currency]
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol}{abs(amount):,.2f}"


def _address_lines(address: str) -> list[str]:
    parts = address.split(", ")
    return [", ".join(parts[i : i + 2]) for i in range(0, len(parts), 2)]


@dataclass
class LineItem:
    description: str
    qty: float
    unit_price: float

    @property
    def line_total(self) -> float:
        return round(self.qty * self.unit_price, 2)


@dataclass
class HeldoutDoc:
    file_stem: str
    challenge: str
    language: str
    document_type: str
    supplier: Company
    supplier_as_printed: str
    invoice_number: str | None
    issue_date: date
    issue_date_printed: str
    due_date: date | None
    due_date_printed: str | None
    currency: str
    line_items: list[LineItem]
    net: float | None
    vat: float | None
    total: float
    net_str: str
    vat_str: str
    total_str: str
    money_fmt: Callable[[float], str]
    trap: str | None = None
    vat_breakdown: list[tuple[float, float, float]] | None = None
    tax_inclusive_note: bool = False
    category: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self.category = self.supplier.category


# ---------------------------------------------------------------------------
# Renderers. All four of these are deliberately structured differently from
# the four layouts in src/synthetic/pdf_render.py: no colour-fill header
# bands, no stacked two-column address block up top, bordered boxes instead
# of accent-coloured rule lines, and (for two_column/multi_page/handwritten)
# structural choices pdf_render.py never makes at all.
# ---------------------------------------------------------------------------


def _render_standard(doc: HeldoutDoc, output_path: Path) -> None:
    labels = LABELS[doc.language]
    title = labels["credit_note"] if doc.document_type == "credit_note" else labels["invoice"]
    c = canvas.Canvas(str(output_path), pagesize=A4, invariant=1)
    width, height = A4
    margin = 20 * mm
    y = height - margin

    # Masthead: title left, supplier identity right, single compact line
    # (pdf_render.py always prints a full stacked address block instead).
    c.setFont("Times-Bold", 20)
    c.drawString(margin, y, title)
    c.setFont("Helvetica", 9)
    c.drawRightString(width - margin, y, doc.supplier_as_printed)
    y -= 5 * mm
    c.setFont("Helvetica", 8)
    c.drawRightString(width - margin, y, f"{labels['tax_id']}: {doc.supplier.tax_id}")
    y -= 6 * mm

    c.setLineWidth(1.2)
    c.line(margin, y, width - margin, y)
    c.setLineWidth(0.4)
    c.line(margin, y - 1.2 * mm, width - margin, y - 1.2 * mm)
    y -= 10 * mm

    # Bill-to boxed panel, left side (bordered box, not plain text columns).
    box_w, box_h = 85 * mm, 22 * mm
    c.setLineWidth(0.8)
    c.rect(margin, y - box_h, box_w, box_h, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(margin + 3 * mm, y - 5 * mm, labels["bill_to"])
    c.setFont("Helvetica", 8)
    ty = y - 9 * mm
    c.drawString(margin + 3 * mm, ty, OUR_COMPANY.canonical_name)
    ty -= 4 * mm
    for line in _address_lines(OUR_COMPANY.address):
        c.drawString(margin + 3 * mm, ty, line)
        ty -= 4 * mm

    # Metadata, inline "Label: value" on one line (pdf_render.py always
    # stacks the value under the label in separate columns instead).
    meta_x = margin + box_w + 10 * mm
    meta_y = y - 5 * mm
    c.setFont("Helvetica-Bold", 9)
    if doc.invoice_number:
        c.drawString(meta_x, meta_y, f"{labels['invoice_no']}: {doc.invoice_number}")
        meta_y -= 5.5 * mm
    c.drawString(meta_x, meta_y, f"{labels['date']}: {doc.issue_date_printed}")
    meta_y -= 5.5 * mm
    if doc.due_date_printed:
        c.drawString(meta_x, meta_y, f"{labels['due']}: {doc.due_date_printed}")

    y -= box_h + 8 * mm

    # Item table (plain rule lines, no colour fill).
    col_desc_x = margin
    col_qty_x = width - margin - 60 * mm
    col_price_x = width - margin - 40 * mm
    col_amount_x = width - margin

    c.setFont("Helvetica-Bold", 8)
    c.drawString(col_desc_x, y, labels["description"])
    c.drawString(col_qty_x, y, labels["qty"])
    c.drawRightString(col_price_x + 18 * mm, y, labels["unit_price"])
    c.drawRightString(col_amount_x, y, labels["amount"])
    y -= 2 * mm
    c.setLineWidth(0.6)
    c.line(margin, y, width - margin, y)
    y -= 5 * mm

    c.setFont("Helvetica", 9)
    for item in doc.line_items:
        c.drawString(col_desc_x, y, item.description)
        c.drawString(col_qty_x, y, f"{item.qty:g}")
        c.drawRightString(col_price_x + 18 * mm, y, doc.money_fmt(item.unit_price))
        c.drawRightString(col_amount_x, y, doc.money_fmt(item.line_total))
        y -= 6 * mm

    c.setLineWidth(0.6)
    c.line(margin, y, width - margin, y)
    y -= 4 * mm

    if doc.tax_inclusive_note:
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(margin, y, labels["vat_included"])
        y -= 6 * mm

    # Totals box, bottom-right, bordered.
    box_w2 = 75 * mm
    n_vat_lines = len(doc.vat_breakdown) if doc.vat_breakdown else 1
    lines_needed = 2 + n_vat_lines
    box_h2 = lines_needed * 6 * mm + 4 * mm
    box_x = width - margin - box_w2
    c.rect(box_x, y - box_h2, box_w2, box_h2, stroke=1, fill=0)
    ty = y - 5 * mm
    c.setFont("Helvetica", 9)
    c.drawString(box_x + 3 * mm, ty, labels["net"])
    c.drawRightString(box_x + box_w2 - 3 * mm, ty, doc.net_str)
    ty -= 6 * mm
    if doc.vat_breakdown:
        for rate, _base, vat_amt in doc.vat_breakdown:
            c.drawString(box_x + 3 * mm, ty, f"{labels['vat']} ({rate * 100:g}%)")
            c.drawRightString(box_x + box_w2 - 3 * mm, ty, doc.money_fmt(vat_amt))
            ty -= 6 * mm
    else:
        c.drawString(box_x + 3 * mm, ty, labels["vat"])
        c.drawRightString(box_x + box_w2 - 3 * mm, ty, doc.vat_str)
        ty -= 6 * mm
    c.setLineWidth(0.6)
    c.line(box_x + 2 * mm, ty + 2 * mm, box_x + box_w2 - 2 * mm, ty + 2 * mm)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(box_x + 3 * mm, ty - 3 * mm, labels["total"])
    c.drawRightString(box_x + box_w2 - 3 * mm, ty - 3 * mm, doc.total_str)

    y = y - box_h2 - 14 * mm

    # Footer: supplier identity/payment details (pdf_render.py prints this
    # at the top, never the bottom).
    c.setFont("Helvetica", 8)
    c.drawString(margin, y, f"{doc.supplier_as_printed} — {labels['tax_id']}: {doc.supplier.tax_id}")
    y -= 4 * mm
    for line in _address_lines(doc.supplier.address):
        c.drawString(margin, y, line)
        y -= 4 * mm
    if doc.supplier.iban:
        c.drawString(margin, y, f"IBAN: {doc.supplier.iban}")

    c.showPage()
    c.save()


def _render_two_column(doc: HeldoutDoc, output_path: Path) -> None:
    """totals on the left, supplier details at the bottom, no table
    header row."""
    labels = LABELS[doc.language]
    c = canvas.Canvas(str(output_path), pagesize=A4, invariant=1)
    width, height = A4
    margin = 20 * mm
    y = height - margin

    c.setFont("Times-Bold", 18)
    c.drawCentredString(width / 2, y, labels["invoice"])
    y -= 10 * mm

    c.setFont("Helvetica", 9)
    c.drawString(
        margin, y,
        f"{labels['invoice_no']}: {doc.invoice_number}    "
        f"{labels['date']}: {doc.issue_date_printed}    "
        f"{labels['due']}: {doc.due_date_printed}",
    )
    y -= 5 * mm
    c.drawString(margin, y, f"{labels['bill_to']}: {OUR_COMPANY.canonical_name}")
    y -= 10 * mm

    col_desc_x = margin
    col_qty_x = width - margin - 60 * mm
    col_price_x = width - margin - 40 * mm
    col_amount_x = width - margin

    c.setLineWidth(0.6)
    c.line(margin, y, width - margin, y)
    y -= 6 * mm
    c.setFont("Helvetica", 9)
    for item in doc.line_items:
        c.drawString(col_desc_x, y, item.description)
        c.drawString(col_qty_x, y, f"{item.qty:g}")
        c.drawRightString(col_price_x + 18 * mm, y, doc.money_fmt(item.unit_price))
        c.drawRightString(col_amount_x, y, doc.money_fmt(item.line_total))
        y -= 6 * mm
    c.line(margin, y, width - margin, y)
    y -= 10 * mm

    box_w, box_h = 70 * mm, 24 * mm
    c.rect(margin, y - box_h, box_w, box_h, stroke=1, fill=0)
    ty = y - 5 * mm
    c.setFont("Helvetica", 9)
    c.drawString(margin + 3 * mm, ty, labels["net"])
    c.drawRightString(margin + box_w - 3 * mm, ty, doc.net_str)
    ty -= 6 * mm
    c.drawString(margin + 3 * mm, ty, labels["vat"])
    c.drawRightString(margin + box_w - 3 * mm, ty, doc.vat_str)
    ty -= 6 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin + 3 * mm, ty, labels["total"])
    c.drawRightString(margin + box_w - 3 * mm, ty, doc.total_str)

    y = y - box_h - 20 * mm

    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin, y, doc.supplier_as_printed)
    y -= 4.5 * mm
    c.setFont("Helvetica", 8)
    for line in _address_lines(doc.supplier.address):
        c.drawString(margin, y, line)
        y -= 4 * mm
    c.drawString(margin, y, f"{labels['tax_id']}: {doc.supplier.tax_id}")
    y -= 4 * mm
    if doc.supplier.iban:
        c.drawString(margin, y, f"IBAN: {doc.supplier.iban}")

    c.showPage()
    c.save()


def _render_multi_page(doc: HeldoutDoc, output_path: Path) -> None:
    """2 pages; line items continue across both, the total is only on
    page 2."""
    labels = LABELS[doc.language]
    c = canvas.Canvas(str(output_path), pagesize=A4, invariant=1)
    width, height = A4
    margin = 20 * mm

    mid = len(doc.line_items) // 2 + (len(doc.line_items) % 2)
    page1_items = doc.line_items[:mid]
    page2_items = doc.line_items[mid:]

    def draw_header(page_label: str) -> float:
        y = height - margin
        c.setFont("Times-Bold", 18)
        c.drawString(margin, y, labels["invoice"])
        c.setFont("Helvetica", 9)
        c.drawRightString(width - margin, y, page_label)
        y -= 8 * mm
        c.drawString(
            margin, y,
            f"{labels['invoice_no']}: {doc.invoice_number}    "
            f"{labels['date']}: {doc.issue_date_printed}    "
            f"{labels['due']}: {doc.due_date_printed}",
        )
        y -= 10 * mm
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin, y, labels["description"])
        c.drawString(width - margin - 60 * mm, y, labels["qty"])
        c.drawRightString(width - margin - 22 * mm, y, labels["unit_price"])
        c.drawRightString(width - margin, y, labels["amount"])
        y -= 2 * mm
        c.setLineWidth(0.6)
        c.line(margin, y, width - margin, y)
        return y - 5 * mm

    def draw_items(items: list[LineItem], y: float) -> float:
        c.setFont("Helvetica", 9)
        for item in items:
            c.drawString(margin, y, item.description)
            c.drawString(width - margin - 60 * mm, y, f"{item.qty:g}")
            c.drawRightString(width - margin - 22 * mm, y, doc.money_fmt(item.unit_price))
            c.drawRightString(width - margin, y, doc.money_fmt(item.line_total))
            y -= 6 * mm
        return y

    y = draw_header("Page 1 of 2")
    y = draw_items(page1_items, y)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(margin, y - 4 * mm, "... continued on page 2")
    c.showPage()

    y = draw_header("Page 2 of 2")
    y = draw_items(page2_items, y)
    y -= 6 * mm
    c.setLineWidth(0.6)
    c.line(margin, y, width - margin, y)
    y -= 8 * mm

    box_w, box_h = 75 * mm, 24 * mm
    box_x = width - margin - box_w
    c.rect(box_x, y - box_h, box_w, box_h, stroke=1, fill=0)
    ty = y - 5 * mm
    c.setFont("Helvetica", 9)
    c.drawString(box_x + 3 * mm, ty, labels["net"])
    c.drawRightString(box_x + box_w - 3 * mm, ty, doc.net_str)
    ty -= 6 * mm
    c.drawString(box_x + 3 * mm, ty, labels["vat"])
    c.drawRightString(box_x + box_w - 3 * mm, ty, doc.vat_str)
    ty -= 6 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(box_x + 3 * mm, ty, labels["total"])
    c.drawRightString(box_x + box_w - 3 * mm, ty, doc.total_str)

    c.showPage()
    c.save()


def _render_handwritten(doc: HeldoutDoc, output_path: Path) -> None:
    """Receipt-style, handwritten-looking font (Times-Italic - reportlab's
    base-14 fonts have no script/cursive face, so an italic serif is the
    closest built-in approximation), printed total only - no net/VAT
    breakdown anywhere on the document."""
    labels = LABELS[doc.language]
    c = canvas.Canvas(str(output_path), pagesize=A4, invariant=1)
    width, _height = A4
    y = 230 * mm

    c.setFont("Times-Italic", 18)
    c.drawCentredString(width / 2, y, labels["receipt"])
    y -= 10 * mm
    c.setFont("Times-Italic", 12)
    c.drawCentredString(width / 2, y, doc.supplier_as_printed)
    y -= 7 * mm
    if doc.invoice_number:
        c.drawCentredString(width / 2, y, f"No. {doc.invoice_number}")
        y -= 7 * mm
    c.drawCentredString(width / 2, y, doc.issue_date_printed)
    y -= 10 * mm
    for item in doc.line_items:
        c.drawCentredString(width / 2, y, f"{item.description} ... {doc.money_fmt(item.line_total)}")
        y -= 6 * mm
    y -= 6 * mm
    c.setFont("Times-BoldItalic", 15)
    c.drawCentredString(width / 2, y, f"{labels['total']}: {doc.total_str}")

    c.showPage()
    c.save()


def _degrade_to_scan(pdf_path: Path, output_path: Path, seed: int) -> None:
    """Degrades a rendered PDF's first page into a scanner-style JPEG:
    a grey cast, a slight skew, and scattered speckle noise. Distinct
    from photos.py's pdf_to_phone_photo (which simulates a phone camera
    shot - corner shadow + blur), since the scan_like challenge wants a
    different kind of degraded image."""
    rng = random.Random(seed)
    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()

    angle = rng.uniform(-2.5, 2.5)
    img = img.rotate(angle, expand=True, fillcolor=(190, 190, 185), resample=Image.BICUBIC)

    grey = Image.new("RGB", img.size, (205, 205, 200))
    img = Image.blend(img, grey, alpha=0.18)
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.85, 0.95))

    pixels = img.load()
    width, height = img.size
    n_specks = int(width * height * 0.0015)
    for _ in range(n_specks):
        x = rng.randrange(width)
        y = rng.randrange(height)
        shade = rng.choice([30, 225])
        pixels[x, y] = (shade, shade, shade)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(str(output_path), "JPEG", quality=rng.randint(55, 70))


# ---------------------------------------------------------------------------
# The 12 challenge documents (written_month expands to 3: en/es/ca).
# ---------------------------------------------------------------------------


def build_heldout_docs() -> list[tuple[HeldoutDoc, Callable[[HeldoutDoc, Path], None], bool]]:
    """Returns (doc, renderer, is_photo_only) for every heldout document."""
    docs: list[tuple[HeldoutDoc, Callable[[HeldoutDoc, Path], None], bool]] = []

    # 1. us_date --------------------------------------------------------
    supplier = Company(
        canonical_name="Bay Area Dev Tools Inc",
        country="US",
        address="000 Fictional Blvd, Suite 000, Austin, TX 00000",
        tax_id="00-0000099",
        iban="",
        language="en",
        category="Software & Subscriptions",
    )
    items = [LineItem("Annual API usage plan", 1, 450.00)]
    net, vat, total = 450.00, 36.00, 486.00
    doc = HeldoutDoc(
        file_stem="heldout_us_date",
        challenge="us_date",
        language="en",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="BADT-2026-0304",
        issue_date=date(2026, 3, 4),
        issue_date_printed="03/04/2026",
        due_date=date(2026, 3, 25),
        due_date_printed="03/25/2026",
        currency="USD",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "USD"),
        vat_str=_fmt_money_default(vat, "USD"),
        total_str=_fmt_money_default(total, "USD"),
        money_fmt=lambda a: _fmt_money_default(a, "USD"),
    )
    docs.append((doc, _render_standard, False))

    # 2-4. written_month (en / es / ca) ----------------------------------
    supplier = Company(
        canonical_name="Thistle & Co Design Studio",
        country="GB",
        address="0 Fictional Row, Bristol, BS0 0AA, United Kingdom",
        tax_id="GB000000099",
        iban="GB00 FAKE 0000 0000 0000 99",
        language="en",
        category="Professional Services",
    )
    items = [LineItem("Brand identity refresh — concept phase", 1, 1200.00)]
    net, vat, total = 1200.00, 252.00, 1452.00
    doc = HeldoutDoc(
        file_stem="heldout_written_month_en",
        challenge="written_month",
        language="en",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="TCDS-2026-014",
        issue_date=date(2026, 9, 3),
        issue_date_printed="3rd September 2026",
        due_date=date(2026, 10, 3),
        due_date_printed="03/10/2026",
        currency="GBP",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "GBP"),
        vat_str=_fmt_money_default(vat, "GBP"),
        total_str=_fmt_money_default(total, "GBP"),
        money_fmt=lambda a: _fmt_money_default(a, "GBP"),
    )
    docs.append((doc, _render_standard, False))

    supplier = Company(
        canonical_name="Taller de Encuadernación Martí, S.L.",
        country="ES",
        address="Carrer Mallorca, 0, 08029 Barcelona",
        tax_id="B00000099",
        iban="ES00 0000 0000 0000 0000 0099",
        language="es",
        category="Printing & Supplies",
    )
    items = [LineItem("Encuadernación de catálogos — 50 unidades", 50, 4.50)]
    net, vat, total = 225.00, 47.25, 272.25
    doc = HeldoutDoc(
        file_stem="heldout_written_month_es",
        challenge="written_month",
        language="es",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="TEM-2026-0098",
        issue_date=date(2026, 10, 12),
        issue_date_printed="12 de octubre de 2026",
        due_date=date(2026, 11, 11),
        due_date_printed="11/11/2026",
        currency="EUR",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "EUR"),
        vat_str=_fmt_money_default(vat, "EUR"),
        total_str=_fmt_money_default(total, "EUR"),
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
    )
    docs.append((doc, _render_standard, False))

    supplier = Company(
        canonical_name="Vivers Can Bruguera",
        country="ES",
        address="Carretera Vella, 0, 17310 Lloret de Mar",
        tax_id="00000099X",
        iban="ES00 0000 0000 0000 0000 0098",
        language="ca",
        category="Facilities & Maintenance",
    )
    items = [LineItem("Manteniment de jardí — març", 1, 180.00)]
    net, vat, total = 180.00, 37.80, 217.80
    doc = HeldoutDoc(
        file_stem="heldout_written_month_ca",
        challenge="written_month",
        language="ca",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="VCB-2026-007",
        issue_date=date(2026, 3, 4),
        issue_date_printed="4 de març de 2026",
        due_date=date(2026, 4, 20),
        due_date_printed="20/04/2026",
        currency="EUR",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "EUR"),
        vat_str=_fmt_money_default(vat, "EUR"),
        total_str=_fmt_money_default(total, "EUR"),
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
    )
    docs.append((doc, _render_standard, False))

    # 5. two_column_layout ------------------------------------------------
    supplier = Company(
        canonical_name="Decoracions Bages, S.L.",
        country="ES",
        address="Carrer Sant Francesc, 0, 08240 Manresa",
        tax_id="B00000097",
        iban="ES00 0000 0000 0000 0000 0097",
        language="ca",
        category="Facilities & Maintenance",
    )
    items = [
        LineItem("Pintura interior mat 15L", 2, 65.00),
        LineItem("Vernís protector 4L", 1, 38.00),
        LineItem("Mà d'obra aplicació", 8, 22.00),
    ]
    net, vat, total = 344.00, 72.24, 416.24
    doc = HeldoutDoc(
        file_stem="heldout_two_column_layout",
        challenge="two_column_layout",
        language="ca",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="DB-2026-0231",
        issue_date=date(2026, 9, 14),
        issue_date_printed="14/09/2026",
        due_date=date(2026, 10, 14),
        due_date_printed="14/10/2026",
        currency="EUR",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "EUR"),
        vat_str=_fmt_money_default(vat, "EUR"),
        total_str=_fmt_money_default(total, "EUR"),
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
    )
    docs.append((doc, _render_two_column, False))

    # 6. multi_page ---------------------------------------------------------
    supplier = Company(
        canonical_name="Meridian Consulting Group, S.L.",
        country="ES",
        address="Avinguda Diagonal, 000, 08036 Barcelona",
        tax_id="B00000096",
        iban="ES00 0000 0000 0000 0000 0096",
        language="en",
        category="Professional Services",
    )
    items = [
        LineItem("Strategic planning workshop — March", 1, 950.00),
        LineItem("Market research report", 1, 620.00),
        LineItem("Stakeholder interviews (x6)", 6, 85.00),
        LineItem("Competitive analysis deck", 1, 480.00),
        LineItem("Follow-up workshop", 1, 400.00),
        LineItem("Implementation roadmap", 1, 700.00),
        LineItem("Executive summary presentation", 1, 350.00),
        LineItem("Travel & expenses", 1, 120.00),
    ]
    net, vat, total = 4130.00, 867.30, 4997.30
    doc = HeldoutDoc(
        file_stem="heldout_multi_page",
        challenge="multi_page",
        language="en",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="MCG-2026-0045",
        issue_date=date(2026, 7, 22),
        issue_date_printed="22/07/2026",
        due_date=date(2026, 8, 21),
        due_date_printed="21/08/2026",
        currency="EUR",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "EUR"),
        vat_str=_fmt_money_default(vat, "EUR"),
        total_str=_fmt_money_default(total, "EUR"),
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
    )
    docs.append((doc, _render_multi_page, False))

    # 7. tax_inclusive --------------------------------------------------
    supplier = Company(
        canonical_name="Taller Ceràmic Girona",
        country="ES",
        address="Carrer de la Llebre, 0, 17004 Girona",
        tax_id="B00000095",
        iban="ES00 0000 0000 0000 0000 0095",
        language="ca",
        category="Office Supplies",
    )
    items = [LineItem("Peces de ceràmica personalitzades (packs)", 3, 60.50)]
    net, vat, total = 150.00, 31.50, 181.50
    doc = HeldoutDoc(
        file_stem="heldout_tax_inclusive",
        challenge="tax_inclusive",
        language="ca",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="TCG-2026-0067",
        issue_date=date(2026, 9, 5),
        issue_date_printed="05/09/2026",
        due_date=date(2026, 10, 5),
        due_date_printed="05/10/2026",
        currency="EUR",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "EUR"),
        vat_str=_fmt_money_default(vat, "EUR"),
        total_str=_fmt_money_default(total, "EUR"),
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
        tax_inclusive_note=True,
    )
    docs.append((doc, _render_standard, False))

    # 8. multiple_vat_rates ------------------------------------------------
    supplier = Company(
        canonical_name="Esdeveniments Girona, S.L.",
        country="ES",
        address="Plaça del Vi, 0, 17004 Girona",
        tax_id="B00000094",
        iban="ES00 0000 0000 0000 0000 0094",
        language="ca",
        category="Professional Services",
    )
    items = [
        LineItem("Càtering esdeveniment corporatiu", 1, 800.00),
        LineItem("Lloguer equip audiovisual", 1, 500.00),
    ]
    net, vat, total = 1300.00, 185.00, 1485.00
    doc = HeldoutDoc(
        file_stem="heldout_multiple_vat_rates",
        challenge="multiple_vat_rates",
        language="ca",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="EG-2026-0112",
        issue_date=date(2026, 9, 30),
        issue_date_printed="30/09/2026",
        due_date=date(2026, 10, 30),
        due_date_printed="30/10/2026",
        currency="EUR",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "EUR"),
        vat_str=_fmt_money_default(vat, "EUR"),
        total_str=_fmt_money_default(total, "EUR"),
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
        vat_breakdown=[(0.10, 800.00, 80.00), (0.21, 500.00, 105.00)],
    )
    docs.append((doc, _render_standard, False))

    # 9. scan_like (PDF rendered -> degraded scan JPG, PDF itself discarded)
    supplier = Company(
        canonical_name="Ferreteria El Martell, S.L.",
        country="ES",
        address="Carrer Nou, 0, 17600 Figueres",
        tax_id="B00000093",
        iban="ES00 0000 0000 0000 0000 0093",
        language="ca",
        category="Office Supplies",
    )
    items = [LineItem("Eines i material divers", 1, 95.00)]
    net, vat, total = 95.00, 19.95, 114.95
    doc = HeldoutDoc(
        file_stem="heldout_scan_like",
        challenge="scan_like",
        language="ca",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="FM-2026-0301",
        issue_date=date(2026, 8, 19),
        issue_date_printed="19/08/2026",
        due_date=date(2026, 9, 18),
        due_date_printed="18/09/2026",
        currency="EUR",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "EUR"),
        vat_str=_fmt_money_default(vat, "EUR"),
        total_str=_fmt_money_default(total, "EUR"),
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
    )
    docs.append((doc, _render_standard, True))

    # 10. handwritten_note -----------------------------------------------
    supplier = Company(
        canonical_name="Cafeteria Pont Vell",
        country="ES",
        address="Pont de Pedra, 0, 17001 Girona",
        tax_id="00000098B",
        iban="",
        language="ca",
        category="Meals & Entertainment",
    )
    items = [LineItem("Cafè i pastís", 1, 14.50)]
    total = 14.50
    doc = HeldoutDoc(
        file_stem="heldout_handwritten_note",
        challenge="handwritten_note",
        language="ca",
        document_type="receipt",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="0482",
        issue_date=date(2026, 9, 21),
        issue_date_printed="21/09/2026",
        due_date=None,
        due_date_printed=None,
        currency="EUR",
        line_items=items,
        net=None, vat=None, total=total,
        net_str="",
        vat_str="",
        total_str=_fmt_money_default(total, "EUR"),
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
    )
    docs.append((doc, _render_handwritten, False))

    # 11. european_numbers --------------------------------------------------
    supplier = Company(
        canonical_name="Maquinària Industrial Girona, S.L.",
        country="ES",
        address="Polígon Industrial Celrà, 0, 17460 Celrà",
        tax_id="B00000092",
        iban="ES00 0000 0000 0000 0000 0092",
        language="es",
        category="Equipment",
    )
    items = [LineItem("Compressor industrial 100L", 1, 1234.56)]
    net, vat, total = 1234.56, 259.26, 1493.82
    doc = HeldoutDoc(
        file_stem="heldout_european_numbers",
        challenge="european_numbers",
        language="es",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="MIG-2026-0890",
        issue_date=date(2026, 8, 11),
        issue_date_printed="11/08/2026",
        due_date=date(2026, 9, 10),
        due_date_printed="10/09/2026",
        currency="EUR",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str="€1.234,56",  # dot thousands, comma decimal
        vat_str="€259,26",
        total_str="€1 493,82",  # space thousands, comma decimal
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
    )
    docs.append((doc, _render_standard, False))

    # 12. no_invoice_number ------------------------------------------------
    supplier = Company(
        canonical_name="Quiosc La Rambla",
        country="ES",
        address="La Rambla, 0, 17004 Girona",
        tax_id="00000097C",
        iban="",
        language="ca",
        category="Meals & Entertainment",
    )
    items = [LineItem("Premsa i begudes", 1, 7.80)]
    net, vat, total = 6.45, 1.35, 7.80
    doc = HeldoutDoc(
        file_stem="heldout_no_invoice_number",
        challenge="no_invoice_number",
        language="ca",
        document_type="receipt",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number=None,
        issue_date=date(2026, 7, 9),
        issue_date_printed="09/07/2026",
        due_date=None,
        due_date_printed=None,
        currency="EUR",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "EUR"),
        vat_str=_fmt_money_default(vat, "EUR"),
        total_str=_fmt_money_default(total, "EUR"),
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
    )
    docs.append((doc, _render_standard, False))

    # 13. usd_with_symbol_variants ------------------------------------------
    supplier = Company(
        canonical_name="Pacific Grove Software LLC",
        country="US",
        address="000 Fictional Ave, Pacific Grove, CA 00000",
        tax_id="00-0000098",
        iban="",
        language="en",
        category="Software & Subscriptions",
    )
    items = [LineItem("Cloud API credits — monthly", 1, 1200.00)]
    net, vat, total = 1200.00, 96.00, 1296.00
    doc = HeldoutDoc(
        file_stem="heldout_usd_with_symbol_variants",
        challenge="usd_with_symbol_variants",
        language="en",
        document_type="invoice",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="PGS-2026-3387",
        issue_date=date(2026, 6, 14),
        issue_date_printed="June 14, 2026",
        due_date=date(2026, 7, 14),
        due_date_printed="July 14, 2026",
        currency="USD",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str="US$ 1,200.00",
        vat_str="US$ 96.00",
        total_str="US$ 1,296.00",
        money_fmt=lambda a: _fmt_money_default(a, "USD"),
    )
    docs.append((doc, _render_standard, False))

    # 14. credit_note_es -----------------------------------------------------
    supplier = Company(
        canonical_name="Suministros Garrotxa, S.L.",
        country="ES",
        address="Carrer Mulleres, 0, 17800 Olot",
        tax_id="B00000091",
        iban="ES00 0000 0000 0000 0000 0091",
        language="es",
        category="Office Supplies",
    )
    items = [LineItem("Devolución material defectuoso", 1, -150.00)]
    net, vat, total = -150.00, -31.50, -181.50
    doc = HeldoutDoc(
        file_stem="heldout_credit_note_es",
        challenge="credit_note_es",
        language="es",
        document_type="credit_note",
        supplier=supplier,
        supplier_as_printed=supplier.canonical_name,
        invoice_number="FR-2026-0012",
        issue_date=date(2026, 10, 2),
        issue_date_printed="02/10/2026",
        due_date=None,
        due_date_printed=None,
        currency="EUR",
        line_items=items,
        net=net, vat=vat, total=total,
        net_str=_fmt_money_default(net, "EUR"),
        vat_str=_fmt_money_default(vat, "EUR"),
        total_str=_fmt_money_default(total, "EUR"),
        money_fmt=lambda a: _fmt_money_default(a, "EUR"),
        trap="credit_note",
    )
    docs.append((doc, _render_standard, False))

    return docs


def _answer_entry(doc: HeldoutDoc, file_path: str) -> dict:
    return {
        "file": file_path,
        "supplier": doc.supplier.canonical_name,
        "supplier_as_printed": doc.supplier_as_printed,
        "invoice_number": doc.invoice_number,
        "issue_date": doc.issue_date.isoformat(),
        "due_date": doc.due_date.isoformat() if doc.due_date else None,
        "currency": doc.currency,
        "net": doc.net,
        "vat": doc.vat,
        "total": doc.total,
        "document_type": doc.document_type,
        "language": doc.language,
        "expected_category": doc.category,
        "trap": doc.trap,
        "challenge": doc.challenge,
    }


def generate(out_dir: Path) -> list[dict]:
    invoices_dir = out_dir / "invoices"
    photos_dir = out_dir / "photos"
    invoices_dir.mkdir(parents=True, exist_ok=True)
    photos_dir.mkdir(parents=True, exist_ok=True)

    answer_key: list[dict] = []
    for i, (doc, render_fn, is_photo) in enumerate(build_heldout_docs()):
        if is_photo:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_pdf = Path(tmp) / f"{doc.file_stem}.pdf"
                render_fn(doc, tmp_pdf)
                photo_path = photos_dir / f"{doc.file_stem}.jpg"
                _degrade_to_scan(tmp_pdf, photo_path, seed=SEED + i)
            file_path = f"photos/{doc.file_stem}.jpg"
        else:
            pdf_path = invoices_dir / f"{doc.file_stem}.pdf"
            render_fn(doc, pdf_path)
            file_path = f"invoices/{doc.file_stem}.pdf"
        answer_key.append(_answer_entry(doc, file_path))

    with (out_dir / "answer_key.json").open("w", encoding="utf-8") as f:
        json.dump(answer_key, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return answer_key


def print_summary(answer_key: list[dict]) -> None:
    by_challenge: dict[str, list[str]] = {}
    for entry in answer_key:
        by_challenge.setdefault(entry["challenge"], []).append(entry["file"])

    print("\nHeld-out dataset summary")
    print("=" * 60)
    print(f"{'challenge':<26} {'count':>5}  files")
    print("-" * 60)
    for challenge, files in sorted(by_challenge.items()):
        print(f"{challenge:<26} {len(files):>5}  {', '.join(files)}")
    print("-" * 60)
    print(f"total answer-key entries: {len(answer_key)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"output directory for the held-out dataset (default: {DEFAULT_OUT_DIR})",
    )
    args = parser.parse_args(argv)

    try:
        answer_key = generate(args.out)
    except Exception as exc:  # noqa: BLE001 - CLI entry point, report and exit non-zero
        print(f"error: held-out dataset generation failed: {exc}", file=sys.stderr)
        return 1

    print_summary(answer_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
