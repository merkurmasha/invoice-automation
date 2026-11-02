"""Shared paths for the wrapper scripts in this folder.

Kept separate from src/*/config.py so this phase never edits those
modules' files (same rule phase 6/7 followed — see CLAUDE.md).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The real, persistent supplier master that process_invoice.py reads and
# writes on every run. Gitignored — it's runtime state the pipeline
# builds up over time, not project source, and it must never be the
# same file tests or evals/run_supplier_eval.py point SupplierMaster at
# (they always use a tmp_path).
SUPPLIER_MASTER_PATH = PROJECT_ROOT / "data" / "suppliers.csv"
