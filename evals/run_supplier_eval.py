"""Eval harness for supplier matching + expense categorisation.

Runs every document's `supplier_as_printed` through a FRESH temporary
SupplierMaster (never data/suppliers.csv), in answer-key file order,
then categorises each one and scores both steps against the answer
key.

Runnable as:
    python -m evals.run_supplier_eval                    # live run, asks before calling the API
    python -m evals.run_supplier_eval --offline           # score from cache only, never call the API
    python -m evals.run_supplier_eval --dataset heldout   # score data/heldout/ instead of data/synthetic/

Per CLAUDE.md, this never calls the Claude API without the human
typing "yes" first. It also never touches data/suppliers.csv or
data/review_queue.csv — everything runs against fresh files in a
temporary directory, so a fixture run can never pollute real app
state (same principle run_eval.py applies to seen_invoices.json).

--- Mapping the answer keys onto the chart of accounts -----------------

config/chart_of_accounts.yaml has 12 categories. 9 of the answer keys'
`expected_category` strings map onto them 1:1. Two more categories that
appear in the *synthetic* (core) answer key — "Meals & Entertainment"
and "Shipping & Courier" — did not fit any of the original ~10
proposed categories; the user chose (2026-10-30) to add them to the
chart as their own codes rather than folding them into "other".

"Equipment" and "Facilities & Maintenance" appear only in the
*held-out* answer key, which is deliberately built to test
generalisation to things the system has never seen. Mapping those to
"other" is the intended, correct answer for them — not a mapping gap —
so they're listed here too, but on purpose.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from src.extract import config as extract_config
from src.suppliers import categorise as categorise_module
from src.suppliers import review_queue
from src.suppliers.config import CATEGORISE_MODEL, CATEGORISE_PROMPT_VERSION
from src.suppliers.master import SupplierMaster

RESULTS_DIR = extract_config.PROJECT_ROOT / "evals" / "results"

ANSWER_KEY_TO_CODE = {
    "Software & Subscriptions": "software_subscriptions",
    "Coworking & Office Space": "rent_coworking",
    "Utilities": "utilities",
    "Professional Services": "professional_services",
    "Printing & Supplies": "printing_marketing",
    "Travel": "travel",
    "Office Supplies": "office_supplies_furniture",
    "Insurance": "insurance",
    "Accounting & Legal": "accounting_legal",
    "Meals & Entertainment": "meals_entertainment",
    "Shipping & Courier": "shipping_courier",
    "Equipment": "other",
    "Facilities & Maintenance": "other",
}

# Rough per-call token estimate, used only to tell the human what a live
# run is about to cost before they approve it. Never used for scoring.
_ESTIMATED_INPUT_TOKENS = 350
_ESTIMATED_OUTPUT_TOKENS = 80


def expected_code(entry: dict) -> str:
    category = entry["expected_category"]
    if category not in ANSWER_KEY_TO_CODE:
        raise KeyError(
            f"{entry['file']}: expected_category {category!r} has no entry in "
            "ANSWER_KEY_TO_CODE — add it instead of silently skipping this file."
        )
    return ANSWER_KEY_TO_CODE[category]


# ---------------------------------------------------------------------------
# Pure scoring helpers (no API calls, no filesystem) — unit tested directly.
# ---------------------------------------------------------------------------


def score_supplier_merging(
    answer_key: list[dict], assigned_ids: dict[str, str]
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Compare the supplier_id the master assigned each file against the
    answer key's ground-truth canonical `supplier` name.

    Returns (missed_merges, false_merges):
      - missed_merges: {true_canonical_name: {assigned_ids}} for names that
        should all share one supplier_id but didn't.
      - false_merges: {assigned_id: {true_canonical_names}} for an id that
        was given to more than one genuinely different real supplier.
    """
    by_true_name: dict[str, set[str]] = {}
    by_assigned_id: dict[str, set[str]] = {}
    for entry in answer_key:
        assigned_id = assigned_ids[entry["file"]]
        by_true_name.setdefault(entry["supplier"], set()).add(assigned_id)
        by_assigned_id.setdefault(assigned_id, set()).add(entry["supplier"])

    missed_merges = {name: ids for name, ids in by_true_name.items() if len(ids) > 1}
    false_merges = {sid: names for sid, names in by_assigned_id.items() if len(names) > 1}
    return missed_merges, false_merges


def confidently_wrong(
    category_scores: list[dict], threshold: float = 0.90
) -> list[dict]:
    """Category results that are wrong but reported above `threshold`
    confidence — the dangerous case: a mistake the system itself didn't
    flag for review."""
    return [s for s in category_scores if not s["correct"] and s["confidence"] > threshold]


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------


def _pct(correct: int, total: int) -> str:
    return f"{(correct / total * 100):.1f}%" if total else "n/a"


def build_report(data: dict) -> tuple[str, dict]:
    category_scores = data["category_scores"]
    missed_merges = data["missed_merges"]
    false_merges = data["false_merges"]
    match_statuses = data["match_statuses"]
    review_items = data["review_items"]

    cat_correct = sum(1 for s in category_scores if s["correct"])
    cat_total = len(category_scores)
    conf_wrong = confidently_wrong(category_scores)

    md = []
    md.append(f"# Supplier matching + categorisation eval — {data['model']} — {data['timestamp']}")
    md.append("")
    md.append("## Run metadata")
    md.append("")
    md.append(f"- Model: `{data['model']}`")
    md.append(f"- Categorisation prompt version: `{data['prompt_version']}`")
    md.append(f"- Dataset: `{data['dataset']}`")
    md.append(f"- Tokens used this run — input: {data['usage']['input']}, output: {data['usage']['output']}")
    md.append("")

    md.append("## (a) Supplier merge accuracy")
    md.append("")
    md.append(f"- Missed merges (same real supplier, different supplier_id assigned): {len(missed_merges)}")
    md.append(f"- False merges (different real suppliers given the same supplier_id): {len(false_merges)}")
    md.append("")
    status_tally: dict[str, int] = {}
    for status in match_statuses:
        status_tally[status] = status_tally.get(status, 0) + 1
    md.append("| Match status | Count |")
    md.append("| --- | --- |")
    for status in sorted(status_tally):
        md.append(f"| {status} | {status_tally[status]} |")
    md.append("")
    if missed_merges:
        md.append("### Missed merges")
        md.append("")
        md.append("| True supplier | Supplier IDs assigned |")
        md.append("| --- | --- |")
        for name, ids in missed_merges.items():
            md.append(f"| {name} | {', '.join(sorted(ids))} |")
        md.append("")
    if false_merges:
        md.append("### False merges")
        md.append("")
        md.append("| Supplier ID | True suppliers merged together |")
        md.append("| --- | --- |")
        for sid, names in false_merges.items():
            md.append(f"| {sid} | {', '.join(sorted(names))} |")
        md.append("")

    md.append("## (b) Categorisation accuracy")
    md.append("")
    md.append(f"**Overall: {cat_correct}/{cat_total} correct ({_pct(cat_correct, cat_total)})**")
    md.append("")
    low_conf_count = sum(1 for item in review_items if item.item_type == "low_confidence_category")
    md.append(f"- Routed to review queue for low confidence: {low_conf_count}")
    md.append("")
    md.append("| File | Supplier | Expected | Actual | Confidence | Correct |")
    md.append("| --- | --- | --- | --- | --- | --- |")
    for score in category_scores:
        md.append(
            f"| {score['file']} | {score['supplier']} | {score['expected']} | "
            f"{score['actual']} | {score['confidence']:.2f} | {'yes' if score['correct'] else 'NO'} |"
        )
    md.append("")

    md.append("## (c) Confidence calibration")
    md.append("")
    md.append(f"**Wrong categories reported with confidence above 0.90: {len(conf_wrong)}**")
    md.append("")
    if conf_wrong:
        md.append("| File | Supplier | Expected | Actual | Confidence |")
        md.append("| --- | --- | --- | --- | --- |")
        for score in conf_wrong:
            md.append(
                f"| {score['file']} | {score['supplier']} | {score['expected']} | "
                f"{score['actual']} | {score['confidence']:.2f} |"
            )
    else:
        md.append("_None._")
    md.append("")

    md.append("## Review queue")
    md.append("")
    md.append(f"Total items logged this run: {len(review_items)}")
    md.append("")
    if review_items:
        md.append("| Item type | File | Reason |")
        md.append("| --- | --- | --- |")
        for item in review_items:
            md.append(f"| {item.item_type} | {item.file} | {item.reason} |")
    md.append("")

    markdown_text = "\n".join(md)
    json_data = {
        "model": data["model"],
        "prompt_version": data["prompt_version"],
        "dataset": data["dataset"],
        "timestamp": data["timestamp"],
        "usage": data["usage"],
        "match_status_tally": status_tally,
        "missed_merges": {name: sorted(ids) for name, ids in missed_merges.items()},
        "false_merges": {sid: sorted(names) for sid, names in false_merges.items()},
        "category_accuracy": {"correct": cat_correct, "total": cat_total},
        "category_scores": category_scores,
        "confidently_wrong": conf_wrong,
        "review_queue_count": len(review_items),
        "review_queue_items": [
            {"item_type": i.item_type, "file": i.file, "reason": i.reason, "date": i.date}
            for i in review_items
        ],
    }
    return markdown_text, json_data


def write_report(markdown_text: str, json_data: dict, md_path: Path, json_path: Path) -> None:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_text)
    json_path.write_text(json.dumps(json_data, indent=2, default=str))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the supplier-matching + categorisation eval harness."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Score using only cached categorisation results; never call the API.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the categorisation model (defaults to CATEGORISE_MODEL in src/suppliers/config.py).",
    )
    parser.add_argument(
        "--dataset",
        choices=["synthetic", "heldout"],
        default="synthetic",
        help="Which dataset to evaluate: 'synthetic' (default) or 'heldout'.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    model = args.model or CATEGORISE_MODEL

    data_dir = extract_config.PROJECT_ROOT / "data" / args.dataset
    answer_key: list[dict] = json.loads((data_dir / "answer_key.json").read_text())
    answer_key = sorted(answer_key, key=lambda e: e["file"])

    # Validate the mapping up front, so a gap is a clear error before any
    # API call, not a crash halfway through a live run.
    for entry in answer_key:
        expected_code(entry)

    cached = {
        entry["file"]: categorise_module.is_cached(entry["supplier_as_printed"], None, model)
        for entry in answer_key
    }
    uncached_before_run = [f for f, is_cached in cached.items() if not is_cached]

    if args.offline:
        if uncached_before_run:
            print(
                f"{len(uncached_before_run)} file(s) have no cached categorisation for "
                f"model '{model}' — offline mode, skipping (not scored as failures):"
            )
            for f in uncached_before_run:
                print(f"  - {f}")
            print()
    else:
        if uncached_before_run:
            est_input = len(uncached_before_run) * _ESTIMATED_INPUT_TOKENS
            est_output = len(uncached_before_run) * _ESTIMATED_OUTPUT_TOKENS
            print(
                f"{len(uncached_before_run)} file(s) are not cached for model '{model}' "
                "and need a live API call:"
            )
            for f in uncached_before_run:
                print(f"  - {f}")
            print(f"\nRough estimate: ~{est_input} input tokens, ~{est_output} output tokens.\n")
            reply = input('Type "yes" to continue: ').strip().lower()
            if reply != "yes":
                print("Aborted — no API calls made.")
                return 1
        else:
            print("Every file is already cached for this model — no API calls needed.\n")

    with tempfile.TemporaryDirectory(prefix="supplier_eval_") as tmp_dir:
        master_path = Path(tmp_dir) / "suppliers.csv"
        review_queue_path = Path(tmp_dir) / "review_queue.csv"
        master = SupplierMaster(master_path)

        usage = {"input": 0, "output": 0}

        def on_usage(input_tokens: int, output_tokens: int) -> None:
            usage["input"] += input_tokens
            usage["output"] += output_tokens

        assigned_ids: dict[str, str] = {}
        match_statuses: list[str] = []
        category_scores: list[dict] = []

        for entry in answer_key:
            file_name = entry["file"]
            printed_name = entry["supplier_as_printed"]

            match_result = master.match_or_create(printed_name)
            assigned_ids[file_name] = match_result.supplier_id
            match_statuses.append(match_result.status)

            if match_result.status == "new":
                review_queue.add_item(
                    review_queue_path,
                    "new_supplier",
                    file_name,
                    f"no match above review threshold for printed name {printed_name!r}",
                )
            elif match_result.status == "possible_match":
                review_queue.add_item(
                    review_queue_path,
                    "possible_match",
                    file_name,
                    f"{printed_name!r} ~ {match_result.matched_against!r} "
                    f"(score {match_result.score:.1f})",
                )

            if args.offline and not cached[file_name]:
                continue

            try:
                result = categorise_module.categorise(
                    printed_name, None, model=model, on_usage=on_usage
                )
            except categorise_module.CategorisationError as error:
                print(f"Categorisation error for {file_name}: {error}", file=sys.stderr)
                continue

            expected = expected_code(entry)
            category_scores.append(
                {
                    "file": file_name,
                    "supplier": printed_name,
                    "expected": expected,
                    "actual": result.category_code,
                    "confidence": result.confidence,
                    "correct": result.category_code == expected,
                }
            )
            if result.needs_review():
                review_queue.add_item(
                    review_queue_path,
                    "low_confidence_category",
                    file_name,
                    f"category {result.category_code!r} confidence "
                    f"{result.confidence:.2f} below threshold",
                )

        missed_merges, false_merges = score_supplier_merging(answer_key, assigned_ids)
        review_items = review_queue.list_open_items(review_queue_path)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    report_data = {
        "model": model,
        "prompt_version": CATEGORISE_PROMPT_VERSION,
        "dataset": args.dataset,
        "timestamp": timestamp,
        "usage": usage,
        "category_scores": category_scores,
        "missed_merges": missed_merges,
        "false_merges": false_merges,
        "match_statuses": match_statuses,
        "review_items": review_items,
    }
    markdown_text, json_data = build_report(report_data)

    model_slug = model.replace("/", "-")
    dataset_suffix = "" if args.dataset == "synthetic" else f"_{args.dataset}"
    md_path = RESULTS_DIR / f"{timestamp}_suppliers_{model_slug}_{CATEGORISE_PROMPT_VERSION}{dataset_suffix}.md"
    json_path = RESULTS_DIR / f"{timestamp}_suppliers_{model_slug}_{CATEGORISE_PROMPT_VERSION}{dataset_suffix}.json"
    write_report(markdown_text, json_data, md_path, json_path)

    cat_correct = sum(1 for s in category_scores if s["correct"])
    print(f"\nCategorisation accuracy: {cat_correct}/{len(category_scores)}")
    print(f"Missed supplier merges: {len(missed_merges)}")
    print(f"False supplier merges: {len(false_merges)}")
    print(f"Review queue items: {len(review_items)}")
    print(f"Tokens used this run — input: {usage['input']}, output: {usage['output']}")
    print(f"\nReport written to:\n  {md_path}\n  {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
