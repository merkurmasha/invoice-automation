# Case study: invoice automation for a small studio

## The problem

Costa Brava Studio S.L. is a fictional design studio with the finance problems of a real one. Invoices arrive as PDFs and photos. Someone types them into a spreadsheet. Late payers get chased when someone remembers. At month end the accountant receives a pile of files and sends back questions.

I built a pipeline for that workflow. It reads each invoice, checks it, files it, tracks who owes money, matches the bank statement and prepares the month-end pack. A person approves everything that leaves the system.

All data is synthetic. No real company, customer or bank account is involved.

**Status: a working version one with known gaps.** Each stage works and is tested. The stages are not yet joined into one closed loop for a real month. This page says what works, what is missing and what I am building next.

## The design rule

One rule shaped every decision: the language model reads, code decides.

The model has three jobs. It extracts fields from an invoice, suggests a category and writes the wording of a reminder. Everything with a right answer is plain code with tests: arithmetic checks, duplicate detection, supplier matching, receivables aging and bank reconciliation. A model that reads documents correctly 98% of the time is good at reading. It is the wrong tool for deciding whether EUR 3,852.95 is 88 days overdue.

The third part is the human. Nothing is sent automatically. Reminders are Gmail drafts that I read and send myself. An invoice that fails a check goes to a review queue with the reason written next to it.

## How it works

- **Intake.** A file dropped into a Drive folder is picked up, read by the model and validated by code. Invoices that pass go to a Processed folder and a Ledger row. Invoices that fail go to a Review folder and a Review queue row, with the reason (due date is missing).
- **Suppliers and categories.** Fuzzy matching joins "Adobe Inc." and "Adobe Systems Software Ireland Ltd" into one supplier. The model suggests a category and flags how sure it is.
- **Receivables.** This covers invoices the studio issues to its customers, read from a fixed list. Each day, code works out how overdue each one is and which reminder stage it has reached. The model writes the wording. A Gmail draft appears for me to review. A reminder log stops the same reminder from being drafted twice.
- **Reconciliation.** Each bank line is matched to invoices by amount, name and date. Every match carries a score and a plain-language reason. Uncertain ones are marked "possible match" for a human.
- **Month-end pack.** One command builds the 13 files the accountant needs. In this version it builds them from the project's synthetic data, not from the live Ledger (see "What is missing in the workflow").
- **Dashboard.** One page shows spend by category, receivables aging, the review queue, reconciliation status and the accuracy numbers below. It is live at https://merkurmasha.github.io/invoice-automation/dashboard/.

The same steps run as three n8n workflows: intake, daily receivables and month-end pack. n8n only moves files and calls the scripts. The logic lives in the Python code, so it is tested without n8n.

## What I built

I built it in phases, each merged through a pull request with CI passing: synthetic data first, then extraction, validation, an evaluation harness, suppliers and categories, receivables, reconciliation together with the month-end pack, the n8n workflows and the dashboard. The repo has 266 tests.

Building the synthetic data first meant I always knew the right answer. That made every later number measurable.

## Results

| What | Result | How it was measured |
|---|---|---|
| Extraction, synthetic set | 97.4% with the first prompt, 100% with the second | Field-level accuracy against the known answers. I used this set to fix the prompt, so 100% proves less than it looks. |
| Extraction, held-out | 98.6% (138 of 140 fields) | Documents I never used while building the prompt. This is the number I trust. |
| Supplier merging | 0 false merges, 0 missed merges | Against the known list of supplier name variants. |
| Categorisation, synthetic | 87% | Category assigned correctly, against the known answers. |
| Categorisation, held-out | 64.3% (9 of 14) | A small sample. The wrong answers were all low-confidence, so they land in front of a human. |
| Reconciliation | 36 of 36 correct, 0 false matches | I tuned the matcher on this same data, so treat it as a ceiling, not a forecast. |

On the demo bank statement, 32 of 37 lines (86.5%) match automatically. The other 5 go to a human with a reason.

## What broke and how I fixed it

The unit tests passed from day one. Most real problems appeared only when I ran the workflows live in n8n with real Google accounts.

**The first extraction prompt missed fields.** It scored 97.4%. Most misses were dates read with the day and month swapped: one invoice's issue date was `2026-09-05`, the model read `2026-05-09`. One invoice legitimately has zero VAT, and the model left the field empty instead of recording 0. I read the misses, changed the prompt and reached 100%. Then I tested on documents I had not used to tune it and got 98.6%. The gap between the two numbers is the lesson: a score on the data you tuned on flatters you.

**A script exit code stopped the workflow.** Invoices that needed review made the script exit with a non-zero code, which n8n treats as a failure. The review route never ran. I added an `--n8n` flag that returns the same result with exit code 0, so a review case is a normal outcome and not an error.

**Google Sheets wrote the wrong columns.** The Sheets node auto-mapped Drive fields into the Ledger and added four columns I never asked for. I switched to manual mapping, set each column from the parsed result and added a test that checks the mapped columns against the documented headers.

**n8n blocked file access.** The workflow could not write the downloaded invoice to disk, and later could not read the month-end pack. n8n restricts which folders a node can touch. I gave it one temporary folder for intake and one for packs, and documented both.

**My own test files were flagged as duplicates.** Duplicate detection remembers every invoice it has processed, including test runs. A clean re-run therefore rejected files as already seen. I added a `--dry-run` flag that checks without writing to memory, and a reset section in the docs.

**Drive could not rename on move.** I wanted processed files renamed to a standard name. The Drive move node does not support it. I dropped the rename. The standardised name lives in the Ledger, and the file keeps its original name.

**A batch test found that half the files were skipped.** I dropped six invoices into the inbox. Only three left it. n8n passed two files per run, but the script step was set to Execute Once, which processes the first item only. One-file tests never showed it. I turned that setting off, made the next node handle one item at a time and added tests that fail if either setting comes back. A second batch test cleared all files.

## What works today

- Drop a supplier invoice into the Drive inbox. Within about a minute it is read, validated and filed. A clean invoice gets a Ledger row. A problem invoice gets a Review queue row with the reason.
- Drop the same invoice twice. The duplicate check catches it and sends the second copy to review.
- Run the receivables workflow. It drafts reminders for overdue customer invoices in Gmail. Nothing is sent.
- Run the month-end workflow. A 13-file accountant pack lands in a Drive folder.
- Open the live dashboard.
- Run the offline evaluations to reproduce every accuracy number on this page.

## What is missing in the workflow

I tested the whole system by tracing where each stage reads and writes. These are the gaps.

1. **The live path and the demo path do not connect.** The inbox flow writes to the Ledger and Review queue tabs in Google Sheets. Nothing reads those tabs back. The receivables flow, the bank reconciliation, the month-end pack and the dashboard all read static synthetic files in the repo. An invoice dropped in the inbox today does not reach the pack, the reminders or the dashboard.
2. **The Review queue has no approve step.** To resolve an item, I fix it, add the row to the Ledger and move the file by hand.
3. **Receivables run on a fixed list.** The issued-invoice list is a static file with no way to add a new invoice. Nothing tracks payment: the Status column on the Reminders tab says "Drafted" and never changes to Sent or Paid.
4. **No reminders for bills the studio pays.** An invoice sitting in Processed never triggers a due-date reminder.
5. **The bank statement is a fixed file.** There is no folder to drop a new month's statement into.
6. **The pack uses answer-key categories and names.** It does not use the live categoriser output.
7. **A duplicate costs a full model call.** The duplicate check runs after extraction, so the model is paid twice before the duplicate is caught.
8. **State lives on one laptop.** The supplier master and duplicate memory are local files, and the Sheet can drift from them. Two separate review queue implementations also exist and never reconcile with each other.

## Limits

- **Synthetic data only.** I have not run this on real invoices, so I do not know how it handles messy scans.
- **It runs only while my laptop is awake.** n8n runs locally. A real deployment needs a server.
- **The categoriser sees the supplier name only.** It does not read the line items, which is why held-out accuracy is 64.3%.
- **The matcher was tuned on scored data.** The 36 of 36 will drop on new data.
- **The held-out categorisation sample is 14 documents.** Treat it as a signal, not a measurement.

## How I built it

I directed the work and Claude Code wrote the code from my specifications. I set up the Google Drive folders, Sheets, Gmail and OAuth credentials myself, ran every workflow live and found the n8n problems above by testing them. I made the product decisions: nothing is sent automatically, the model never does arithmetic and a rename was not worth the complexity. I reviewed each pull request before merging.

## What I am building next

The next version closes the loop, in this order:

1. **One shared store.** Processed invoices write to a single data source that the Ledger, the pack, the reminders and the dashboard all read.
2. **An approve step.** The Review queue gets an Approved column. A workflow moves approved rows into the Ledger and the file into Processed.
3. **Real inputs for a month.** A folder for the bank statement and a sheet tab for issued invoices, so the pack builds from live data.
4. **Payment tracking.** Reconciliation marks an issued invoice as paid, reminders for it stop and the Status column shows it.
5. **Due-date reminders for bills the studio pays.**
6. **A mock month.** Thirty days of invoices go in and the pack comes out at the end, checked against the answer key. I will run the 31 synthetic invoices that never went through live n8n as part of it.

After that: give the categoriser the line items, test on a small set of real anonymised invoices, move n8n to a hosted server and rebuild the three workflows by hand so I can explain every node.

Step 1 starts this week. I will post the updated version when the mock month passes.
