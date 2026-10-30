"""Settings for the receivables module.

Styled the same way as src/extract/config.py and src/suppliers/config.py
(model name + prompt version + cache dir all in one place), kept as its
own file so this phase never edits those modules' files.
"""

from pathlib import Path

# Same cheap model as extraction/categorisation — drafting a short
# reminder email is not a job that needs a bigger model.
DRAFT_MODEL = "claude-haiku-5-5"

# Bumped whenever the system prompt in draft.py changes meaningfully.
# Part of the cache key, so a prompt change naturally misses the cache.
# v2: dropped the stage-3 "escalated internally" phrasing, added the
# previous_reminders_sent gate, and added the forbidden-terms rule.
DRAFT_PROMPT_VERSION = "v2"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Shared with extraction/categorisation's cache dir — safe because cache
# keys are content hashes that already include which module produced
# them (draft.py salts its key differently), so they can never collide.
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

# Where reminder drafts are written. Gitignored — these are working
# files for a human to review, not project source.
DRAFTS_DIR = PROJECT_ROOT / "data" / "drafts"

# The append-only record of which (invoice, stage) reminders have
# already been drafted, so the scheduler never repeats one. Gitignored.
REMINDER_LOG_PATH = PROJECT_ROOT / "data" / "reminder_log.csv"

# Default source of sales invoices for the tracker.
SALES_INVOICES_PATH = PROJECT_ROOT / "data" / "synthetic" / "sales_invoices.csv"

# Reminder stage -> days after the due date that stage becomes due.
# Stage 1 fires on the due date itself (offset 0).
STAGE_OFFSETS_DAYS = {1: 0, 2: 7, 3: 14}
