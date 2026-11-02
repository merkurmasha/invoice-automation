"""Tests for scripts/build_pack.py. No LLM call is involved anywhere in
this wrapper (src.pack.build is plain deterministic code, per
CLAUDE.md), so these are plain functional tests — nothing to mock.
"""

from __future__ import annotations

from datetime import date

from scripts import build_pack as build_pack_module


def test_build_pack_reports_ok_and_lists_files(tmp_path):
    result = build_pack_module.run_build_pack("2026-09", tmp_path / "pack", date(2026, 10, 28))

    assert result["status"] == "ok"
    assert result["month"] == "2026-09"
    assert result["output_path"] == str(tmp_path / "pack" / "2026-09")
    assert any(f.endswith("ledger.csv") for f in result["files"])
    assert any(f.endswith("summary.md") for f in result["files"])
    assert any(f.endswith("exceptions.csv") for f in result["files"])


def test_build_pack_unwritable_out_dir_is_an_error_not_a_crash(tmp_path):
    # out_dir's parent component is a plain file, so build_pack() can't
    # mkdir() the pack directory inside it — this should be reported as
    # an "error" result, not an uncaught OSError.
    blocking_file = tmp_path / "not_a_directory"
    blocking_file.write_text("")

    result = build_pack_module.run_build_pack("2026-09", blocking_file, date(2026, 10, 28))

    assert result["status"] == "error"
    assert "error" in result


def test_main_prints_one_json_object_and_exits_zero(tmp_path, capsys):
    exit_code = build_pack_module.main(
        ["2026-09", "--out", str(tmp_path / "pack"), "--today", "2026-10-28"]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert '"status": "ok"' in out


def test_main_exits_one_on_bad_today(tmp_path, capsys):
    exit_code = build_pack_module.main(
        ["2026-09", "--out", str(tmp_path / "pack"), "--today", "not-a-date"]
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert '"status": "error"' in out
