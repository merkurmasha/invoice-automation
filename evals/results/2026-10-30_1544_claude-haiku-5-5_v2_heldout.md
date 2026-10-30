# Eval run — claude-haiku-5-5 — 2026-10-30_1544

## Run metadata

- Model: `claude-haiku-5-5`
- Prompt version: `v2`
- Wall-clock time: 31.3s
- Tokens used this run — input: 55269, output: 5461
- Not cached / skipped: 0
- Extraction failures: 0

## Field-level accuracy

**Overall: 138/140 fields correct (98.6%)**

### By document type

| Group | Correct | Total | Accuracy |
| --- | --- | --- | --- |
| pdf | 128 | 130 | 98.5% |
| photo | 10 | 10 | 100.0% |

### By language

| Group | Correct | Total | Accuracy |
| --- | --- | --- | --- |
| ca | 69 | 70 | 98.6% |
| en | 39 | 40 | 97.5% |
| es | 30 | 30 | 100.0% |

### By currency

| Group | Correct | Total | Accuracy |
| --- | --- | --- | --- |
| EUR | 108 | 110 | 98.2% |
| GBP | 10 | 10 | 100.0% |
| USD | 20 | 20 | 100.0% |

### By challenge

| Group | Correct | Total | Accuracy |
| --- | --- | --- | --- |
| credit_note_es | 10 | 10 | 100.0% |
| european_numbers | 10 | 10 | 100.0% |
| handwritten_note | 10 | 10 | 100.0% |
| multi_page | 9 | 10 | 90.0% |
| multiple_vat_rates | 10 | 10 | 100.0% |
| no_invoice_number | 9 | 10 | 90.0% |
| scan_like | 10 | 10 | 100.0% |
| tax_inclusive | 10 | 10 | 100.0% |
| two_column_layout | 10 | 10 | 100.0% |
| us_date | 10 | 10 | 100.0% |
| usd_with_symbol_variants | 10 | 10 | 100.0% |
| written_month | 30 | 30 | 100.0% |

## Validation / trap scoring

### Trap outcomes

| Trap | Caught | Total | Expectation |
| --- | --- | --- | --- |
| credit_note | 1 | 1 | must NOT include MATH_MISMATCH or a negative-amount issue (CREDIT_NOTE_NOT_NEGATIVE / INVOICE_NEGATIVE_TOTAL) — MISSING_DUE_DATE alone is acceptable |
| no_trap | 12 | 13 | must NOT include any error (a LOW_CONFIDENCE warning alone is a soft flag) |

**False flags:** 1 clean document(s) got an unexpected error.

| Issue code | Count |
| --- | --- |
| MISSING_FIELD | 1 |

**Soft flags (LOW_CONFIDENCE warning, not counted as a failure):** 2

## Photo vs. source PDF

_No photo had both itself and its source PDF extracted this run._

## Misses

### Field mismatches

| File | Field | Expected | Actual | Confidence |
| --- | --- | --- | --- | --- |
| invoices/heldout_multi_page.pdf | supplier | Meridian Consulting Group, S.L. | MCG | 0.60 |
| invoices/heldout_no_invoice_number.pdf | document_type | receipt | invoice | 0.95 |

### Trap misses

| File | Trap | Detail |
| --- | --- | --- |
| invoices/heldout_no_invoice_number.pdf | no_trap | expected: must NOT include any error (a LOW_CONFIDENCE warning alone is a soft flag); got issues=['MISSING_DUE_DATE', 'MISSING_FIELD'] |

## Confidence sanity check

### 5 lowest-confidence *correct* fields

| File | Field | Expected | Actual | Confidence |
| --- | --- | --- | --- | --- |
| invoices/heldout_us_date.pdf | issue_date | 2026-03-04 | 2026-03-04 | 0.60 |
| invoices/heldout_multiple_vat_rates.pdf | vat | 185.0 | 185.0 | 0.85 |
| photos/heldout_scan_like.jpg | supplier | Ferreteria El Martell, S.L. | Ferreteria El Martell, S.L. | 0.85 |
| invoices/heldout_european_numbers.pdf | language | es | es | 0.90 |
| invoices/heldout_handwritten_note.pdf | supplier | Cafeteria Pont Vell | Cafeteria Pont Vell | 0.90 |

### Wrong fields with confidence above 0.90

| File | Field | Expected | Actual | Confidence |
| --- | --- | --- | --- | --- |
| invoices/heldout_no_invoice_number.pdf | document_type | receipt | invoice | 0.95 |
