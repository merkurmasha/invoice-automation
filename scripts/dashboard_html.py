"""Renders the dict scripts/dashboard_data.build_dashboard_data() returns
into one self-contained HTML page: no external stylesheet, script, font,
or image — everything is inline, so the file opens by double-clicking
it, offline, with no server and no login. See scripts/build_dashboard.py
for the CLI that writes this to dashboard/index.html.

Color roles below (CSS custom properties, light + dark values) come
from the project's dataviz skill's reference palette — chosen, not
guessed, so the categorical hues and status colors stay colorblind-safe
and contrast-checked in both themes. Categorical slots are assigned to
whichever categories appear in the selected month, in a fixed
alphabetical order, so re-running for a different month never shuffles
colors depending on totals.
"""

from __future__ import annotations

import html

# --- Palette (from the dataviz skill's references/palette.md) -------------

_CATEGORICAL_LIGHT = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#6250d6", "#e34948",
]
_CATEGORICAL_DARK = [
    "#3987e5", "#d95926", "#199e70", "#c98500",
    "#d55181", "#008300", "#9085e9", "#e66767",
]

_STATUS_LIGHT = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
_STATUS_DARK = _STATUS_LIGHT  # same four steps clear 3:1 on the dark surface too

_BUCKET_STATUS = {"current": "good", "1-30": "warning", "31-60": "serious", "60+": "critical"}
_BUCKET_ICON = {"current": "●", "1-30": "▲", "31-60": "▲", "60+": "■"}
_BUCKET_TITLE = {
    "current": "Current",
    "1-30": "1–30 days overdue",
    "31-60": "31–60 days overdue",
    "60+": "60+ days overdue",
}

_DECISION_LABEL = {
    "auto": "Auto-matched", "partial": "Partial payment", "combo": "Combo payment",
    "possible": "Possible match", "ambiguous": "Ambiguous", "unmatched": "Unmatched",
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _money(amount: float, currency: str) -> str:
    sign = "−" if amount < 0 else ""
    return f"{sign}{currency} {abs(amount):,.2f}"


def _pct(value: float) -> str:
    return f"{value:.1f}%"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _css() -> str:
    return """
:root {
  color-scheme: light;
  --surface-page: #f9f9f7;
  --surface-card: #fcfcfb;
  --ink-primary: #0b0b0b;
  --ink-secondary: #52514e;
  --ink-muted: #898781;
  --gridline: #e1e0d9;
  --border: rgba(11,11,11,0.10);
  --cat-1: #2a78d6; --cat-2: #eb6834; --cat-3: #1baf7a; --cat-4: #eda100;
  --cat-5: #e87ba4; --cat-6: #008300; --cat-7: #6250d6; --cat-8: #e34948;
  --status-good: #0ca30c; --status-warning: #fab219;
  --status-serious: #ec835a; --status-critical: #d03b3b;
  --status-good-label: #ffffff; --status-warning-label: #0b0b0b;
  --status-serious-label: #ffffff; --status-critical-label: #ffffff;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --surface-page: #0d0d0d;
    --surface-card: #1a1a19;
    --ink-primary: #f0efec;
    --ink-secondary: #c3c2b7;
    --ink-muted: #898781;
    --gridline: #2c2c2a;
    --border: rgba(255,255,255,0.10);
    --cat-1: #3987e5; --cat-2: #d95926; --cat-3: #199e70; --cat-4: #c98500;
    --cat-5: #d55181; --cat-6: #008300; --cat-7: #9085e9; --cat-8: #e66767;
    --status-warning-label: #0b0b0b;
  }
}
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0; background: var(--surface-page); color: var(--ink-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}
body { padding: 16px; max-width: 1100px; margin: 0 auto; }
h1, h2, h3 { font-weight: 600; margin: 0; }
h1 { font-size: 1.5rem; }
h2 { font-size: 1.05rem; margin-bottom: 4px; }
p { margin: 4px 0; }
.muted { color: var(--ink-muted); font-size: 0.85rem; }
.secondary { color: var(--ink-secondary); }
header.top {
  display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between;
  gap: 8px; padding: 16px 0 8px 0; border-bottom: 1px solid var(--gridline); margin-bottom: 16px;
}
.stat-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px;
}
@media (max-width: 720px) { .stat-grid { grid-template-columns: repeat(2, 1fr); } }
.stat-tile {
  background: var(--surface-card); border: 1px solid var(--border); border-radius: 10px;
  padding: 14px; min-width: 0;
}
.stat-tile .value { font-size: 1.6rem; font-weight: 600; line-height: 1.2; }
.stat-tile .label { font-size: 0.8rem; color: var(--ink-secondary); margin-top: 2px; }
.panel {
  background: var(--surface-card); border: 1px solid var(--border); border-radius: 10px;
  padding: 16px; margin-bottom: 20px;
}
.panel-head { margin-bottom: 12px; }
.bar-row { display: grid; grid-template-columns: 180px 1fr auto; align-items: center; gap: 10px; margin: 8px 0; }
@media (max-width: 720px) { .bar-row { grid-template-columns: 110px 1fr auto; font-size: 0.85rem; } }
.bar-label { color: var(--ink-primary); overflow-wrap: anywhere; }
.bar-track { background: var(--gridline); border-radius: 4px; height: 18px; position: relative; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px 0 0 4px; }
.bar-value { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; color: var(--ink-secondary); }
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--gridline); vertical-align: top; }
th { color: var(--ink-secondary); font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.02em; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.table-wrap { overflow-x: auto; }
.badge {
  display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 999px;
  font-size: 0.78rem; font-weight: 600; white-space: nowrap;
}
.badge-good { background: var(--status-good); color: var(--status-good-label); }
.badge-warning { background: var(--status-warning); color: var(--status-warning-label); }
.badge-serious { background: var(--status-serious); color: var(--status-serious-label); }
.badge-critical { background: var(--status-critical); color: var(--status-critical-label); }
.bucket-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; }
@media (max-width: 720px) { .bucket-grid { grid-template-columns: repeat(2, 1fr); } }
.bucket-card { border: 1px solid var(--border); border-radius: 8px; padding: 10px; }
.bucket-card .count { font-size: 1.3rem; font-weight: 600; }
.recon-bar { display: flex; height: 22px; border-radius: 6px; overflow: hidden; border: 1px solid var(--border); margin: 10px 0; }
.recon-seg-matched { background: var(--status-good); }
.recon-seg-review { background: var(--status-warning); }
.legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 0.85rem; color: var(--ink-secondary); margin-bottom: 4px; }
.legend-dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: middle; }
.accuracy-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
@media (max-width: 960px) { .accuracy-grid { grid-template-columns: repeat(2, 1fr); } }
.accuracy-tile .value { font-size: 1.3rem; font-weight: 600; }
.accuracy-tile .sub { font-size: 0.72rem; color: var(--ink-muted); margin-top: 2px; }
footer { color: var(--ink-muted); font-size: 0.8rem; padding: 16px 0; border-top: 1px solid var(--gridline); margin-top: 8px; }
.empty { color: var(--ink-muted); font-style: italic; font-size: 0.9rem; }
""".strip()


def _stat_tile(value: str, label: str) -> str:
    return f'<div class="stat-tile"><div class="value">{value}</div><div class="label">{esc(label)}</div></div>'


def _header(data: dict) -> str:
    headline = data["headline"]
    spend = headline["total_spend"]
    spend_html = "<br>".join(_money(row["total"], row["currency"]) for row in spend) if spend else "—"
    tiles = [
        _stat_tile(spend_html, f"Total spend — {esc(data['month_label'])}"),
        _stat_tile(_money(headline["open_receivables"], "EUR"), "Open receivables — whole book"),
        _stat_tile(str(headline["review_queue_count"]), f"In review queue — {esc(data['month_label'])}"),
        _stat_tile(_pct(headline["reconciliation_match_rate_pct"]), "Reconciliation match rate — whole statement"),
    ]
    return f"""
<header class="top">
  <div>
    <h1>{esc(data['company'])}</h1>
    <p class="muted">Operations dashboard — {esc(data['month_label'])} (as of {esc(data['today'])})</p>
    <p class="muted">"{esc(data['today'])}" is a fixed demo date, not live — the bank statement below runs
    through {esc(data['bank_statement_through'])}.</p>
  </div>
</header>
<div class="stat-grid">{''.join(tiles)}</div>
""".strip()


def _category_bars(data: dict) -> str:
    rows = data["spend_by_category"]
    if not rows:
        return '<p class="empty">No invoices this month.</p>'
    categories = sorted({row["category"] for row in rows})
    slot_of = {category: i % 8 for i, category in enumerate(categories)}
    max_total = max(abs(row["total"]) for row in rows) or 1.0
    bars = []
    for row in rows:
        slot = slot_of[row["category"]] + 1
        width = round(100 * abs(row["total"]) / max_total, 1)
        bars.append(
            f'<div class="bar-row">'
            f'<div class="bar-label">{esc(row["category"])}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width}%;background:var(--cat-{slot});"></div></div>'
            f'<div class="bar-value">{esc(_money(row["total"], row["currency"]))}</div>'
            f"</div>"
        )
    return "".join(bars)


def _aging_buckets(data: dict) -> str:
    cards = []
    for bucket in data["receivables_aging"]["buckets"]:
        status = _BUCKET_STATUS[bucket["bucket"]]
        cards.append(
            f'<div class="bucket-card">'
            f'<div class="badge badge-{status}">{_BUCKET_ICON[bucket["bucket"]]} {esc(_BUCKET_TITLE[bucket["bucket"]])}</div>'
            f'<div class="count">{bucket["count"]}</div>'
            f'<div class="secondary">{esc(_money(bucket["outstanding"], "EUR"))} outstanding</div>'
            f"</div>"
        )
    return f'<div class="bucket-grid">{"".join(cards)}</div>'


def _reminder_legend(data: dict) -> str:
    parts = []
    for entry in data["receivables_aging"]["reminder_stage_legend"]:
        when = "on the due date" if entry["days_after_due"] == 0 else f'{entry["days_after_due"]} day(s) after the due date'
        parts.append(f'stage {entry["stage"]} ({esc(entry["label"])}) {when}')
    return (
        '<p class="muted">Reminder stages: ' + "; ".join(parts) + " — only the latest stage that's "
        "come due and hasn't been sent yet is ever shown for an invoice.</p>"
    )


def _overdue_table(data: dict) -> str:
    rows = [r for r in data["receivables_aging"]["overdue_invoices"]]
    if not rows:
        return '<p class="empty">No overdue invoices — everything is current.</p>'
    body = []
    for row in rows:
        status = _BUCKET_STATUS[row["bucket"]]
        reminder = row["reminder"]
        reminder_html = f'{esc(reminder["stage_label"])} (stage {reminder["stage"]})' if reminder else "—"
        body.append(
            "<tr>"
            f'<td>{esc(row["invoice_number"])}</td>'
            f'<td>{esc(row["customer_name"])}</td>'
            f'<td>{esc(row["due_date"])}</td>'
            f'<td class="num">{row["days_overdue"]}</td>'
            f'<td class="num">{esc(_money(row["amount_outstanding"], row["currency"]))}</td>'
            f'<td><span class="badge badge-{status}">{esc(_BUCKET_TITLE[row["bucket"]])}</span></td>'
            f"<td>{reminder_html}</td>"
            "</tr>"
        )
    return f"""
<div class="table-wrap">
<table>
<thead><tr><th>Invoice</th><th>Customer</th><th>Due</th><th class="num">Days overdue</th>
<th class="num">Outstanding</th><th>Bucket</th><th>Reminder stage</th></tr></thead>
<tbody>{''.join(body)}</tbody>
</table>
</div>
""".strip()


def _review_queue_table(data: dict) -> str:
    rows = data["review_queue"]
    if not rows:
        return '<p class="empty">Nothing needs review this month — every invoice passed validation.</p>'
    body = []
    for row in rows:
        reasons = "; ".join(issue["message"] for issue in row["issues"])
        body.append(
            "<tr>"
            f'<td>{esc(row["invoice_number"])}</td>'
            f'<td>{esc(row["supplier"])}</td>'
            f'<td>{esc(row["issue_date"])}</td>'
            f"<td>{esc(reasons)}</td>"
            "</tr>"
        )
    return f"""
<div class="table-wrap">
<table>
<thead><tr><th>Invoice</th><th>Supplier</th><th>Issue date</th><th>Why it needs a human</th></tr></thead>
<tbody>{''.join(body)}</tbody>
</table>
</div>
""".strip()


def _reconciliation(data: dict) -> str:
    recon = data["reconciliation"]
    total = recon["total_lines"] or 1
    matched_width = round(100 * recon["matched_count"] / total, 1)
    review_width = round(100 - matched_width, 1)
    legend = (
        f'<span class="legend"><span><span class="legend-dot" style="background:var(--status-good)"></span>'
        f'Matched automatically ({recon["matched_count"]})</span>'
        f'<span><span class="legend-dot" style="background:var(--status-warning)"></span>'
        f'Needs a human ({recon["needs_review_count"]})</span></span>'
    )
    bar = (
        f'<div class="recon-bar">'
        f'<div class="recon-seg-matched" style="width:{matched_width}%"></div>'
        f'<div class="recon-seg-review" style="width:{review_width}%"></div>'
        f"</div>"
    )
    items = recon["needs_review_items"]
    if items:
        body = []
        for item in items:
            invoices = ", ".join(item["invoice_numbers"]) or "—"
            body.append(
                "<tr>"
                f'<td>{esc(item["bank_date"])}</td>'
                f'<td>{esc(item["description"])}</td>'
                f'<td class="num">{esc(_money(item["amount"], "EUR"))}</td>'
                f'<td>{esc(_DECISION_LABEL.get(item["category"], item["category"]))}</td>'
                f'<td>{esc(invoices)}</td>'
                f'<td>{esc(item["reason"])}</td>'
                "</tr>"
            )
        table = f"""
<div class="table-wrap">
<table>
<thead><tr><th>Bank date</th><th>Description</th><th class="num">Amount</th><th>Status</th><th>Invoice(s)</th><th>Why</th></tr></thead>
<tbody>{''.join(body)}</tbody>
</table>
</div>
""".strip()
    else:
        table = '<p class="empty">Every bank line matched automatically.</p>'
    summary = (
        f'<p class="secondary">{_plural(total, "bank line")} in this statement — '
        f'{_pct(recon["match_rate_pct"])} matched automatically; the rest goes to a human to confirm.</p>'
    )
    return f"{summary}{legend}{bar}{table}"


def _accuracy(data: dict) -> str:
    acc = data["accuracy"]
    tiles = [
        (
            f'{acc["extraction_synthetic_before_pct"]:.1f}% → {acc["extraction_synthetic_after_pct"]:.1f}%',
            "Extraction (synthetic)",
            "field-level accuracy, prompt v1 → v2",
        ),
        (f'{acc["extraction_heldout_pct"]:.1f}%', "Extraction (held-out)", "documents never used while building the prompt"),
        (f'{acc["categorisation_synthetic_pct"]:.1f}%', "Categorisation (synthetic)", "category assigned correctly"),
        (f'{acc["categorisation_heldout_pct"]:.1f}%', "Categorisation (held-out)", "category assigned correctly"),
        (
            f'{acc["reconciliation_correct"]}/{acc["reconciliation_expected"]}',
            "Reconciliation (test set)",
            f'{acc["reconciliation_false_matches"]} false matches',
        ),
    ]
    cells = "".join(
        f'<div class="stat-tile accuracy-tile"><div class="value">{esc(value)}</div>'
        f'<div class="label">{esc(label)}</div><div class="sub">{esc(sub)}</div></div>'
        for value, label, sub in tiles
    )
    if acc["missing"]:
        source_note = (
            f'<p class="muted">Note: no eval result file was found for {esc(", ".join(acc["missing"]))}; '
            "showing this project's last known hardcoded figures instead (see scripts/eval_summary.py).</p>"
        )
    else:
        source_note = '<p class="muted">Read live from this project\'s own eval result files in evals/results/ — see evals/ for the harness that produced them.</p>'
    fairness_note = (
        '<p class="muted">Categorisation and matching were tuned on synthetic data; '
        "the held-out figures are the fairer measure.</p>"
    )
    return f'<div class="accuracy-grid">{cells}</div>{source_note}{fairness_note}'


def render(data: dict) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(data['company'])} — Dashboard</title>
<style>{_css()}</style>
</head>
<body>
{_header(data)}

<section class="panel">
  <div class="panel-head"><h2>Spend by category</h2><p class="muted">{esc(data['month_label'])} — supplier invoices issued that month</p></div>
  {_category_bars(data)}
</section>

<section class="panel">
  <div class="panel-head"><h2>Receivables aging</h2><p class="muted">Whole book, as of {esc(data['today'])} — not just {esc(data['month_label'])}</p></div>
  {_aging_buckets(data)}
  {_reminder_legend(data)}
  {_overdue_table(data)}
</section>

<section class="panel">
  <div class="panel-head"><h2>Review queue</h2><p class="muted">{esc(data['month_label'])} — invoices a human needs to look at before they're filed</p></div>
  {_review_queue_table(data)}
</section>

<section class="panel">
  <div class="panel-head"><h2>Bank reconciliation</h2><p class="muted">Whole bank statement period</p></div>
  {_reconciliation(data)}
</section>

<section class="panel">
  <div class="panel-head"><h2>Accuracy</h2><p class="muted">From this project's own evaluation runs (see evals/)</p></div>
  {_accuracy(data)}
</section>

<footer>
  <p>Built from this project's synthetic data (demo date {esc(data['today'])}, month {esc(data['month_label'])}).</p>
  <p>Synthetic data. Nothing in this project is sent automatically; reminders are Gmail drafts a human approves.</p>
</footer>
</body>
</html>
"""
