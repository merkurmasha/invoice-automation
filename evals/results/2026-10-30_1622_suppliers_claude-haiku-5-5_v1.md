# Supplier matching + categorisation eval — claude-haiku-5-5 — 2026-10-30_1622

## Run metadata

- Model: `claude-haiku-5-5`
- Categorisation prompt version: `v1`
- Dataset: `synthetic`
- Tokens used this run — input: 10942, output: 1073

## (a) Supplier merge accuracy

- Missed merges (same real supplier, different supplier_id assigned): 0
- False merges (different real suppliers given the same supplier_id): 0

| Match status | Count |
| --- | --- |
| exact | 26 |
| fuzzy_merge | 1 |
| new | 17 |
| possible_match | 2 |

## (b) Categorisation accuracy

**Overall: 40/46 correct (87.0%)**

- Routed to review queue for low confidence: 25

| File | Supplier | Expected | Actual | Confidence | Correct |
| --- | --- | --- | --- | --- | --- |
| invoices/accounting_2026-10-10.pdf | Assessoria Fiscal Puig & Associats | accounting_legal | accounting_legal | 0.85 | yes |
| invoices/adobe_2026-07-05.pdf | Adobe Inc. | software_subscriptions | software_subscriptions | 0.90 | yes |
| invoices/adobe_2026-08-05.pdf | Adobe Inc. | software_subscriptions | software_subscriptions | 0.90 | yes |
| invoices/adobe_2026-09-05.pdf | ADOBE SYSTEMS SOFTWARE IRELAND LTD | software_subscriptions | software_subscriptions | 0.95 | yes |
| invoices/adobe_2026-10-05.pdf | Adobe Inc. | software_subscriptions | software_subscriptions | 0.90 | yes |
| invoices/adobe_2026-10-15.pdf | Adobe Inc. | software_subscriptions | software_subscriptions | 0.90 | yes |
| invoices/catering_2026-09-18.pdf | Café Central | meals_entertainment | meals_entertainment | 0.60 | yes |
| invoices/cloudhost_2026-07-08.pdf | CloudHost Barcelona, S.L. | software_subscriptions | software_subscriptions | 0.70 | yes |
| invoices/courier_2026-08-14.pdf | Missatgeria Girona, S.L. | shipping_courier | other | 0.20 | NO |
| invoices/coworking_2026-07-01.pdf | Barcelona Working Hub, S.L. | rent_coworking | rent_coworking | 0.85 | yes |
| invoices/coworking_2026-08-01.pdf | Barcelona Working Hub, S.L. | rent_coworking | rent_coworking | 0.85 | yes |
| invoices/coworking_2026-09-01.pdf | Barcelona Working Hub, S.L. | rent_coworking | rent_coworking | 0.85 | yes |
| invoices/coworking_2026-09-01_near.pdf | Barcelona Working Hub, S.L. | rent_coworking | rent_coworking | 0.85 | yes |
| invoices/coworking_2026-10-01.pdf | Barcelona Working Hub, S.L. | rent_coworking | rent_coworking | 0.85 | yes |
| invoices/electricity_2026-07-10.pdf | Energia Costa Brava, S.L. | utilities | utilities | 0.60 | yes |
| invoices/electricity_2026-08-10.pdf | Energia Costa Brava, S.L. | utilities | utilities | 0.60 | yes |
| invoices/electricity_2026-08-10_dup.pdf | Energia Costa Brava, S.L. | utilities | utilities | 0.60 | yes |
| invoices/electricity_2026-09-10.pdf | Energia Costa Brava, S.L. | utilities | utilities | 0.60 | yes |
| invoices/electricity_2026-10-10.pdf | Energia Costa Brava, S.L. | utilities | utilities | 0.60 | yes |
| invoices/figma_2026-07-12.pdf | Figma, Inc. | software_subscriptions | software_subscriptions | 0.95 | yes |
| invoices/figma_2026-09-12.pdf | Figma, Inc. | software_subscriptions | software_subscriptions | 0.95 | yes |
| invoices/freelancer_2026-07-20.pdf | Jordi Soler Fotografia | professional_services | professional_services | 0.70 | yes |
| invoices/freelancer_2026-09-22.pdf | Jordi Soler Fotografia | professional_services | professional_services | 0.70 | yes |
| invoices/furniture_2026-08-25.pdf | Mobles Office BCN, S.L. | office_supplies_furniture | office_supplies_furniture | 0.60 | yes |
| invoices/insurance_2026-07-30.pdf | Assegurances Costa Brava, S.L. | insurance | insurance | 0.80 | yes |
| invoices/internet_2026-07-15.pdf | Fibra Catalana, S.L. | utilities | other | 0.20 | NO |
| invoices/internet_2026-08-15.pdf | Fibra Catalana, S.L. | utilities | other | 0.20 | NO |
| invoices/internet_2026-09-15.pdf | Fibra Catalana, S.L. | utilities | other | 0.20 | NO |
| invoices/internet_2026-10-15.pdf | Fibra Catalana, S.L. | utilities | other | 0.20 | NO |
| invoices/nordic_2026-08-01.pdf | Nordic Design Tools GmbH | software_subscriptions | software_subscriptions | 0.60 | yes |
| invoices/notion_2026-07-03.pdf | Notion Labs Inc | software_subscriptions | software_subscriptions | 0.95 | yes |
| invoices/notion_2026-08-03.pdf | NOTION LABS | software_subscriptions | software_subscriptions | 0.90 | yes |
| invoices/notion_2026-09-03.pdf | Notion Labs, Inc | software_subscriptions | software_subscriptions | 0.95 | yes |
| invoices/notion_2026-10-03.pdf | Notion Labs, Inc. | software_subscriptions | software_subscriptions | 0.95 | yes |
| invoices/officesupplies_2026-10-02.pdf | Toner & Papereria Girona | office_supplies_furniture | office_supplies_furniture | 0.80 | yes |
| invoices/pixelco_2026-09-25.pdf | Pixel & Co Design Ltd | professional_services | professional_services | 0.50 | yes |
| invoices/printer_2026-08-18.pdf | Impremta Girona, S.L. | printing_marketing | printing_marketing | 0.70 | yes |
| invoices/printer_2026-10-06.pdf | Impremta Girona, S.L. | printing_marketing | printing_marketing | 0.70 | yes |
| invoices/studiofonts_2026-09-09.pdf | Studio Fonts France SARL | software_subscriptions | software_subscriptions | 0.45 | yes |
| invoices/travel_2026-10-20.pdf | Viatges Business, S.L. | travel | travel | 0.50 | yes |
| photos/coworking_2026-07-01.jpg | Barcelona Working Hub, S.L. | rent_coworking | rent_coworking | 0.85 | yes |
| photos/freelancer_2026-07-20.jpg | Jordi Soler Fotografia | professional_services | professional_services | 0.70 | yes |
| photos/internet_2026-10-15.jpg | Fibra Catalana, S.L. | utilities | other | 0.20 | NO |
| photos/notion_2026-08-03.jpg | NOTION LABS | software_subscriptions | software_subscriptions | 0.90 | yes |
| photos/pixelco_2026-09-25.jpg | Pixel & Co Design Ltd | professional_services | professional_services | 0.50 | yes |
| photos/studiofonts_2026-09-09.jpg | Studio Fonts France SARL | software_subscriptions | software_subscriptions | 0.45 | yes |

## (c) Confidence calibration

**Wrong categories reported with confidence above 0.90: 0**

_None._

## Review queue

Total items logged this run: 44

| Item type | File | Reason |
| --- | --- | --- |
| new_supplier | invoices/accounting_2026-10-10.pdf | no match above review threshold for printed name 'Assessoria Fiscal Puig & Associats' |
| new_supplier | invoices/adobe_2026-07-05.pdf | no match above review threshold for printed name 'Adobe Inc.' |
| new_supplier | invoices/catering_2026-09-18.pdf | no match above review threshold for printed name 'Café Central' |
| low_confidence_category | invoices/catering_2026-09-18.pdf | category 'meals_entertainment' confidence 0.60 below threshold |
| new_supplier | invoices/cloudhost_2026-07-08.pdf | no match above review threshold for printed name 'CloudHost Barcelona, S.L.' |
| low_confidence_category | invoices/cloudhost_2026-07-08.pdf | category 'software_subscriptions' confidence 0.70 below threshold |
| new_supplier | invoices/courier_2026-08-14.pdf | no match above review threshold for printed name 'Missatgeria Girona, S.L.' |
| low_confidence_category | invoices/courier_2026-08-14.pdf | category 'other' confidence 0.20 below threshold |
| new_supplier | invoices/coworking_2026-07-01.pdf | no match above review threshold for printed name 'Barcelona Working Hub, S.L.' |
| new_supplier | invoices/electricity_2026-07-10.pdf | no match above review threshold for printed name 'Energia Costa Brava, S.L.' |
| low_confidence_category | invoices/electricity_2026-07-10.pdf | category 'utilities' confidence 0.60 below threshold |
| low_confidence_category | invoices/electricity_2026-08-10.pdf | category 'utilities' confidence 0.60 below threshold |
| low_confidence_category | invoices/electricity_2026-08-10_dup.pdf | category 'utilities' confidence 0.60 below threshold |
| low_confidence_category | invoices/electricity_2026-09-10.pdf | category 'utilities' confidence 0.60 below threshold |
| low_confidence_category | invoices/electricity_2026-10-10.pdf | category 'utilities' confidence 0.60 below threshold |
| new_supplier | invoices/figma_2026-07-12.pdf | no match above review threshold for printed name 'Figma, Inc.' |
| new_supplier | invoices/freelancer_2026-07-20.pdf | no match above review threshold for printed name 'Jordi Soler Fotografia' |
| low_confidence_category | invoices/freelancer_2026-07-20.pdf | category 'professional_services' confidence 0.70 below threshold |
| low_confidence_category | invoices/freelancer_2026-09-22.pdf | category 'professional_services' confidence 0.70 below threshold |
| new_supplier | invoices/furniture_2026-08-25.pdf | no match above review threshold for printed name 'Mobles Office BCN, S.L.' |
| low_confidence_category | invoices/furniture_2026-08-25.pdf | category 'office_supplies_furniture' confidence 0.60 below threshold |
| new_supplier | invoices/insurance_2026-07-30.pdf | no match above review threshold for printed name 'Assegurances Costa Brava, S.L.' |
| new_supplier | invoices/internet_2026-07-15.pdf | no match above review threshold for printed name 'Fibra Catalana, S.L.' |
| low_confidence_category | invoices/internet_2026-07-15.pdf | category 'other' confidence 0.20 below threshold |
| low_confidence_category | invoices/internet_2026-08-15.pdf | category 'other' confidence 0.20 below threshold |
| low_confidence_category | invoices/internet_2026-09-15.pdf | category 'other' confidence 0.20 below threshold |
| low_confidence_category | invoices/internet_2026-10-15.pdf | category 'other' confidence 0.20 below threshold |
| new_supplier | invoices/nordic_2026-08-01.pdf | no match above review threshold for printed name 'Nordic Design Tools GmbH' |
| low_confidence_category | invoices/nordic_2026-08-01.pdf | category 'software_subscriptions' confidence 0.60 below threshold |
| new_supplier | invoices/notion_2026-07-03.pdf | no match above review threshold for printed name 'Notion Labs Inc' |
| new_supplier | invoices/officesupplies_2026-10-02.pdf | no match above review threshold for printed name 'Toner & Papereria Girona' |
| possible_match | invoices/pixelco_2026-09-25.pdf | 'Pixel & Co Design Ltd' ~ 'Assessoria Fiscal Puig & Associats' (score 85.5) |
| low_confidence_category | invoices/pixelco_2026-09-25.pdf | category 'professional_services' confidence 0.50 below threshold |
| possible_match | invoices/printer_2026-08-18.pdf | 'Impremta Girona, S.L.' ~ 'Toner & Papereria Girona' (score 85.5) |
| low_confidence_category | invoices/printer_2026-08-18.pdf | category 'printing_marketing' confidence 0.70 below threshold |
| low_confidence_category | invoices/printer_2026-10-06.pdf | category 'printing_marketing' confidence 0.70 below threshold |
| new_supplier | invoices/studiofonts_2026-09-09.pdf | no match above review threshold for printed name 'Studio Fonts France SARL' |
| low_confidence_category | invoices/studiofonts_2026-09-09.pdf | category 'software_subscriptions' confidence 0.45 below threshold |
| new_supplier | invoices/travel_2026-10-20.pdf | no match above review threshold for printed name 'Viatges Business, S.L.' |
| low_confidence_category | invoices/travel_2026-10-20.pdf | category 'travel' confidence 0.50 below threshold |
| low_confidence_category | photos/freelancer_2026-07-20.jpg | category 'professional_services' confidence 0.70 below threshold |
| low_confidence_category | photos/internet_2026-10-15.jpg | category 'other' confidence 0.20 below threshold |
| low_confidence_category | photos/pixelco_2026-09-25.jpg | category 'professional_services' confidence 0.50 below threshold |
| low_confidence_category | photos/studiofonts_2026-09-09.jpg | category 'software_subscriptions' confidence 0.45 below threshold |
