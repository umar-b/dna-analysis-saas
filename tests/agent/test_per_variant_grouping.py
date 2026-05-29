"""Pure tests for same-gene grouping (ADR-0008). No LLM."""

from dna_analysis.agent.per_variant import build_same_gene_context, rsid_to_gene
from dna_analysis.ingest.genome import parse_text
from dna_analysis.models import PgxPair


def _filtered():
    return parse_text(
        "rs4244285\t10\t96541616\tGG\n"
        "rs12248560\t10\t96521657\tCC\n"
        "rs1799853\t10\t96702047\tCC\n"
    )


def test_same_gene_context_lists_neighbours_excluding_focal():
    gene_of = {
        "rs4244285": "CYP2C19",
        "rs12248560": "CYP2C19",
        "rs1799853": "CYP2C9",
    }
    ctx = build_same_gene_context(_filtered(), gene_of)
    assert ctx["rs4244285"] == [("rs12248560", "CC")]
    assert ctx["rs12248560"] == [("rs4244285", "GG")]
    assert ctx["rs1799853"] == []  # only CYP2C9 variant


def test_rsid_to_gene_from_pgx_pairs():
    pairs = [
        PgxPair(rsid="rs4244285", gene="CYP2C19", drug="clopidogrel",
                guideline_id="PA1", evidence_level="A"),
    ]
    assert rsid_to_gene(pairs) == {"rs4244285": "CYP2C19"}
