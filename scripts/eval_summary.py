"""Reads the project's own eval result files (evals/results/*.json) and
boils them down to the handful of numbers the dashboard's "Accuracy"
strip shows.

Plain deterministic code, no LLM call, no network access — it only
reads JSON files this project already committed (see evals/run_eval.py,
evals/run_supplier_eval.py and evals/run_reconcile_eval.py, which wrote
them from real API runs). Picked by content shape, not filename
convention, so a future eval run with a different name still sorts
into the right bucket:

  - a reconciliation report has "correctly_matched_count"
  - a categorisation report has "category_accuracy" (dataset field
    says "synthetic" vs "heldout")
  - an extraction report has "overall_accuracy"; "accuracy_by_challenge"
    is only present on a held-out run (see evals/scoring.py)

Within each bucket, files are read in filename order (they're
timestamped YYYY-MM-DD_HHMM..., so that's chronological) — the
synthetic-extraction bucket reports its FIRST and LAST entry (an
accuracy-over-time "before -> after"), every other bucket reports only
its latest.

If no eval result files exist at all (e.g. evals/results/ was emptied),
each missing bucket falls back to the fixed numbers in
_HARDCODED_FALLBACK below — the real figures from this project's actual
eval runs, re-typed here as a last resort so the dashboard never shows
nothing. `missing` in the returned dict names which buckets, if any,
came from that fallback rather than a real file.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_RESULTS_DIR = PROJECT_ROOT / "evals" / "results"

# Last-resort numbers, taken from this project's real eval runs as of
# 2026-10-30 (see evals/results/*.md for the reports they came from).
# Only used for a bucket whose eval result file is genuinely missing.
_HARDCODED_FALLBACK = {
    "extraction_synthetic_before_pct": 97.4,
    "extraction_synthetic_after_pct": 100.0,
    "extraction_heldout_pct": 98.6,
    "categorisation_synthetic_pct": 87.0,
    "categorisation_heldout_pct": 64.3,
    "reconciliation_correct": 36,
    "reconciliation_expected": 36,
    "reconciliation_false_matches": 0,
}


def _pct(correct: int, total: int) -> float:
    return round(100 * correct / total, 1) if total else 0.0


def _read_json_files(results_dir: Path) -> list[tuple[str, dict]]:
    if not results_dir.is_dir():
        return []
    files: list[tuple[str, dict]] = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            files.append((path.name, json.loads(path.read_text())))
        except (OSError, json.JSONDecodeError):
            continue
    return files


def load_accuracy_strip(results_dir: Path = EVAL_RESULTS_DIR) -> dict:
    """Returns the dashboard's accuracy-strip numbers plus a `missing`
    list naming any bucket that had to fall back to the hardcoded
    numbers above."""
    extraction_synthetic: list[dict] = []
    extraction_heldout: list[dict] = []
    categorisation_synthetic: list[dict] = []
    categorisation_heldout: list[dict] = []
    reconciliation: list[dict] = []

    for _name, data in _read_json_files(results_dir):
        if "correctly_matched_count" in data:
            reconciliation.append(data)
        elif "category_accuracy" in data:
            (categorisation_heldout if data.get("dataset") == "heldout" else categorisation_synthetic).append(data)
        elif "overall_accuracy" in data:
            (extraction_heldout if "accuracy_by_challenge" in data else extraction_synthetic).append(data)

    result: dict = {"missing": []}

    if extraction_synthetic:
        first_acc = extraction_synthetic[0]["overall_accuracy"]
        last_acc = extraction_synthetic[-1]["overall_accuracy"]
        result["extraction_synthetic_before_pct"] = _pct(first_acc["correct"], first_acc["total"])
        result["extraction_synthetic_after_pct"] = _pct(last_acc["correct"], last_acc["total"])
    else:
        result["extraction_synthetic_before_pct"] = _HARDCODED_FALLBACK["extraction_synthetic_before_pct"]
        result["extraction_synthetic_after_pct"] = _HARDCODED_FALLBACK["extraction_synthetic_after_pct"]
        result["missing"].append("extraction_synthetic")

    if extraction_heldout:
        acc = extraction_heldout[-1]["overall_accuracy"]
        result["extraction_heldout_pct"] = _pct(acc["correct"], acc["total"])
    else:
        result["extraction_heldout_pct"] = _HARDCODED_FALLBACK["extraction_heldout_pct"]
        result["missing"].append("extraction_heldout")

    if categorisation_synthetic:
        acc = categorisation_synthetic[-1]["category_accuracy"]
        result["categorisation_synthetic_pct"] = _pct(acc["correct"], acc["total"])
    else:
        result["categorisation_synthetic_pct"] = _HARDCODED_FALLBACK["categorisation_synthetic_pct"]
        result["missing"].append("categorisation_synthetic")

    if categorisation_heldout:
        acc = categorisation_heldout[-1]["category_accuracy"]
        result["categorisation_heldout_pct"] = _pct(acc["correct"], acc["total"])
    else:
        result["categorisation_heldout_pct"] = _HARDCODED_FALLBACK["categorisation_heldout_pct"]
        result["missing"].append("categorisation_heldout")

    if reconciliation:
        latest = reconciliation[-1]
        result["reconciliation_correct"] = latest["correctly_matched_count"]
        result["reconciliation_expected"] = latest["real_matches_expected"]
        result["reconciliation_false_matches"] = len(latest["false_matches"])
    else:
        result["reconciliation_correct"] = _HARDCODED_FALLBACK["reconciliation_correct"]
        result["reconciliation_expected"] = _HARDCODED_FALLBACK["reconciliation_expected"]
        result["reconciliation_false_matches"] = _HARDCODED_FALLBACK["reconciliation_false_matches"]
        result["missing"].append("reconciliation")

    return result
