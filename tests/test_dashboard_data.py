"""Tests for scripts/dashboard_data.py: the dashboard's numbers are
assembled by calling the project's existing deterministic modules
(aging, reconciliation, validation, pack-building), reused as-is — no
LLM call, no new pipeline logic. These lock in known-good numbers that
also appear in data/packs/2026-10/summary.md (built the same way by
src/pack/build.py), so a regression in either place is caught."""

from __future__ import annotations

from datetime import date

from scripts.dashboard_data import build_dashboard_data
from src.reconcile import config as reconcile_config
from src.reconcile import match
from src.receivables.config import STAGE_OFFSETS_DAYS
from src.receivables.draft import STAGE_LABELS


def _build(tmp_path, month="2026-10", today=date(2026, 10, 28)):
    return build_dashboard_data(month, today, tmp_path / "no_such_reminder_log.csv")


def test_headline_numbers_are_consistent_with_their_own_panels(tmp_path):
    data = _build(tmp_path)

    assert data["headline"]["review_queue_count"] == len(data["review_queue"])

    outstanding_total = round(sum(b["outstanding"] for b in data["receivables_aging"]["buckets"]), 2)
    assert data["headline"]["open_receivables"] == outstanding_total

    assert data["headline"]["reconciliation_match_rate_pct"] == data["reconciliation"]["match_rate_pct"]

    spend_by_currency: dict[str, float] = {}
    for row in data["spend_by_category"]:
        spend_by_currency[row["currency"]] = round(spend_by_currency.get(row["currency"], 0.0) + row["total"], 2)
    for row in data["headline"]["total_spend"]:
        assert row["total"] == spend_by_currency[row["currency"]]


def test_october_spend_by_category_matches_the_known_accountant_pack(tmp_path):
    # Same figures as data/packs/2026-10/summary.md's "Top categories"
    # table, built independently via src.pack.build.build_pack().
    data = _build(tmp_path)

    totals = {row["category"]: row["total"] for row in data["spend_by_category"]}
    assert totals["Coworking & Office Space"] == 477.39
    assert totals["Printing & Supplies"] == 248.05
    assert totals["Travel"] == 229.90
    assert totals["Utilities"] == 228.93
    assert totals["Accounting & Legal"] == 217.80
    assert totals["Office Supplies"] == 154.40
    assert totals["Software & Subscriptions"] == 121.00


def test_october_aging_buckets_match_the_known_accountant_pack(tmp_path):
    # Same figures as data/packs/2026-10/summary.md's "Overdue
    # receivables (whole book, not just this month)" table.
    data = _build(tmp_path)

    buckets = {b["bucket"]: b for b in data["receivables_aging"]["buckets"]}
    assert buckets["current"] == {"bucket": "current", "count": 3, "outstanding": 6171.14}
    assert buckets["1-30"] == {"bucket": "1-30", "count": 2, "outstanding": 4414.64}
    assert buckets["31-60"] == {"bucket": "31-60", "count": 2, "outstanding": 4993.93}
    assert buckets["60+"] == {"bucket": "60+", "count": 2, "outstanding": 7527.97}


def test_review_queue_is_scoped_to_the_requested_month(tmp_path):
    data = _build(tmp_path)

    assert len(data["review_queue"]) == 2
    for item in data["review_queue"]:
        assert item["issue_date"].startswith("2026-10")


def test_reconciliation_runs_over_the_whole_bank_statement_not_just_the_month(tmp_path):
    data = _build(tmp_path)

    recon = data["reconciliation"]
    assert recon["total_lines"] == 37
    assert recon["by_category"] == {"auto": 29, "partial": 3, "possible": 4, "unmatched": 1}
    assert recon["matched_count"] == 32
    assert recon["needs_review_count"] == 5
    assert len(recon["needs_review_items"]) == 5


def test_reminder_stage_uses_the_given_log_path_not_the_real_gitignored_one(tmp_path):
    # Every overdue invoice should get a reminder stage computed from a
    # clean "nothing drafted yet" state, since the log path passed in
    # does not exist — never whatever a developer's local
    # data/reminder_log.csv happens to contain.
    data = _build(tmp_path)

    overdue = data["receivables_aging"]["overdue_invoices"]
    assert overdue, "expected at least one overdue invoice in the October demo data"
    for invoice in overdue:
        assert invoice["reminder"] is not None
        assert invoice["reminder"]["stage"] in (1, 2, 3)


def test_different_month_changes_spend_and_review_queue(tmp_path):
    october = _build(tmp_path, month="2026-10")
    september = _build(tmp_path, month="2026-09")

    assert october["spend_by_category"] != september["spend_by_category"]
    # Receivables aging and reconciliation are whole-book/whole-statement,
    # so they must NOT change just because `month` changed.
    assert october["receivables_aging"] == september["receivables_aging"]
    assert october["reconciliation"] == september["reconciliation"]


def test_reminder_stage_legend_matches_the_real_scheduling_code(tmp_path):
    # Must be read from src/receivables/config.py's STAGE_OFFSETS_DAYS
    # and src/receivables/draft.py's STAGE_LABELS, never hand-typed, so
    # the legend can't silently drift from the actual scheduling rule.
    data = _build(tmp_path)

    legend = {entry["stage"]: entry for entry in data["receivables_aging"]["reminder_stage_legend"]}

    assert set(legend) == set(STAGE_OFFSETS_DAYS)
    for stage, offset_days in STAGE_OFFSETS_DAYS.items():
        assert legend[stage]["days_after_due"] == offset_days
        assert legend[stage]["label"] == STAGE_LABELS[stage]


def test_bank_statement_through_is_the_real_last_transaction_date(tmp_path):
    data = _build(tmp_path)

    bank_lines = match.load_bank_statement(reconcile_config.BANK_STATEMENT_PATH)
    expected = max(line.txn_date for line in bank_lines).isoformat()

    assert data["bank_statement_through"] == expected
