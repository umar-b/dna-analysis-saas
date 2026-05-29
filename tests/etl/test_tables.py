"""Tests for ETL table writing (ADR-0013): idempotent jsonl + json output."""

import json
from pathlib import Path

from dna_analysis.etl.flatten import (
    build_name_allowlist,
    build_pgx_pairs,
    flatten_clinvar,
)
from dna_analysis.etl.tables import write_tables

FIX = Path(__file__).parent / "fixtures"


def _inputs():
    cpic = lambda n: json.loads((FIX / "cpic" / f"{n}.json").read_text())
    pgx = build_pgx_pairs(
        cpic("sequence_location"),
        cpic("pairs"),
        cpic("recommendation"),
        cpic("diplotype"),
    )
    clinvar = flatten_clinvar(
        (FIX / "clinvar" / "variant_summary_excerpt.tsv").read_text()
    )
    allow = build_name_allowlist(pgx, clinvar, clinvar_genes={"AP5Z1"})
    return pgx, clinvar, allow


def test_write_tables_is_idempotent(tmp_path):
    pgx, clinvar, allow = _inputs()
    out = tmp_path / "etl"
    write_tables(out, pgx, clinvar, allow)
    first = (out / "pgx_pairs.jsonl").read_bytes(), (out / "name_allowlist.json").read_bytes()
    # re-run into the same dir
    write_tables(out, pgx, clinvar, allow)
    second = (out / "pgx_pairs.jsonl").read_bytes(), (out / "name_allowlist.json").read_bytes()
    assert first == second


def test_write_tables_artifacts_are_wellformed(tmp_path):
    pgx, clinvar, allow = _inputs()
    out = tmp_path / "etl"
    write_tables(out, pgx, clinvar, allow)
    # jsonl: one parseable object per line, round-trips to a PgxPair shape
    lines = (out / "pgx_pairs.jsonl").read_text().splitlines()
    rows = [json.loads(ln) for ln in lines]
    assert any(r["rsid"] == "rs4244285" and r["drug"] == "clopidogrel" for r in rows)
    # allowlist json
    al = json.loads((out / "name_allowlist.json").read_text())
    assert "clopidogrel" in al["drugs"] and "CYP2C19" in al["genes"]
