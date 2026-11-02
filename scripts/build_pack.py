"""n8n wrapper: build the month-end accountant pack.

    .venv/bin/python -m scripts.build_pack <YYYY-MM> [--out data/packs/] [--today YYYY-MM-DD]

Thin wrapper around src.pack.build.build_pack() — no pipeline logic of
its own, and no LLM call anywhere in this script or in build_pack()
itself (see src/pack/build.py's own module docstring; this phase
follows the same plain-code rule from CLAUDE.md). Prints exactly one
JSON object to stdout with the output path and every file written, and
exits:

    0 — ok: the pack was built
    1 — error: a bad --month/--out, or build_pack() itself raised

There is no "needs review" state for building a pack — review-worthy
problems inside the data (validation issues, reconciliation exceptions)
are reported as rows *inside* exceptions.csv / summary.md, not as this
script's exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.pack.build import build_pack
from src.pack.config import DEFAULT_TODAY, PACKS_DIR

STATUS_OK = "ok"
STATUS_ERROR = "error"


def run_build_pack(month: str, out_dir: Path, today: date) -> dict:
    """Builds the pack and returns the dict main() prints as JSON.
    Kept separate from main() so tests can call it directly."""
    try:
        pack_dir = build_pack(month, out_dir, today)
    except (ValueError, OSError) as error:
        return {"status": STATUS_ERROR, "month": month, "error": str(error)}

    files = sorted(str(p) for p in pack_dir.rglob("*") if p.is_file())
    return {
        "status": STATUS_OK,
        "month": month,
        "output_path": str(pack_dir),
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the month-end accountant pack.")
    parser.add_argument("month", help="YYYY-MM, e.g. 2026-09")
    parser.add_argument("--out", default=str(PACKS_DIR), help="Output directory")
    parser.add_argument("--today", default=DEFAULT_TODAY, help="ISO date for aging/overdue sections")
    args = parser.parse_args(argv)

    try:
        today = date.fromisoformat(args.today)
    except ValueError as error:
        result = {"status": STATUS_ERROR, "month": args.month, "error": f"bad --today: {error}"}
    else:
        result = run_build_pack(args.month, Path(args.out), today)

    print(json.dumps(result, indent=2))
    return 0 if result["status"] == STATUS_OK else 1


if __name__ == "__main__":
    sys.exit(main())
