"""Tests for the dashboard build (scripts/build_dashboard.py and
scripts/dashboard_html.py): the generated HTML builds without errors,
contains every panel, its numbers match the underlying data, it has no
external URLs (no CDN, no network calls — opens offline), and it never
leaks real personal data. No LLM call anywhere in this path."""

from __future__ import annotations

import json
import re
from datetime import date

from scripts import build_dashboard as build_dashboard_module
from scripts.dashboard_data import build_dashboard_data
from scripts.dashboard_html import render

OCTOBER = ("2026-10", date(2026, 10, 28))

_EMAIL_RE = re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9-.]+")
_URL_RE = re.compile(r"https?://")


def _render_october(tmp_path) -> str:
    month, today = OCTOBER
    data = build_dashboard_data(month, today, tmp_path / "no_such_reminder_log.csv")
    return render(data)


def test_builds_without_errors_and_writes_the_file(tmp_path):
    month, today = OCTOBER
    out_path = tmp_path / "dashboard" / "index.html"

    result = build_dashboard_module.run_build_dashboard(month, today, out_path)

    assert result["status"] == "ok"
    assert out_path.exists()
    assert out_path.stat().st_size > 1000
    assert out_path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_html_contains_every_panel(tmp_path):
    html_text = _render_october(tmp_path)

    assert "Costa Brava Studio S.L." in html_text
    assert "Spend by category" in html_text
    assert "Receivables aging" in html_text
    assert "Review queue" in html_text
    assert "Bank reconciliation" in html_text
    assert "Accuracy" in html_text
    assert (
        "Synthetic data. Nothing in this project is sent automatically; "
        "reminders are Gmail drafts a human approves." in html_text
    )


def test_headline_numbers_match_the_underlying_data(tmp_path):
    month, today = OCTOBER
    data = build_dashboard_data(month, today, tmp_path / "no_such_reminder_log.csv")
    html_text = render(data)

    assert "EUR 1,677.47" in html_text  # total spend
    assert "EUR 23,107.68" in html_text  # open receivables
    assert "86.5%" in html_text  # reconciliation match rate
    assert f'<div class="value">{data["headline"]["review_queue_count"]}</div>' in html_text


def test_every_category_total_appears_formatted_in_the_html(tmp_path):
    month, today = OCTOBER
    data = build_dashboard_data(month, today, tmp_path / "no_such_reminder_log.csv")
    html_text = render(data)

    for row in data["spend_by_category"]:
        assert row["category"].replace("&", "&amp;") in html_text
        assert f'{row["currency"]} {row["total"]:,.2f}' in html_text


def test_every_overdue_invoice_appears_in_the_html(tmp_path):
    month, today = OCTOBER
    data = build_dashboard_data(month, today, tmp_path / "no_such_reminder_log.csv")
    html_text = render(data)

    for invoice in data["receivables_aging"]["overdue_invoices"]:
        assert invoice["invoice_number"] in html_text


def test_no_external_urls_anywhere_in_the_page(tmp_path):
    html_text = _render_october(tmp_path)

    assert not _URL_RE.search(html_text)
    assert "<script" not in html_text.lower()
    assert "cdn." not in html_text.lower()


def test_no_email_addresses_or_real_personal_data_leak_into_the_page(tmp_path):
    html_text = _render_october(tmp_path)

    assert not _EMAIL_RE.search(html_text)
    assert "merkurmasha" not in html_text.lower()
    assert "ANTHROPIC_API_KEY" not in html_text
    assert "sk-ant-" not in html_text


def test_supplier_and_customer_names_with_html_special_characters_are_escaped():
    # Build a minimal fake data dict (same shape build_dashboard_data()
    # returns) with characters that would break the page if unescaped.
    data = {
        "company": "Costa Brava Studio S.L.",
        "month": "2026-10",
        "month_label": "October 2026",
        "today": "2026-10-28",
        "headline": {
            "total_spend": [{"currency": "EUR", "total": 1.0}],
            "open_receivables": 1.0,
            "review_queue_count": 1,
            "reconciliation_match_rate_pct": 100.0,
        },
        "spend_by_category": [{"category": "<script>alert(1)</script>", "currency": "EUR", "total": 1.0}],
        "receivables_aging": {
            "buckets": [
                {"bucket": b, "count": 0, "outstanding": 0.0} for b in ("current", "1-30", "31-60", "60+")
            ],
            "overdue_invoices": [
                {
                    "invoice_number": "INV-1",
                    "customer_name": "O'Brien & <Sons>",
                    "currency": "EUR",
                    "due_date": "2026-10-01",
                    "days_overdue": 5,
                    "amount_outstanding": 1.0,
                    "bucket": "1-30",
                    "reminder": None,
                }
            ],
        },
        "review_queue": [
            {
                "invoice_number": "INV-2",
                "supplier": "<b>Evil</b> Supplier",
                "issue_date": "2026-10-02",
                "summary": "Needs review.",
                "issues": [{"severity": "error", "code": "X", "message": "<img src=x onerror=alert(1)>"}],
            }
        ],
        "reconciliation": {
            "total_lines": 1,
            "matched_count": 1,
            "needs_review_count": 0,
            "match_rate_pct": 100.0,
            "by_category": {"auto": 1},
            "needs_review_items": [],
        },
        "accuracy": {
            "missing": [],
            "extraction_synthetic_before_pct": 1.0,
            "extraction_synthetic_after_pct": 1.0,
            "extraction_heldout_pct": 1.0,
            "categorisation_synthetic_pct": 1.0,
            "categorisation_heldout_pct": 1.0,
            "reconciliation_correct": 1,
            "reconciliation_expected": 1,
            "reconciliation_false_matches": 0,
        },
    }

    html_text = render(data)

    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;" in html_text
    assert "<img src=x onerror=alert(1)>" not in html_text
    assert "O&#x27;Brien &amp; &lt;Sons&gt;" in html_text


def test_cli_main_prints_one_json_object_and_exits_zero(tmp_path, capsys):
    exit_code = build_dashboard_module.main(
        ["--month", "2026-10", "--today", "2026-10-28", "--out", str(tmp_path / "index.html")]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert '"status": "ok"' in out
    payload = json.loads(out)
    assert payload["output_path"] == str(tmp_path / "index.html")


def test_cli_main_exits_one_on_bad_today(tmp_path, capsys):
    exit_code = build_dashboard_module.main(
        ["--today", "not-a-date", "--out", str(tmp_path / "index.html")]
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert '"status": "error"' in out


def test_cli_defaults_month_from_today(tmp_path, capsys):
    build_dashboard_module.main(["--today", "2026-10-28", "--out", str(tmp_path / "index.html")])

    out = json.loads(capsys.readouterr().out)
    assert out["month"] == "2026-10"


def test_run_build_dashboard_reports_error_not_crash_on_unwritable_out_dir(tmp_path):
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("")
    month, today = OCTOBER

    result = build_dashboard_module.run_build_dashboard(month, today, blocking_file / "index.html")

    assert result["status"] == "error"
    assert "error" in result
