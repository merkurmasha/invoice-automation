"""Generates the full synthetic dataset: supplier invoice PDFs, degraded
phone-photo JPEGs, the answer key, and the sales/bank CSVs.

Run as:
    python -m src.synthetic.generate [--out DIR]

Everything is built from a fixed random seed (see jobs.py / sales_bank.py),
so re-running this script produces byte-for-byte identical output. Exit
code is 0 on success, 1 on failure - useful when this is later called as
a step from an n8n workflow.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from src.synthetic.answer_key import build_answer_key
from src.synthetic.jobs import build_jobs
from src.synthetic.pdf_render import render_invoice_pdf
from src.synthetic.photos import PHOTO_SEED_OFFSET, pdf_to_phone_photo
from src.synthetic.sales_bank import build_bank_lines, build_sales_invoices, write_bank_csv, write_sales_invoices_csv

DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"


def generate(out_dir: Path) -> list[dict]:
    invoices_dir = out_dir / "invoices"
    photos_dir = out_dir / "photos"
    bank_dir = out_dir / "bank"
    invoices_dir.mkdir(parents=True, exist_ok=True)
    photos_dir.mkdir(parents=True, exist_ok=True)
    bank_dir.mkdir(parents=True, exist_ok=True)

    jobs = build_jobs()
    for job in jobs:
        render_invoice_pdf(job, invoices_dir / f"{job.file_stem}.pdf")

    for i, job in enumerate(j for j in jobs if j.is_photo_source):
        pdf_path = invoices_dir / f"{job.file_stem}.pdf"
        photo_path = photos_dir / f"{job.file_stem}.jpg"
        pdf_to_phone_photo(pdf_path, photo_path, seed=PHOTO_SEED_OFFSET + i)

    sales_invoices = build_sales_invoices()
    write_sales_invoices_csv(sales_invoices, out_dir / "sales_invoices.csv")

    bank_lines = build_bank_lines(jobs, sales_invoices)
    write_bank_csv(bank_lines, bank_dir / "statement.csv")

    answer_key = build_answer_key(jobs)
    with (out_dir / "answer_key.json").open("w", encoding="utf-8") as f:
        json.dump(answer_key, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return answer_key


def print_summary(answer_key: list[dict]) -> None:
    trap_files: dict[str | None, list[str]] = {}
    for entry in answer_key:
        trap_files.setdefault(entry["trap"], []).append(entry["file"])

    print("\nSynthetic dataset summary")
    print("=" * 60)
    print(f"{'trap type':<20} {'count':>5}  files")
    print("-" * 60)
    for trap, files in sorted(trap_files.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        label = trap or "(no trap)"
        print(f"{label:<20} {len(files):>5}  {', '.join(files)}")
    print("-" * 60)
    print(f"total answer-key entries: {len(answer_key)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"output directory for the synthetic dataset (default: {DEFAULT_OUT_DIR})",
    )
    args = parser.parse_args(argv)

    try:
        answer_key = generate(args.out)
    except Exception as exc:  # noqa: BLE001 - CLI entry point, report and exit non-zero
        print(f"error: synthetic data generation failed: {exc}", file=sys.stderr)
        return 1

    print_summary(answer_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
