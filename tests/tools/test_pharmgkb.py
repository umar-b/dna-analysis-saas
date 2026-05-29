"""Tests for the lookup_pharmgkb_pgx tool (ADR-0005). Pure, no LLM."""

from dna_analysis.models import PgxPair
from dna_analysis.tools.pharmgkb import lookup_pharmgkb_pgx


def _pairs():
    return [
        PgxPair(rsid="rs4244285", gene="CYP2C19", drug="clopidogrel",
                guideline_id="PA166251443", evidence_level="A",
                citation_url="https://clinpgx.org/g/PA166251443"),
        PgxPair(rsid="rs4244285", gene="CYP2C19", drug="voriconazole",
                guideline_id="PA166251456", evidence_level="A"),
        PgxPair(rsid="rs1799853", gene="CYP2C9", drug="warfarin",
                guideline_id="PA166251465", evidence_level="A"),
    ]


def test_lookup_by_rsid_returns_all_drug_pairs():
    out = lookup_pharmgkb_pgx("rs4244285", _pairs())
    drugs = {r["drug"] for r in out}
    assert drugs == {"clopidogrel", "voriconazole"}
    rec = next(r for r in out if r["drug"] == "clopidogrel")
    assert rec["gene"] == "CYP2C19"
    assert rec["guideline_id"] == "PA166251443"
    assert rec["citation_url"] == "https://clinpgx.org/g/PA166251443"


def test_lookup_by_gene_and_by_drug():
    assert {r["drug"] for r in lookup_pharmgkb_pgx("CYP2C19", _pairs())} == {
        "clopidogrel",
        "voriconazole",
    }
    assert [r["rsid"] for r in lookup_pharmgkb_pgx("warfarin", _pairs())] == ["rs1799853"]
    assert lookup_pharmgkb_pgx("nonexistent", _pairs()) == []
