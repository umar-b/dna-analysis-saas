"""CLI smoke tests (ADR-0010). grade-stub runs the grader on bundled fixtures."""

import pytest

from dna_analysis.cli import main


def test_grade_stub_runs_and_reports(capsys):
    rc = main(["grade-stub"])
    out = capsys.readouterr().out
    assert rc == 0
    # per-entry (a)(b) lines for the three canned gold entries
    assert "rs4244285" in out
    assert "rs9923231" in out
    assert "rs4149056" in out
    # aggregates
    assert "2/3" in out  # surfaced: rs4244285 + rs9923231
    assert "1/3" in out  # cited: clopidogrel only
    # (c) report-level, clean fixture
    assert "PASS" in out


def test_help_lists_grade_stub(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "grade-stub" in capsys.readouterr().out
