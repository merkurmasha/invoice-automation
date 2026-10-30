# Supplier matching + categorisation eval — claude-haiku-5-5 — 2026-10-30_1621

## Run metadata

- Model: `claude-haiku-5-5`
- Categorisation prompt version: `v1`
- Dataset: `heldout`
- Tokens used this run — input: 19189, output: 2029

## (a) Supplier merge accuracy

- Missed merges (same real supplier, different supplier_id assigned): 0
- False merges (different real suppliers given the same supplier_id): 0

| Match status | Count |
| --- | --- |
| new | 14 |

## (b) Categorisation accuracy

**Overall: 9/14 correct (64.3%)**

- Routed to review queue for low confidence: 14

| File | Supplier | Expected | Actual | Confidence | Correct |
| --- | --- | --- | --- | --- | --- |
| invoices/heldout_credit_note_es.pdf | Suministros Garrotxa, S.L. | office_supplies_furniture | other | 0.20 | NO |
| invoices/heldout_european_numbers.pdf | Maquinària Industrial Girona, S.L. | other | other | 0.20 | yes |
| invoices/heldout_handwritten_note.pdf | Cafeteria Pont Vell | meals_entertainment | meals_entertainment | 0.60 | yes |
| invoices/heldout_multi_page.pdf | Meridian Consulting Group, S.L. | professional_services | professional_services | 0.40 | yes |
| invoices/heldout_multiple_vat_rates.pdf | Esdeveniments Girona, S.L. | professional_services | other | 0.20 | NO |
| invoices/heldout_no_invoice_number.pdf | Quiosc La Rambla | meals_entertainment | other | 0.20 | NO |
| invoices/heldout_tax_inclusive.pdf | Taller Ceràmic Girona | office_supplies_furniture | other | 0.30 | NO |
| invoices/heldout_two_column_layout.pdf | Decoracions Bages, S.L. | other | other | 0.20 | yes |
| invoices/heldout_us_date.pdf | Bay Area Dev Tools Inc | software_subscriptions | software_subscriptions | 0.60 | yes |
| invoices/heldout_usd_with_symbol_variants.pdf | Pacific Grove Software LLC | software_subscriptions | software_subscriptions | 0.70 | yes |
| invoices/heldout_written_month_ca.pdf | Vivers Can Bruguera | other | other | 0.20 | yes |
| invoices/heldout_written_month_en.pdf | Thistle & Co Design Studio | professional_services | professional_services | 0.40 | yes |
| invoices/heldout_written_month_es.pdf | Taller de Encuadernación Martí, S.L. | printing_marketing | printing_marketing | 0.50 | yes |
| photos/heldout_scan_like.jpg | Ferreteria El Martell, S.L. | office_supplies_furniture | other | 0.25 | NO |

## (c) Confidence calibration

**Wrong categories reported with confidence above 0.90: 0**

_None._

## Review queue

Total items logged this run: 28

| Item type | File | Reason |
| --- | --- | --- |
| new_supplier | invoices/heldout_credit_note_es.pdf | no match above review threshold for printed name 'Suministros Garrotxa, S.L.' |
| low_confidence_category | invoices/heldout_credit_note_es.pdf | category 'other' confidence 0.20 below threshold |
| new_supplier | invoices/heldout_european_numbers.pdf | no match above review threshold for printed name 'Maquinària Industrial Girona, S.L.' |
| low_confidence_category | invoices/heldout_european_numbers.pdf | category 'other' confidence 0.20 below threshold |
| new_supplier | invoices/heldout_handwritten_note.pdf | no match above review threshold for printed name 'Cafeteria Pont Vell' |
| low_confidence_category | invoices/heldout_handwritten_note.pdf | category 'meals_entertainment' confidence 0.60 below threshold |
| new_supplier | invoices/heldout_multi_page.pdf | no match above review threshold for printed name 'Meridian Consulting Group, S.L.' |
| low_confidence_category | invoices/heldout_multi_page.pdf | category 'professional_services' confidence 0.40 below threshold |
| new_supplier | invoices/heldout_multiple_vat_rates.pdf | no match above review threshold for printed name 'Esdeveniments Girona, S.L.' |
| low_confidence_category | invoices/heldout_multiple_vat_rates.pdf | category 'other' confidence 0.20 below threshold |
| new_supplier | invoices/heldout_no_invoice_number.pdf | no match above review threshold for printed name 'Quiosc La Rambla' |
| low_confidence_category | invoices/heldout_no_invoice_number.pdf | category 'other' confidence 0.20 below threshold |
| new_supplier | invoices/heldout_tax_inclusive.pdf | no match above review threshold for printed name 'Taller Ceràmic Girona' |
| low_confidence_category | invoices/heldout_tax_inclusive.pdf | category 'other' confidence 0.30 below threshold |
| new_supplier | invoices/heldout_two_column_layout.pdf | no match above review threshold for printed name 'Decoracions Bages, S.L.' |
| low_confidence_category | invoices/heldout_two_column_layout.pdf | category 'other' confidence 0.20 below threshold |
| new_supplier | invoices/heldout_us_date.pdf | no match above review threshold for printed name 'Bay Area Dev Tools Inc' |
| low_confidence_category | invoices/heldout_us_date.pdf | category 'software_subscriptions' confidence 0.60 below threshold |
| new_supplier | invoices/heldout_usd_with_symbol_variants.pdf | no match above review threshold for printed name 'Pacific Grove Software LLC' |
| low_confidence_category | invoices/heldout_usd_with_symbol_variants.pdf | category 'software_subscriptions' confidence 0.70 below threshold |
| new_supplier | invoices/heldout_written_month_ca.pdf | no match above review threshold for printed name 'Vivers Can Bruguera' |
| low_confidence_category | invoices/heldout_written_month_ca.pdf | category 'other' confidence 0.20 below threshold |
| new_supplier | invoices/heldout_written_month_en.pdf | no match above review threshold for printed name 'Thistle & Co Design Studio' |
| low_confidence_category | invoices/heldout_written_month_en.pdf | category 'professional_services' confidence 0.40 below threshold |
| new_supplier | invoices/heldout_written_month_es.pdf | no match above review threshold for printed name 'Taller de Encuadernación Martí, S.L.' |
| low_confidence_category | invoices/heldout_written_month_es.pdf | category 'printing_marketing' confidence 0.50 below threshold |
| new_supplier | photos/heldout_scan_like.jpg | no match above review threshold for printed name 'Ferreteria El Martell, S.L.' |
| low_confidence_category | photos/heldout_scan_like.jpg | category 'other' confidence 0.25 below threshold |
