"""Turns the data an eval run collects into a markdown report (for
humans) and a JSON report (for comparing runs over time programmatically
later). Pure formatting — no API calls, no filesystem writes beyond the
two files passed in.
"""

from __future__ import annotations

import json
from pathlib import Path

from .scoring import (
    FieldScore,
    TrapResult,
    accuracy_breakdown,
    field_mismatches,
    false_flags,
    high_confidence_wrong,
    lowest_confidence_correct,
    overall_accuracy,
    soft_flag_count,
    trap_misses,
)


def _pct(correct: int, total: int) -> str:
    return f"{(correct / total * 100):.1f}%" if total else "n/a"


def _accuracy_table(title: str, breakdown: dict[str, tuple[int, int]]) -> str:
    lines = [f"### {title}", "", "| Group | Correct | Total | Accuracy |", "| --- | --- | --- | --- |"]
    for key in sorted(breakdown):
        correct, total = breakdown[key]
        lines.append(f"| {key} | {correct} | {total} | {_pct(correct, total)} |")
    return "\n".join(lines)


def _trap_table(trap_results: list[TrapResult]) -> str:
    by_trap: dict[str, list[TrapResult]] = {}
    for result in trap_results:
        by_trap.setdefault(result.trap or "no_trap", []).append(result)

    lines = ["### Trap outcomes", "", "| Trap | Caught | Total | Expectation |", "| --- | --- | --- | --- |"]
    for trap_name in sorted(by_trap):
        results = by_trap[trap_name]
        caught = sum(1 for r in results if r.caught)
        expectation = results[0].note.split(";")[0].removeprefix("expected: ")
        lines.append(f"| {trap_name} | {caught} | {len(results)} | {expectation} |")
    return "\n".join(lines)


def _mismatch_table(mismatches: list[FieldScore]) -> str:
    if not mismatches:
        return "_No field mismatches._"
    lines = ["| File | Field | Expected | Actual | Confidence |", "| --- | --- | --- | --- | --- |"]
    for m in mismatches:
        lines.append(f"| {m.file} | {m.field} | {m.expected} | {m.actual} | {m.confidence:.2f} |")
    return "\n".join(lines)


def _trap_miss_table(misses: list[TrapResult]) -> str:
    if not misses:
        return "_No trap misses._"
    lines = ["| File | Trap | Detail |", "| --- | --- | --- |"]
    for m in misses:
        lines.append(f"| {m.file} | {m.trap or 'no_trap'} | {m.note} |")
    return "\n".join(lines)


def _confidence_table(scores: list[FieldScore]) -> str:
    if not scores:
        return "_None._"
    lines = ["| File | Field | Expected | Actual | Confidence |", "| --- | --- | --- | --- | --- |"]
    for s in scores:
        lines.append(f"| {s.file} | {s.field} | {s.expected} | {s.actual} | {s.confidence:.2f} |")
    return "\n".join(lines)


def _photo_vs_pdf_table(photo_vs_pdf: dict[str, list[tuple[str, bool]]]) -> str:
    if not photo_vs_pdf:
        return "_No photo had both itself and its source PDF extracted this run._"
    lines = ["| Photo | Field | Matches source PDF |", "| --- | --- | --- |"]
    for photo_file, field_results in photo_vs_pdf.items():
        for field, matches in field_results:
            lines.append(f"| {photo_file} | {field} | {'yes' if matches else 'NO'} |")
    return "\n".join(lines)


def build_report(data: dict) -> tuple[str, dict]:
    """Returns (markdown_text, json_data). `data` is the dict assembled
    in run_eval.py's main()."""
    scores: list[FieldScore] = data["field_scores"]
    trap_results: list[TrapResult] = data["trap_results"]
    photo_vs_pdf = data["photo_vs_pdf"]

    overall_correct, overall_total = overall_accuracy(scores)
    by_doc_kind = accuracy_breakdown(scores, lambda s: s.doc_kind)
    by_language = accuracy_breakdown(scores, lambda s: s.language or "unknown")
    by_currency = accuracy_breakdown(scores, lambda s: s.currency or "unknown")

    misses = field_mismatches(scores)
    t_misses = trap_misses(trap_results)
    flagged, flag_tally = false_flags(trap_results)
    soft_flags = soft_flag_count(trap_results)
    lowest_conf = lowest_confidence_correct(scores, n=5)
    high_conf_wrong = high_confidence_wrong(scores, threshold=0.90)

    md = []
    md.append(f"# Eval run — {data['model']} — {data['timestamp']}")
    md.append("")
    md.append("## Run metadata")
    md.append("")
    md.append(f"- Model: `{data['model']}`")
    md.append(f"- Wall-clock time: {data['elapsed_seconds']:.1f}s")
    md.append(f"- Tokens used this run — input: {data['usage']['input']}, output: {data['usage']['output']}")
    md.append(f"- Not cached / skipped: {len(data['not_cached'])}")
    md.append(f"- Extraction failures: {len(data['extraction_failures'])}")
    md.append("")

    md.append("## Field-level accuracy")
    md.append("")
    md.append(f"**Overall: {overall_correct}/{overall_total} fields correct ({_pct(overall_correct, overall_total)})**")
    md.append("")
    md.append(_accuracy_table("By document type", by_doc_kind))
    md.append("")
    md.append(_accuracy_table("By language", by_language))
    md.append("")
    md.append(_accuracy_table("By currency", by_currency))
    md.append("")

    md.append("## Validation / trap scoring")
    md.append("")
    md.append(_trap_table(trap_results))
    md.append("")
    md.append(f"**False flags:** {len(flagged)} clean document(s) got an unexpected error.")
    md.append("")
    if flag_tally:
        md.append("| Issue code | Count |")
        md.append("| --- | --- |")
        for code in sorted(flag_tally):
            md.append(f"| {code} | {flag_tally[code]} |")
    else:
        md.append("_No false flags._")
    md.append("")
    md.append(f"**Soft flags (LOW_CONFIDENCE warning, not counted as a failure):** {soft_flags}")
    md.append("")

    md.append("## Photo vs. source PDF")
    md.append("")
    md.append(_photo_vs_pdf_table(photo_vs_pdf))
    md.append("")

    md.append("## Misses")
    md.append("")
    md.append("### Field mismatches")
    md.append("")
    md.append(_mismatch_table(misses))
    md.append("")
    md.append("### Trap misses")
    md.append("")
    md.append(_trap_miss_table(t_misses))
    md.append("")

    md.append("## Confidence sanity check")
    md.append("")
    md.append("### 5 lowest-confidence *correct* fields")
    md.append("")
    md.append(_confidence_table(lowest_conf))
    md.append("")
    md.append("### Wrong fields with confidence above 0.90")
    md.append("")
    md.append(_confidence_table(high_conf_wrong))
    md.append("")

    if data["not_cached"]:
        md.append("## Not cached (skipped, not scored)")
        md.append("")
        for f in data["not_cached"]:
            md.append(f"- {f}")
        md.append("")

    if data["extraction_failures"]:
        md.append("## Extraction failures")
        md.append("")
        for f, error in data["extraction_failures"]:
            md.append(f"- {f}: {error}")
        md.append("")

    markdown_text = "\n".join(md)

    json_data = {
        "model": data["model"],
        "timestamp": data["timestamp"],
        "elapsed_seconds": data["elapsed_seconds"],
        "usage": data["usage"],
        "not_cached": data["not_cached"],
        "extraction_failures": data["extraction_failures"],
        "overall_accuracy": {"correct": overall_correct, "total": overall_total},
        "accuracy_by_doc_kind": by_doc_kind,
        "accuracy_by_language": by_language,
        "accuracy_by_currency": by_currency,
        "trap_results": [
            {
                "file": r.file,
                "trap": r.trap,
                "caught": r.caught,
                "is_false_flag": r.is_false_flag,
                "has_soft_flag": r.has_soft_flag,
                "error_codes": sorted(r.error_codes),
            }
            for r in trap_results
        ],
        "false_flag_tally": flag_tally,
        "soft_flag_count": soft_flags,
        "field_mismatches": [
            {
                "file": m.file,
                "field": m.field,
                "expected": m.expected,
                "actual": m.actual,
                "confidence": m.confidence,
            }
            for m in misses
        ],
        "trap_misses": [{"file": m.file, "trap": m.trap, "note": m.note} for m in t_misses],
        "lowest_confidence_correct": [
            {"file": s.file, "field": s.field, "confidence": s.confidence} for s in lowest_conf
        ],
        "high_confidence_wrong": [
            {"file": s.file, "field": s.field, "confidence": s.confidence} for s in high_conf_wrong
        ],
        "photo_vs_source_pdf": {
            photo: [{"field": field, "matches": matches} for field, matches in results]
            for photo, results in photo_vs_pdf.items()
        },
    }
    return markdown_text, json_data


def write_report(markdown_text: str, json_data: dict, md_path: Path, json_path: Path) -> None:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_text)
    json_path.write_text(json.dumps(json_data, indent=2, default=str))
