"""Regression test for the real synthetic dataset: reuses
evals/run_reconcile_eval.py's ground truth and scoring to assert there
are never any false matches and the one genuinely unmatched line stays
unmatched. Protects the scoring calibration in config.py from silently
regressing - if this starts failing, a config.py change made the
matcher worse on real data, not just on the crafted unit tests above.
"""

from __future__ import annotations

from evals.run_reconcile_eval import EXPECTED_PARTIAL, score
from src.reconcile import config, ledger, match


def test_real_bank_statement_has_zero_false_matches_and_zero_missed():
    bank_lines = match.load_bank_statement(config.BANK_STATEMENT_PATH)
    payables = ledger.load_payable_obligations(config.ANSWER_KEY_PATH)
    receivables = ledger.load_receivable_obligations(config.SALES_INVOICES_PATH)
    decisions = match.reconcile(bank_lines, payables + receivables)

    result = score(decisions)

    assert result["false_matches"] == []
    assert result["missed_matches"] == []
    assert result["ambiguous"] == []
    assert result["unmatched_line_found"] is True
    assert set(result["partials_detected"]) == EXPECTED_PARTIAL
    assert len(result["correctly_matched"]) == result["real_matches_expected"]
