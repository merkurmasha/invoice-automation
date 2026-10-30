"""Tests for src/pack/build.py: reproducibility, never summing mixed
currencies, and credit notes keeping their negative sign in ledger.csv.
Writes only to tmp_path - never to the committed data/packs/ (gitignored
anyway, but tests shouldn't depend on it existing)."""

from __future__ import annotations

from datetime import date

from src.pack.build import build_pack, build_summary_md


def test_building_the_same_month_twice_is_byte_identical(tmp_path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    pack1 = build_pack("2026-09", out1, today=date(2026, 10, 28))
    pack2 = build_pack("2026-09", out2, today=date(2026, 10, 28))

    for name in ("ledger.csv", "exceptions.csv", "summary.md"):
        assert (pack1 / name).read_text() == (pack2 / name).read_text(), name


def test_credit_note_keeps_negative_sign_in_the_ledger(tmp_path):
    pack_dir = build_pack("2026-10", tmp_path / "pack", today=date(2026, 10, 28))
    ledger_text = (pack_dir / "ledger.csv").read_text()

    assert "ADB/2026/CN07704" in ledger_text
    line = next(line for line in ledger_text.splitlines() if "ADB/2026/CN07704" in line)
    fields = line.split(",")
    net, vat, total = fields[4], fields[5], fields[6]
    assert net.startswith("-")
    assert vat.startswith("-")
    assert total.startswith("-")


def test_summary_never_sums_different_currencies_together():
    # September's ledger mixes EUR, USD (Figma) and GBP (Pixel & Co) -
    # build_summary_md must keep every total/category breakdown keyed
    # by its own currency, never adding them into one number.
    from src.pack.build import LedgerRow

    rows = [
        LedgerRow(
            date(2026, 9, 1), "Supplier EUR", "INV-EUR", "EUR", 100.0, 21.0, 121.0,
            "Software & Subscriptions", "pass", "open", None,
        ),
        LedgerRow(
            date(2026, 9, 2), "Supplier USD", "INV-USD", "USD", 75.0, 15.75, 90.75,
            "Software & Subscriptions", "pass", "open", None,
        ),
        LedgerRow(
            date(2026, 9, 3), "Supplier GBP", "INV-GBP", "GBP", 900.0, 189.0, 1089.0,
            "Professional Services", "pass", "open", None,
        ),
    ]
    aging_summary = {b: {"count": 0, "outstanding": 0.0} for b in ("current", "1-30", "31-60", "60+")}

    summary = build_summary_md("2026-09", rows, [], aging_summary)

    # Each currency's total appears on its own row - 121.00 (EUR) is
    # never added to 90.75 (USD) or 1089.00 (GBP) anywhere in the text.
    assert "| EUR | 121.00 | 21.00 |" in summary
    assert "| USD | 90.75 | 15.75 |" in summary
    assert "| GBP | 1089.00 | 189.00 |" in summary
    # A blended total across currencies (e.g. 1300.75) must never appear.
    combined = 121.00 + 90.75 + 1089.00
    assert f"{combined:.2f}" not in summary


def test_ledger_rows_are_scoped_to_their_issue_month(tmp_path):
    pack_dir = build_pack("2026-09", tmp_path / "pack", today=date(2026, 10, 28))
    ledger_text = (pack_dir / "ledger.csv").read_text()

    for line in ledger_text.splitlines()[1:]:
        if not line:
            continue
        assert line.startswith("2026-09-"), line
