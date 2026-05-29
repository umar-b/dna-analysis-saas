"""Regression guard on the committed gold.yaml (issue #4).

Genome-presence and allowlist cross-checks are curation-time steps (they need
the gitignored PII genome + ETL output); they were run when gold.yaml was
locked. This committed test guards the schema + coverage-mix invariants that
must hold in CI.
"""

from pathlib import Path

from dna_analysis.grader.loaders import parse_gold

GOLD = Path(__file__).resolve().parents[2] / "gold.yaml"


def test_gold_yaml_parses_against_schema_with_coverage_mix():
    gold = parse_gold(GOLD.read_text())
    assert len(gold) >= 25  # acceptance: >=25 (RSID, drug) entries
    assert sum(1 for e in gold if e.clinically_actionable) >= 1  # actionable present
    assert sum(1 for e in gold if not e.clinically_actionable) >= 2  # unremarkable path
    # one row per (rsid, drug)
    keys = [(e.rsid, e.drug) for e in gold]
    assert len(keys) == len(set(keys))
