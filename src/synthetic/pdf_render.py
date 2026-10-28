"""Renders InvoiceJob objects to PDF files with varied layouts, fonts and colours.

Font note: Catalan uses accented characters (à, è, í, ï, ò, ú, ç) and the
"ela geminada" middle dot (l·l). Reportlab's built-in fonts (Helvetica,
Times-Roman) use WinAnsiEncoding, which covers most of these, but to
guarantee every accented character renders correctly - and to get a third
distinct typeface for visual variety - we bundle DejaVu Sans (a free,
open-licensed font) in assets/fonts/. See assets/fonts/DEJAVU-LICENSE.txt
for its license; it was downloaded from the official project release at
https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from src.synthetic.jobs import CURRENCY_SYMBOL, VAT_LABEL, InvoiceJob
from src.synthetic.suppliers import OUR_COMPANY

ASSETS_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

_FONTS_REGISTERED = False


def _register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("DejaVuSans", str(ASSETS_FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(ASSETS_FONT_DIR / "DejaVuSans-Bold.ttf")))
    _FONTS_REGISTERED = True


FONT_CHOICES = [
    ("Helvetica", "Helvetica-Bold"),
    ("Times-Roman", "Times-Bold"),
    ("DejaVuSans", "DejaVuSans-Bold"),
]

ACCENT_COLORS = [
    "#1B4965",  # navy
    "#6B2737",  # maroon
    "#0B6E4F",  # dark green
    "#264653",  # slate
    "#8A5A44",  # brown
    "#3C3C3C",  # near-black grey
]

LABELS = {
    "en": {
        "invoice": "INVOICE",
        "credit_note": "CREDIT NOTE",
        "bill_to": "Bill to",
        "invoice_no": "Invoice no.",
        "issue_date": "Issue date",
        "due_date": "Due date",
        "description": "Description",
        "qty": "Qty",
        "unit_price": "Unit price",
        "amount": "Amount",
        "subtotal": "Subtotal",
        "total": "Total",
        "payment_details": "Payment details",
        "tax_id": "Tax ID",
        "reverse_charge": "VAT reverse-charged to the customer - Art. 196 Dir. 2006/112/EC",
    },
    "es": {
        "invoice": "FACTURA",
        "credit_note": "NOTA DE ABONO",
        "bill_to": "Facturar a",
        "invoice_no": "Nº factura",
        "issue_date": "Fecha de emisión",
        "due_date": "Fecha de vencimiento",
        "description": "Descripción",
        "qty": "Cant.",
        "unit_price": "Precio unit.",
        "amount": "Importe",
        "subtotal": "Subtotal",
        "total": "Total",
        "payment_details": "Datos de pago",
        "tax_id": "NIF/CIF",
        "reverse_charge": "IVA repercutido al destinatario - inversión del sujeto pasivo",
    },
    "ca": {
        "invoice": "FACTURA",
        "credit_note": "NOTA D'ABONAMENT",
        "bill_to": "Facturar a",
        "invoice_no": "Núm. factura",
        "issue_date": "Data d'emissió",
        "due_date": "Data de venciment",
        "description": "Descripció",
        "qty": "Quant.",
        "unit_price": "Preu unit.",
        "amount": "Import",
        "subtotal": "Subtotal",
        "total": "Total",
        "payment_details": "Dades de pagament",
        "tax_id": "NIF",
        "reverse_charge": "IVA repercutit al destinatari - inversió del subjecte passiu",
    },
}


def _fonts_for(job: InvoiceJob) -> tuple[str, str]:
    if job.language == "ca":
        return FONT_CHOICES[2]
    return FONT_CHOICES[job.layout_seed % 3]


def _address_lines(address: str) -> list[str]:
    """Groups comma-separated address fragments two at a time, so e.g.
    "Carrer Nou, 22, 17600 Figueres" prints as "Carrer Nou, 22" /
    "17600 Figueres" instead of one fragment per line."""
    parts = address.split(", ")
    return [", ".join(parts[i : i + 2]) for i in range(0, len(parts), 2)]


def _fmt_money(amount: float, currency: str) -> str:
    symbol = CURRENCY_SYMBOL[currency]
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol}{abs(amount):,.2f}"


def render_invoice_pdf(job: InvoiceJob, output_path: Path) -> None:
    _register_fonts()
    labels = LABELS[job.language]
    regular, bold = _fonts_for(job)
    accent = HexColor(ACCENT_COLORS[job.layout_seed % len(ACCENT_COLORS)])
    layout = job.layout_seed % 4

    # invariant=1 strips the creation-timestamp/file-ID reportlab would
    # otherwise embed, so re-running the generator produces byte-for-byte
    # identical PDFs, not just identical visible content.
    c = canvas.Canvas(str(output_path), pagesize=A4, invariant=1)
    width, height = A4
    margin = 20 * mm
    y = height - margin

    title = labels["credit_note"] if job.document_type == "credit_note" else labels["invoice"]

    # --- header -------------------------------------------------------
    if layout == 1:
        band_height = 28 * mm
        c.setFillColor(accent)
        c.rect(0, height - band_height, width, band_height, stroke=0, fill=1)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont(bold, 20)
        c.drawString(margin, height - band_height / 2 - 4, title)
        c.setFont(regular, 10)
        c.drawRightString(width - margin, height - band_height / 2 - 4, job.supplier_as_printed)
        c.setFillColor(HexColor("#000000"))
        y = height - band_height - 12 * mm
    elif layout == 3:
        c.setFont(bold, 16)
        c.setFillColor(accent)
        c.drawCentredString(width / 2, y, title)
        c.setFillColor(HexColor("#000000"))
        y -= 10 * mm
    else:
        c.setFont(bold, 18)
        c.setFillColor(accent)
        c.drawString(margin, y, title)
        c.setFillColor(HexColor("#000000"))
        c.setFont(regular, 10)
        c.drawRightString(width - margin, y, job.supplier_as_printed)
        y -= 10 * mm
        if layout != 2:
            c.setStrokeColor(accent)
            c.line(margin, y, width - margin, y)
            y -= 6 * mm

    # --- supplier / client two-column block ----------------------------
    col2_x = width / 2 + 5 * mm
    top_of_block = y
    c.setFont(bold, 10)
    c.drawString(margin, y, job.supplier_as_printed)
    c.setFont(regular, 9)
    y -= 5 * mm
    for line in _address_lines(job.supplier_address):
        c.drawString(margin, y, line)
        y -= 4.5 * mm
    c.drawString(margin, y, f"{labels['tax_id']}: {job.supplier_tax_id}")
    y -= 4.5 * mm
    if job.supplier_iban:
        c.drawString(margin, y, f"IBAN: {job.supplier_iban}")
        y -= 4.5 * mm

    y2 = top_of_block
    c.setFont(bold, 10)
    c.drawString(col2_x, y2, labels["bill_to"])
    c.setFont(regular, 9)
    y2 -= 5 * mm
    c.drawString(col2_x, y2, OUR_COMPANY.canonical_name)
    y2 -= 4.5 * mm
    for line in _address_lines(OUR_COMPANY.address):
        c.drawString(col2_x, y2, line)
        y2 -= 4.5 * mm
    c.drawString(col2_x, y2, f"{labels['tax_id']}: {OUR_COMPANY.tax_id}")
    y2 -= 4.5 * mm

    y = min(y, y2) - 6 * mm

    # --- meta row: invoice no / issue date / due date -------------------
    c.setFont(bold, 9)
    meta_items = [
        (labels["invoice_no"], job.invoice_number),
        (labels["issue_date"], job.issue_date.strftime("%d/%m/%Y")),
    ]
    if job.due_date is not None:
        meta_items.append((labels["due_date"], job.due_date.strftime("%d/%m/%Y")))
    col_width = (width - 2 * margin) / len(meta_items)
    for i, (label, value) in enumerate(meta_items):
        x = margin + i * col_width
        c.setFont(bold, 8)
        c.drawString(x, y, label.upper())
        c.setFont(regular, 10)
        c.drawString(x, y - 4.5 * mm, value)
    y -= 12 * mm

    # --- line item table --------------------------------------------------
    col_desc_x = margin
    col_qty_x = width - margin - 55 * mm
    col_price_x = width - margin - 38 * mm
    col_amount_x = width - margin

    c.setFillColor(accent)
    c.rect(margin, y - 2 * mm, width - 2 * margin, 7 * mm, stroke=0, fill=1)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont(bold, 8)
    c.drawString(col_desc_x + 2, y, labels["description"])
    c.drawString(col_qty_x, y, labels["qty"])
    c.drawRightString(col_price_x + 20 * mm, y, labels["unit_price"])
    c.drawRightString(col_amount_x, y, labels["amount"])
    c.setFillColor(HexColor("#000000"))
    y -= 8 * mm

    c.setFont(regular, 9)
    for item in job.line_items:
        c.drawString(col_desc_x + 2, y, item.description)
        c.drawString(col_qty_x, y, f"{item.qty:g}")
        c.drawRightString(col_price_x + 20 * mm, y, _fmt_money(item.unit_price, job.currency))
        c.drawRightString(col_amount_x, y, _fmt_money(item.line_total, job.currency))
        y -= 6 * mm

    y -= 2 * mm
    c.setStrokeColor(HexColor("#999999"))
    c.line(margin, y, width - margin, y)
    y -= 8 * mm

    # --- totals box ---------------------------------------------------
    totals_x_label = width - margin - 60 * mm
    c.setFont(regular, 9)
    c.drawString(totals_x_label, y, labels["subtotal"])
    c.drawRightString(col_amount_x, y, _fmt_money(job.net, job.currency))
    y -= 5.5 * mm

    if job.trap == "reverse_charge":
        c.setFont(regular, 8)
        c.drawString(totals_x_label, y, labels["reverse_charge"])
        y -= 5.5 * mm
    else:
        c.setFont(regular, 9)
        vat_pct = job.vat_rate * 100
        c.drawString(totals_x_label, y, f"{VAT_LABEL[job.language]} ({vat_pct:g}%)")
        c.drawRightString(col_amount_x, y, _fmt_money(job.vat, job.currency))
        y -= 5.5 * mm

    c.setStrokeColor(accent)
    c.line(totals_x_label, y + 5 * mm, width - margin, y + 5 * mm)
    c.setFont(bold, 11)
    c.setFillColor(accent)
    c.drawString(totals_x_label, y, labels["total"])
    c.drawRightString(col_amount_x, y, _fmt_money(job.printed_total, job.currency))
    c.setFillColor(HexColor("#000000"))
    y -= 14 * mm

    # --- footer: payment details ---------------------------------------
    if job.supplier_iban:
        c.setFont(bold, 8)
        c.drawString(margin, y, labels["payment_details"])
        c.setFont(regular, 8)
        c.drawString(margin, y - 4.5 * mm, f"IBAN: {job.supplier_iban}")

    c.showPage()
    c.save()
