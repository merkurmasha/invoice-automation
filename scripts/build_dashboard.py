"""Builds the portfolio dashboard: one self-contained HTML file, no
server, no external CDN, no login — open it by double-clicking.

    python -m scripts.build_dashboard [--month YYYY-MM] [--today YYYY-MM-DD] [--out dashboard/index.html]

Reuses the project's existing deterministic modules (aging,
reconciliation, validation, the accountant pack's ledger-building) via
scripts/dashboard_data.py, and the real eval result files via
scripts/eval_summary.py — no new pipeline logic, no LLM call, no
network access anywhere in this script (per CLAUDE.md). Prints exactly
one JSON object to stdout and exits:

    0 — ok: the dashboard was built
    1 — error: a bad --month/--today, or the build raised
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

from src.pack.config import DEFAULT_TODAY

from .dashboard_data import build_dashboard_data
from .dashboard_html import render

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "dashboard" / "index.html"

STATUS_OK = "ok"
STATUS_ERROR = "error"


def _default_month(today: date) -> str:
    return f"{today.year:04d}-{today.month:02d}"


def run_build_dashboard(month: str, today: date, out_path: Path) -> dict:
    """Builds the dashboard and returns the dict main() prints as JSON.
    Kept separate from main() so tests can call it directly, same
    pattern as scripts/build_pack.py's run_build_pack()."""
    try:
        with tempfile.TemporaryDirectory(prefix="dashboard_reminder_log_") as tmp_dir:
            nonexistent_log_path = Path(tmp_dir) / "reminder_log.csv"
            data = build_dashboard_data(month, today, nonexistent_log_path)
        html_text = render(data)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_text, encoding="utf-8")
    except (ValueError, OSError) as error:
        return {"status": STATUS_ERROR, "month": month, "error": str(error)}

    return {
        "status": STATUS_OK,
        "month": month,
        "today": today.isoformat(),
        "output_path": str(out_path),
        "size_bytes": out_path.stat().st_size,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the portfolio dashboard as one static HTML file.")
    parser.add_argument("--today", default=DEFAULT_TODAY, help="ISO date, e.g. 2026-10-28 (default: this project's demo 'today')")
    parser.add_argument("--month", default=None, help="YYYY-MM; defaults to --today's month")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output HTML path (default: dashboard/index.html)")
    args = parser.parse_args(argv)

    try:
        today = date.fromisoformat(args.today)
    except ValueError as error:
        result = {"status": STATUS_ERROR, "month": args.month, "error": f"bad --today: {error}"}
        print(json.dumps(result, indent=2))
        return 1

    month = args.month or _default_month(today)
    result = run_build_dashboard(month, today, Path(args.out))
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == STATUS_OK else 1


if __name__ == "__main__":
    sys.exit(main())
