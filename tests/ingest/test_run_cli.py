"""End-to-end `dna-analysis run` CLI test (issue #5). Synthetic inputs only."""

import json

import pandas as pd

from dna_analysis.cli import main
from dna_analysis.models import PgxPair


def _etl_dir(tmp_path):
    etl = tmp_path / "etl"
    etl.mkdir()
    pgx = PgxPair(
        rsid="rs4244285",
        gene="CYP2C19",
        drug="clopidogrel",
        guideline_id="PA166251443",
        evidence_level="A",
    )
    (etl / "pgx_pairs.jsonl").write_text(json.dumps(pgx.model_dump()) + "\n")
    (etl / "clinvar_records.jsonl").write_text("")
    return etl


def test_run_writes_filtered_parquet_and_diagnostics(tmp_path):
    etl = _etl_dir(tmp_path)
    genome = tmp_path / "genome.txt"
    genome.write_text(
        "# header\nrs4244285\t10\t96541616\tGG\nrs9999999\t1\t100\tAA\n"
    )
    out = tmp_path / "out"
    rc = main(["run", "--genome", str(genome), "--etl-dir", str(etl), "--out", str(out)])
    assert rc == 0
    assert (out / "filtered_genotype.parquet").exists()
    diag = json.loads((out / "filter_diagnostics.json").read_text())
    assert diag["kept"] == 1 and diag["total"] == 2
    df = pd.read_parquet(out / "filtered_genotype.parquet")
    assert list(df["rsid"]) == ["rs4244285"]


def test_run_returns_nonzero_on_missing_genome(tmp_path):
    etl = _etl_dir(tmp_path)
    rc = main(
        ["run", "--genome", str(tmp_path / "nope.txt"), "--etl-dir", str(etl), "--out", str(tmp_path / "o")]
    )
    assert rc != 0
