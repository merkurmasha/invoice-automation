"""The eval harness: runs every synthetic document through extract +
validate, scores the result against data/synthetic/answer_key.json, and
writes a report.

Runnable as:
    python -m evals.run_eval              # live run, asks before calling the API
    python -m evals.run_eval --offline     # score from cache only, never calls the API
    python -m evals.run_eval --model NAME  # override the model (see config.py)

Per CLAUDE.md, this never calls the Claude API without the human typing
"yes" first, and it never touches data/cache/seen_invoices.json (that's
the production duplicate-detector cache — this harness uses its own
fresh, in-memory detectors so a fixture file can never pollute real
app state, and a real run can never pollute the eval).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

from src.extract import config as extract_config
from src.extract import extract as extract_module
from src.extract.schema import ExtractedInvoice
from src.validate.duplicates import DuplicateDetector
from src.validate.validate import validate_invoice

from . import scoring
from .report import build_report, write_report

DATA_DIR = extract_config.PROJECT_ROOT / "data" / "synthetic"
ANSWER_KEY_PATH = DATA_DIR / "answer_key.json"
RESULTS_DIR = extract_config.PROJECT_ROOT / "evals" / "results"

# Rough per-document token estimate, used only to tell the human what a
# live run is about to cost before they approve it. Never used for scoring.
_ESTIMATED_INPUT_TOKENS = {"pdf": 3500, "photo": 6500}
_ESTIMATED_OUTPUT_TOKENS = 400


def _load_answer_key() -> list[dict]:
    return json.loads(ANSWER_KEY_PATH.read_text())


def genuinely_skipped(
    all_entries: list[dict],
    extracted_by_file: dict[str, object],
    extraction_failures: list[tuple[str, str]],
) -> list[str]:
    """Files with no result anywhere in the report: not extracted this
    run, and not already explained by an extraction failure. Must be
    computed AFTER extraction runs — the pre-run cache snapshot isn't
    good enough, since a live run goes on to extract whatever was
    uncached before it started."""
    extraction_failure_files = {f for f, _ in extraction_failures}
    return [
        entry["file"]
        for entry in all_entries
        if entry["file"] not in extracted_by_file
        and entry["file"] not in extraction_failure_files
    ]


def _pdf_sort_key(file_name: str) -> tuple[str, bool, str]:
    """Sort PDFs so an original always comes before its _dup/_near
    variant, regardless of plain alphabetical ordering."""
    stem = Path(file_name).stem
    if stem.endswith("_dup"):
        base, is_variant = stem[: -len("_dup")], True
    elif stem.endswith("_near"):
        base, is_variant = stem[: -len("_near")], True
    else:
        base, is_variant = stem, False
    return (base, is_variant, stem)


def _source_pdf_for(photo_file: str) -> str:
    return "invoices/" + Path(photo_file).stem + ".pdf"


def _estimate_tokens(file_names: list[str]) -> dict[str, int]:
    input_tokens = sum(
        _ESTIMATED_INPUT_TOKENS["photo" if f.startswith("photos/") else "pdf"]
        for f in file_names
    )
    output_tokens = len(file_names) * _ESTIMATED_OUTPUT_TOKENS
    return {"input": input_tokens, "output": output_tokens}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the extraction + validation eval harness.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Score using only cached extraction results; never call the API.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the model used for extraction (defaults to MODEL_NAME in src/extract/config.py).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    model = args.model or extract_config.MODEL_NAME

    answer_key = _load_answer_key()
    pdf_entries = sorted(
        (e for e in answer_key if e["file"].startswith("invoices/")),
        key=lambda e: _pdf_sort_key(e["file"]),
    )
    photo_entries = [e for e in answer_key if e["file"].startswith("photos/")]
    all_entries = pdf_entries + photo_entries

    cached = {
        entry["file"]: extract_module.is_cached(DATA_DIR / entry["file"], model)
        for entry in all_entries
    }
    # This is the PRE-run cache state, used only for the cost estimate /
    # confirmation prompt below. A live run goes on to extract these
    # files, so this list must never be reused as "what the report
    # should call skipped" — see `not_cached` built after the run.
    uncached_before_run = [f for f, is_cached in cached.items() if not is_cached]

    print("Trap -> expected validation outcome:")
    for trap, expectation in scoring.TRAP_EXPECTATIONS.items():
        print(f"  - {trap or 'no_trap'}: {expectation}")
    print()

    if args.offline:
        if uncached_before_run:
            print(f"{len(uncached_before_run)} file(s) have no cached result for model '{model}' — offline mode, skipping (not scored as failures):")
            for f in uncached_before_run:
                print(f"  - {f}")
            print()
    else:
        if uncached_before_run:
            estimate = _estimate_tokens(uncached_before_run)
            print(f"{len(uncached_before_run)} file(s) are not cached for model '{model}' and need a live API call:")
            for f in uncached_before_run:
                print(f"  - {f}")
            print(
                f"\nRough estimate: ~{estimate['input']} input tokens, "
                f"~{estimate['output']} output tokens.\n"
            )
            reply = input('Type "yes" to continue: ').strip().lower()
            if reply != "yes":
                print("Aborted — no API calls made.")
                return 1
        else:
            print("Every file is already cached for this model — no API calls needed.\n")

    usage = {"input": 0, "output": 0}

    def on_usage(input_tokens: int, output_tokens: int) -> None:
        usage["input"] += input_tokens
        usage["output"] += output_tokens

    extracted_by_file: dict[str, ExtractedInvoice] = {}
    extraction_failures: list[tuple[str, str]] = []

    def try_extract(file_name: str) -> ExtractedInvoice | None:
        if args.offline and not cached[file_name]:
            return None
        try:
            result = extract_module.extract_invoice(
                DATA_DIR / file_name, model=model, on_usage=on_usage
            )
            extracted_by_file[file_name] = result
            return result
        except extract_module.ExtractionError as error:
            extraction_failures.append((file_name, str(error)))
            return None

    start_time = time.monotonic()
    today = date.today()

    # Pass A: all PDFs in order, one fresh in-memory detector shared
    # across the whole pass. Never loaded from or saved to disk.
    pdf_detector = DuplicateDetector()
    pdf_validation = {}
    for entry in pdf_entries:
        result = try_extract(entry["file"])
        if result is not None:
            pdf_validation[entry["file"]] = validate_invoice(result, pdf_detector, today=today)

    # Pass B: each photo on its own, with its own fresh empty detector,
    # so a photo is never flagged as a duplicate of its own source PDF.
    photo_validation = {}
    for entry in photo_entries:
        result = try_extract(entry["file"])
        if result is not None:
            photo_detector = DuplicateDetector()
            photo_validation[entry["file"]] = validate_invoice(result, photo_detector, today=today)

    elapsed_seconds = time.monotonic() - start_time

    not_cached = genuinely_skipped(all_entries, extracted_by_file, extraction_failures)

    field_scores: list[scoring.FieldScore] = []
    for entry in all_entries:
        extracted = extracted_by_file.get(entry["file"])
        if extracted is None:
            continue
        doc_kind = "photo" if entry["file"].startswith("photos/") else "pdf"
        field_scores.extend(scoring.score_fields(entry, extracted, doc_kind))

    trap_results: list[scoring.TrapResult] = []
    for entry in pdf_entries:
        result = pdf_validation.get(entry["file"])
        if result is not None:
            is_repeat = Path(entry["file"]).stem.endswith("_dup")
            trap_results.append(
                scoring.evaluate_trap(entry["file"], entry["trap"], result.issues, is_repeat=is_repeat)
            )
    for entry in photo_entries:
        result = photo_validation.get(entry["file"])
        if result is not None:
            trap_results.append(scoring.evaluate_trap(entry["file"], entry["trap"], result.issues))

    photo_vs_pdf: dict[str, list[tuple[str, bool]]] = {}
    for entry in photo_entries:
        photo_result = extracted_by_file.get(entry["file"])
        pdf_result = extracted_by_file.get(_source_pdf_for(entry["file"]))
        if photo_result is not None and pdf_result is not None:
            photo_vs_pdf[entry["file"]] = scoring.compare_to_source(photo_result, pdf_result)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    report_data = {
        "model": model,
        "timestamp": timestamp,
        "elapsed_seconds": elapsed_seconds,
        "usage": usage,
        "not_cached": not_cached,
        "extraction_failures": extraction_failures,
        "field_scores": field_scores,
        "trap_results": trap_results,
        "photo_vs_pdf": photo_vs_pdf,
    }
    markdown_text, json_data = build_report(report_data)

    model_slug = model.replace("/", "-")
    md_path = RESULTS_DIR / f"{timestamp}_{model_slug}.md"
    json_path = RESULTS_DIR / f"{timestamp}_{model_slug}.json"
    write_report(markdown_text, json_data, md_path, json_path)

    overall_correct, overall_total = scoring.overall_accuracy(field_scores)
    print(f"\nOverall field accuracy: {overall_correct}/{overall_total}")
    print(f"Not cached / skipped: {len(not_cached)}")
    print(f"Extraction failures: {len(extraction_failures)}")
    print(f"Tokens used this run — input: {usage['input']}, output: {usage['output']}")
    print(f"Wall-clock time: {elapsed_seconds:.1f}s")
    print(f"\nReport written to:\n  {md_path}\n  {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
