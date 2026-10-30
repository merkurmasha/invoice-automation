"""Settings for the accountant-pack module."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Gitignored - these are generated working files, not project source.
PACKS_DIR = PROJECT_ROOT / "data" / "packs"

SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"

# Where the source documents the answer key's "file" field points to
# actually live, so documents/ can copy the real file.
DOCUMENTS_ROOT = SYNTHETIC_DIR

# Every field's confidence when re-running src/validate/validate.py
# against the answer key: the answer key is ground truth (already
# known), not a live extraction result, so there's nothing for
# check_low_confidence to meaningfully score - this keeps every field
# comfortably above src/validate/config.py's CONFIDENCE_THRESHOLD so
# that check never fires here, while still exercising every other
# check (maths, required fields, dates, document type, duplicates)
# for real.
SYNTHETIC_CONFIDENCE = 0.95

# Anchor "today" for the pack's aging/overdue sections, matching the
# date already used elsewhere in this project's receivables/reconcile
# demos - kept as a default so the pack is reproducible without having
# to pass --today every time, but still overridable.
DEFAULT_TODAY = "2026-10-28"
