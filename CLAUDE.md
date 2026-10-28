# Project rules — invoice-automation

This is a portfolio project: an invoice and receipt automation pipeline
for a fictional Barcelona-based company, "Costa Brava Studio S.L.". The
developer is a beginner, so explain new concepts in plain language.

## Role of the LLM (Claude API)

The LLM is used ONLY for three jobs:

1. Reading messy documents (extracting data from invoices/receipts/photos).
2. Categorising expenses.
3. Drafting reminder text.

All arithmetic, duplicate detection, fuzzy matching, aging, and
reconciliation are plain deterministic code, with unit tests. Never use
the LLM for things plain code can do reliably.

## Safety rules

- Nothing is ever sent automatically. Reminders are created as Gmail
  drafts only — a human reviews and sends them.
- No real personal or financial data anywhere, ever. Synthetic data only.
- Never read, print, or commit `.env` or any API key.

## Testing rules

- Tests must never call the Claude API — mock it. Live API calls happen
  only in the eval harness (`evals/`).
- Every module gets tests before the next module starts.

## Git rules

- Never commit directly to `main`.
- Never push unless explicitly asked.
- One branch per phase.
- Small commits with clear messages.

## Communication

- Explain new concepts in plain language — the developer is learning as
  they go.
