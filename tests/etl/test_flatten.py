"""Behavioral tests for the ETL flatteners (ADR-0005, ADR-0013).

Exercised against committed real excerpts of the CPIC API + ClinVar dump.
"""

import json
from pathlib import Path

from dna_analysis.etl.flatten import (
    build_name_allowlist,
    build_pgx_pairs,
    flatten_clinvar,
)

FIX = Path(__file__).parent / "fixtures"


def _clinvar_tsv() -> str:
    return (FIX / "clinvar" / "variant_summary_excerpt.tsv").read_text()


def _cpic(name: str) -> list[dict]:
    return json.loads((FIX / "cpic" / f"{name}.json").read_text())


def _pgx_pairs():
    return build_pgx_pairs(
        _cpic("sequence_location"),
        _cpic("pairs"),
        _cpic("recommendation"),
        _cpic("diplotype"),
    )


def test_flatten_clinvar_maps_rsid_and_significance():
    records = flatten_clinvar(_clinvar_tsv())
    by_rsid = {r.rsid: r for r in records}
    assert "rs397704705" in by_rsid
    rec = by_rsid["rs397704705"]
    assert rec.clinical_significance == "Pathogenic/Likely pathogenic"
    assert "Hereditary spastic paraplegia 48" in rec.condition
    assert rec.review_status.startswith("criteria provided")


def test_flatten_clinvar_drops_rows_without_rsid():
    records = flatten_clinvar(_clinvar_tsv())
    # the fixture contains one RS# = -1 row (PHARC syndrome); it must be dropped
    assert all(r.rsid != "rs-1" for r in records)
    assert all("PHARC" not in r.condition for r in records)
    assert all(r.rsid.startswith("rs") and r.rsid[2:].isdigit() for r in records)


def test_build_pgx_pairs_surfaces_cyp2c19_clopidogrel():
    pairs = _pgx_pairs()
    row = next(
        p
        for p in pairs
        if p.rsid == "rs4244285" and p.drug == "clopidogrel"
    )
    assert row.gene == "CYP2C19"
    assert row.evidence_level == "A"
    assert row.guideline_id == "PA166251443"
    assert row.citation_url == "https://www.clinpgx.org/guideline/PA166251443"


def test_build_pgx_pairs_surfaces_cyp2c9_warfarin():
    pairs = _pgx_pairs()
    row = next(
        p for p in pairs if p.rsid == "rs1799853" and p.drug == "warfarin"
    )
    assert row.gene == "CYP2C9"
    assert row.evidence_level == "A"
    assert row.guideline_id == "PA166251465"


def test_pgx_pair_carries_phenotype_recommendation_map():
    row = next(
        p for p in _pgx_pairs() if p.rsid == "rs4244285" and p.drug == "clopidogrel"
    )
    # recommendation_text is phenotype -> CPIC drug recommendation
    assert row.recommendation_text["Rapid Metabolizer"] == (
        "If considering clopidogrel, use at standard dose (75 mg/day)"
    )


def test_pgx_pair_carries_diplotype_phenotype_table():
    row = next(
        p for p in _pgx_pairs() if p.rsid == "rs4244285" and p.drug == "clopidogrel"
    )
    # phenotype_table is diplotype -> phenotype (gene-level), from CPIC diplotype
    assert row.phenotype_table["*10/*22"] == "Likely Poor Metabolizer"


def test_build_name_allowlist_unions_drugs_genes_conditions():
    pgx = _pgx_pairs()
    clinvar = flatten_clinvar(_clinvar_tsv())
    allowlist = build_name_allowlist(pgx, clinvar, clinvar_genes={"AP5Z1"})
    # drugs from pgx_pairs.drug
    assert "clopidogrel" in allowlist.drugs
    assert "warfarin" in allowlist.drugs
    # genes from pgx_pairs.gene ∪ clinvar genes
    assert "CYP2C19" in allowlist.genes
    assert "AP5Z1" in allowlist.genes
    # conditions from clinvar_records.condition (split on ; and |)
    assert "Hereditary spastic paraplegia 48" in allowlist.conditions
    # deduped
    assert len(allowlist.drugs) == len(set(allowlist.drugs))
