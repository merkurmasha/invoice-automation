# Running this project's n8n workflows locally

This is a step-by-step guide for running [n8n](https://n8n.io) — the
workflow-automation tool that watches your Google Drive folder, calls
this repo's Python scripts, and writes results into Google Sheets and
Gmail drafts — entirely on your own Mac. Nothing here runs in the
cloud and nothing is ever sent without you clicking "Send" yourself in
Gmail.

If you're new to n8n: it's a visual tool where you build a "workflow"
by connecting boxes ("nodes") with arrows. Each node does one thing
(watch a folder, run a command, add a row to a spreadsheet...) and
passes its output to the next node. The three workflows in
`n8n/workflows/` are JSON files you can import instead of building
from scratch — but you'll still need to open each one and connect your
own Google/Gmail account, because credentials are never stored in
those files (see "Why credentials aren't in the JSON files" below).

## 1. Install n8n

This project checked your machine and found: Node.js v22 and npm are
already installed, but n8n itself is not. n8n is a Node.js program, so
install it with npm, **not** Docker — you're running Python scripts
from this project's `.venv` folder via n8n's "Execute Command" node,
and that's far simpler if n8n is just another program on your Mac
(same filesystem, same `.venv` path, no containers to share folders
into). Docker would also work, but you'd have to mount this whole repo
into the container and get the path right in every workflow — not
worth it for a single local instance.

Install n8n globally with:

```bash
npm install -g n8n
```

This is the one command this project asks you to run yourself (nothing
here installs anything without telling you first). Confirm it worked:

```bash
n8n --version
```

## 2. Start n8n

From the repo root:

```bash
n8n/start.sh
```

This script (see its own comments for the full explanation) does three
things before starting n8n:

- Points n8n's data folder at `n8n/data/` inside this repo (not the
  default `~/.n8n`), so everything n8n stores — its database,
  encryption key, and your Google/Gmail credentials — stays inside
  this project and is **gitignored** (`.gitignore` already excludes
  `n8n/data/`). Never commit that folder.
- Binds n8n to `127.0.0.1` only, so nothing outside your own machine
  can reach it.
- Re-enables the "Execute Command" node. Recent n8n versions disable
  this node by default (it can run arbitrary shell commands — a real
  risk if n8n were exposed to the internet or to untrusted workflows).
  Since this n8n only listens on localhost and only ever runs the
  three fixed commands baked into the workflow JSON files you import
  yourself, re-enabling it here is safe.

Once it's running, open **http://localhost:5678** in your browser and
create your n8n account (this is a *local* account — n8n asks for an
email/password the first time, but nothing leaves your machine with
them).

Leave this terminal running while you work with n8n. Press `Ctrl+C` to
stop it.

## 3. Google Cloud project + OAuth client

n8n needs its own Google OAuth credentials to act as you on Drive,
Sheets, and Gmail. This takes about ten minutes, once:

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
   and create a new project (e.g. "invoice-automation-local").
2. **Enable APIs.** In the left sidebar, go to "APIs & Services" →
   "Library", and enable each of these (search by name, click it,
   click "Enable"):
   - Google Drive API
   - Google Sheets API
   - Gmail API
3. **Configure the OAuth consent screen.** Go to "APIs & Services" →
   "OAuth consent screen". Choose **External** (unless you have a
   Google Workspace account — then Internal is simpler), fill in an
   app name and your email, and save. On the "Scopes" step you can
   leave the defaults; n8n will request the specific scopes it needs
   when you connect each credential.
4. **Add yourself as a test user.** Still on the consent screen
   settings, under "Test users", add the Google account you want this
   project to use (create a fresh test Google account if you don't
   want to use your real one — this project only ever uses synthetic
   data, but it's still good practice not to point a demo at your main
   account). While the app is in "Testing" mode, only test users you
   list here can authorize it.
5. **Create an OAuth client.** Go to "APIs & Services" → "Credentials"
   → "Create Credentials" → "OAuth client ID". Choose **Web
   application**. Under "Authorized redirect URIs", add exactly:

   ```
   http://localhost:5678/rest/oauth2-credential/callback
   ```

   (This is n8n's fixed local OAuth callback path — `5678` is n8n's
   default port from step 2. If you changed `N8N_PORT` in
   `n8n/start.sh`, use that port instead.)
6. Save, and copy the **Client ID** and **Client Secret** it gives
   you — you'll paste them into n8n in the next step. Don't paste them
   anywhere in this repo.

## 4. Add credentials in n8n

In the n8n editor (http://localhost:5678), go to **Credentials** (left
sidebar) → **Add credential**, and create three:

1. **Google Drive OAuth2 API** — paste in the Client ID/Secret from
   step 3, then click "Connect my account" and sign in as your test
   user.
2. **Google Sheets OAuth2 API** — same Client ID/Secret, connect the
   same account.
3. **Gmail OAuth2 API** — same Client ID/Secret, connect the same
   account.

Name them exactly **"Google Drive account"**, **"Google Sheets
account"**, and **"Gmail account"** — those are the placeholder names
already written into the workflow JSON files, so after importing a
workflow you'll just need to pick each credential from a dropdown
rather than typing a new name everywhere.

### Why credentials aren't in the JSON files

Every node that needs Google access in `n8n/workflows/*.json` has a
`credentials` block that looks like:

```json
"credentials": { "googleDriveOAuth2Api": { "id": "", "name": "Google Drive account" } }
```

The `id` is deliberately blank. n8n always stores the real OAuth
tokens encrypted in its own database (`n8n/data/`, gitignored) — never
inside a workflow export — so this repo can safely commit these JSON
files with zero secrets in them.
`tests/test_n8n_workflows.py::test_credentials_are_placeholders_only`
enforces this: it fails the build if anyone ever commits a non-blank
credential id.

## 5. Create the Drive folders and the Sheet

**Drive folders** (anywhere in your Google Drive — pick one spot and
remember it):

- `Invoices-Inbox` — drop new invoices/receipts here; the intake
  workflow watches this folder.
- `Invoices-Processed` — invoices that passed validation land here,
  renamed.
- `Invoices-Review` — invoices that need a human look land here,
  under their original name.
- `Accountant-Packs` — month-end packs get uploaded here.

**Google Sheet** — create one new Sheet named "Invoice Automation"
(or anything — you'll pick it by name in n8n either way), with three
tabs and these exact header rows in row 1:

| Tab name | Column headers (row 1) |
| --- | --- |
| `Ledger` | `Date`, `Supplier`, `Invoice Number`, `Category`, `Standardised Filename`, `Drive Subfolder`, `Original File`, `Status` |
| `Review queue` | `Date`, `Original File`, `Status`, `Reasons`, `Error` |
| `Reminders` | `Date`, `Invoice`, `Stage`, `Customer`, `Subject`, `Needs Review`, `Status` |

## 6. Import each workflow

For each file in `n8n/workflows/` (`intake.json`, `receivables.json`,
`month_end_pack.json`):

1. In the n8n editor, click **Workflows** → **Add workflow** → the
   **⋯** menu (or "Import from File") → **Import from File**, and pick
   the JSON file.
2. Open every Google Drive / Google Sheets / Gmail node (double-click
   it) and:
   - Pick the matching credential from step 4 in the "Credential"
     dropdown.
   - For any field showing a folder/file/sheet picker with a name like
     "Invoices-Inbox" or "Ledger" already filled in, click the field
     and re-pick the real folder/sheet/tab from the list — the JSON
     only carries the *name* as a label, not Google's internal ID, so
     this step re-links it to your actual Drive/Sheet.
3. n8n node parameters occasionally change their exact field names
   between versions. If a node shows a small warning icon after
   import, open it — n8n usually shows you exactly which field needs
   re-entering, and the node's own built-in description (hover the
   field's "?" icon) explains what it expects. Cross-check against the
   plain-English description of that workflow in this repo's
   `CLAUDE.md`-adjacent script docstrings
   (`scripts/process_invoice.py`, `scripts/receivables_today.py`,
   `scripts/build_pack.py`) if you're unsure what a step is *supposed*
   to do.
4. Save the workflow (the Save button, or `Cmd+S`).

`receivables.json` imports **inactive**, with its Schedule Trigger
node disabled, on purpose — see the safety note in step 8.

## 7. Test each flow with a synthetic file

This repo already has synthetic test invoices you can use — don't use
any real document (see `CLAUDE.md`: synthetic data only, always):

```bash
ls data/synthetic/invoices | head -3
```

**Test intake.json:**
1. Open `intake.json` in n8n and click the **Watch Invoices-Inbox**
   node, then "Fetch test event" (or just upload a file to your real
   `Invoices-Inbox` Drive folder and wait — the trigger polls every
   minute).
2. Upload one synthetic PDF from `data/synthetic/invoices/` into your
   Drive's `Invoices-Inbox` folder.
3. Within a minute, check the **Executions** tab in n8n for a run.
   Click it to see each node's output. Confirm: the file moved out of
   `Invoices-Inbox` into either `Invoices-Processed` (renamed) or
   `Invoices-Review` (original name), and a new row appeared in the
   matching Sheet tab.

**Test receivables.json:**
1. Open the workflow, click the **Run receivables_today.py** node, and
   use "Execute step" to run just that node (safe — it only prints
   JSON, draft creation happens in the next node).
2. If its output shows `"due_count": 0`, there's nothing due today
   against `data/synthetic/sales_invoices.csv` — that's fine, it
   proves the script runs; to see a real draft, temporarily edit that
   node's command to add ` --today 2026-11-01` (a date well past the
   synthetic invoices' due dates) and re-run, then revert the edit
   before relying on this workflow for real.
3. Run the rest of the workflow manually (the ▶ button on each node in
   turn) and confirm one Gmail draft appears in your connected
   account's Drafts folder, and one row appears in the "Reminders"
   Sheet tab. **Do not click Send** — this is exactly the point of the
   exercise: confirming a draft was created, not sent.

**Test month_end_pack.json:**
1. Click **Execute workflow** (the Manual Trigger's button).
2. Confirm `data/packs/<month>/` was created locally (check with `ls
   data/packs/`) and that the same files appear in your
   `Accountant-Packs` Drive folder afterwards.

## 8. Safety notes — read before turning anything "live"

- **`receivables.json` imports inactive, with its trigger disabled.**
  This project drafts reminders automatically but never sends them —
  but running it on a schedule means it'll draft *every day* once
  enabled. Only flip the workflow to Active and the Schedule Trigger's
  disabled switch to off once you're comfortable reviewing its output
  — and even then, every draft still needs you to open Gmail and send
  it by hand. The Gmail node is hardcoded to `resource: "draft"`,
  `operation: "create"` — never "send" — and
  `tests/test_n8n_workflows.py` fails the test suite if anyone ever
  changes that.
- **The reminder drafts have no recipient filled in.** This project's
  synthetic `sales_invoices.csv` only has a customer *name*, never a
  real email address, so the Gmail node intentionally leaves "To"
  blank — you fill it in by hand before sending, which doubles as a
  final human check.
- **`intake.json` files invoices into a single `Invoices-Processed`
  folder, not nested `year/month/supplier` subfolders.** The wrapper
  script (`scripts/process_invoice.py`) *computes* the suggested
  `year/month/supplier` path and writes it to the Ledger sheet's
  "Drive Subfolder" column — but Google Drive's API won't auto-create
  folders that don't exist yet, and reliably creating three levels of
  nested folders on demand needs several more nodes than fit cleanly
  in a hand-written import file. If you want that extra filing step,
  add three "Google Drive: Search/Create Folder" node pairs (one per
  path segment) between "Rename + move to processed" and "Append to
  Ledger", each checking whether that segment's folder already exists
  before creating it.
- **Never commit `n8n/data/`.** It holds the encryption key n8n uses
  to decrypt your stored OAuth tokens. `.gitignore` already excludes
  it — don't override that.

## Troubleshooting

**"Execute Command node is disabled" / node won't run.** You started
n8n without `n8n/start.sh` (e.g. ran `n8n start` directly), so
`NODES_EXCLUDE` wasn't set. Stop n8n and start it with
`n8n/start.sh` instead.

**Execute Command fails with "command not found" or a Python
`ModuleNotFoundError`.** Check `$INVOICE_AUTOMATION_REPO` resolved
correctly — it's set by `n8n/start.sh`, so if you started n8n any other
way, this variable won't exist and the node's `cd` will fail. Also
confirm you ran `.venv/bin/python -m pip install -e .` from the repo
root at least once (step 6 of the main setup, not this file) — the
wrapper scripts live in the `scripts` package, which needs that
install step to be importable.

**Execute Command fails with something like "access to env vars denied"
or the node can't see `$INVOICE_AUTOMATION_REPO` at all.** n8n blocks
nodes from reading process env vars via `$env` by default; `n8n/start.sh`
sets `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` to allow it, so make sure
you started n8n with that script rather than `n8n start` directly.

**A Google node fails with `403` or "access blocked: this app's
request is invalid".** Almost always one of: the redirect URI in your
OAuth client doesn't exactly match
`http://localhost:5678/rest/oauth2-credential/callback` (check for a
trailing slash or wrong port), the relevant API isn't enabled yet
(step 3.2), or your Google account isn't listed as a test user while
the app is in "Testing" mode (step 3.4).

**A node shows "unrecognized node type/version" right after
import.** Your n8n version is newer or older than the one this file
was written against. Open the node — n8n usually offers to update it
in place; confirm the resulting fields match this guide's description
of what that node should do, then save.

**Sheets append writes to the wrong tab, or fails with "Unable to find
sheet".** Re-pick the sheet/tab in the node's dropdown (see step 6.2)
rather than trusting the name n8n shows after import — the JSON only
carries a label, not the real spreadsheet/tab ID, until you re-select
it once.

**The intake workflow runs twice for one file, or Drive trigger fires
on files you didn't just add.** The Google Drive Trigger node polls on
a timer and can occasionally re-report a file if Drive's own "modified
time" changes (e.g. you touched its sharing settings). This is a Drive
API quirk, not a bug in this project's scripts —
`scripts/process_invoice.py`'s duplicate detector (keyed on supplier +
invoice number + total, in `data/cache/seen_invoices.json`) will
correctly flag the second run as a `DUPLICATE` and route it to the
review queue rather than double-booking it.
