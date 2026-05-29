"""End-to-end ETL CLI test against committed local fixture sources (issue #3).

`dna-analysis etl --out <dir> --from <dir>` reads pre-downloaded raw sources
(no network), runs the flatteners, and writes the three artifacts.
"""

import json
from pathlib import Path

from dna_analysis.cli import main

FIX = Path(__file__).parent / "fixtures"


def test_etl_writes_three_artifacts_from_local_sources(tmp_path, capsys):
    out = tmp_path / "out"
    rc = main(["etl", "--out", str(out), "--from", str(FIX)])
    assert rc == 0

    assert (out / "pgx_pairs.jsonl").exists()
    assert (out / "clinvar_records.jsonl").exists()
    assert (out / "name_allowlist.json").exists()

    pgx = [json.loads(ln) for ln in (out / "pgx_pairs.jsonl").read_text().splitlines()]
    assert any(r["rsid"] == "rs4244285" and r["drug"] == "clopidogrel" for r in pgx)

    allowlist = json.loads((out / "name_allowlist.json").read_text())
    assert "clopidogrel" in allowlist["drugs"]
    assert "CYP2C19" in allowlist["genes"]
