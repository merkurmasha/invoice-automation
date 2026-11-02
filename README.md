# invoice-automation

An automated pipeline that extracts, validates, files, and reconciles
invoices and receipts for a small business, turning piles of messy
documents into clean records and an accountant-ready pack. Built as a
portfolio project around a fictional Barcelona-based company, **Costa
Brava Studio S.L.**

## Build phases

1. **Extraction and validation** — read invoices/receipts/photos into
   structured data and check it for correctness.
2. **Filing, suppliers, and categorisation** — organise documents and
   classify expenses by supplier and category.
3. **Receivables and follow-up** — track money owed and draft reminders.
4. **Reconciliation and accountant pack** — match records against bank
   data and produce a handoff package.
5. **Dashboard and portfolio packaging** — present the results.

## Dashboard

A single self-contained HTML file — no server, no external CDN, no
login — summarising spend, receivables, the review queue, bank
reconciliation, and this project's own eval accuracy numbers.

```
python -m scripts.build_dashboard
```

Writes `dashboard/index.html`; open it by double-clicking. It only
reads this project's own synthetic data and already-committed eval
result files (`evals/results/`) — no API key needed, nothing is sent
anywhere. Defaults to the same demo "today" (2026-10-28) the rest of
the project uses; pass `--month YYYY-MM`, `--today YYYY-MM-DD`, or
`--out path/to/file.html` to override. See `scripts/dashboard_data.py`
for exactly which panels are scoped to the given month versus the
whole book/statement.

The build is deterministic (same inputs → byte-identical output), so
`dashboard/index.html` is committed to the repo rather than
gitignored — regenerate it after changing `--month`/`--today` or any
of the underlying synthetic data, and commit the new version.

## Live dashboard

The committed `dashboard/index.html` above is generated entirely from
this project's synthetic/fictional data (see "Dashboard" above) — no
real company, customer, or financial data anywhere in it. A live copy
is published via GitHub Pages: **[TODO: add the GitHub Pages URL
here]**.

## License

See [LICENSE](LICENSE).
