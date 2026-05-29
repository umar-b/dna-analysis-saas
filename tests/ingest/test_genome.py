"""Tests for genome ingest + RSID filter (issue #5, ADR-0004).

Synthetic fixture rows only — never the PGP file.
"""

import pytest

from dna_analysis.ingest.genome import (
    GenomeParseError,
    filter_genotype,
    parse_text,
)
from dna_analysis.models import ClinvarRecord, PgxPair


def _pgx(rsid, gene="CYP2C19", drug="clopidogrel"):
    return PgxPair(
        rsid=rsid, gene=gene, drug=drug, guideline_id="PA1", evidence_level="A"
    )


def _genome(rows):
    return parse_text("\n".join("\t".join(r) for r in rows) + "\n")


def test_parse_strips_comments_and_returns_columns():
    text = (
        "# this is a 23andMe header comment\n"
        "#\n"
        "rs4244285\t10\t96541616\tGG\n"
        "rs1799853\t10\t96702047\tCC\n"
    )
    df = parse_text(text)
    assert list(df.columns) == ["rsid", "chromosome", "position", "genotype"]
    assert len(df) == 2
    assert df.iloc[0]["rsid"] == "rs4244285"
    assert df.iloc[0]["genotype"] == "GG"


def test_parse_rejects_malformed_line_with_line_number():
    text = (
        "# header\n"
        "rs4244285\t10\t96541616\tGG\n"
        "rs1799853\t10\t96702047\n"  # only 3 fields — malformed (line 3)
    )
    with pytest.raises(GenomeParseError) as exc:
        parse_text(text)
    assert "line 3" in str(exc.value)


def test_filter_keeps_only_rsids_in_reference_union():
    genome = _genome(
        [
            ["rs4244285", "10", "96541616", "GG"],  # in pgx -> kept
            ["rs9999999", "1", "100", "AA"],  # not in refs -> dropped
        ]
    )
    filtered, diag = filter_genotype(
        genome, pgx_pairs=[_pgx("rs4244285")], clinvar_records=[]
    )
    assert list(filtered["rsid"]) == ["rs4244285"]
    assert diag["total"] == 2
    assert diag["kept"] == 1
    assert diag["dropped"] == 1


def test_filter_union_includes_clinvar():
    genome = _genome([["rs397704705", "1", "100", "AG"]])
    filtered, diag = filter_genotype(
        genome,
        pgx_pairs=[],
        clinvar_records=[
            ClinvarRecord(
                rsid="rs397704705",
                clinical_significance="Pathogenic",
                condition="x",
                review_status="y",
            )
        ],
    )
    assert diag["kept"] == 1


def test_filter_classifies_drop_reasons():
    genome = _genome(
        [
            ["rs4244285", "10", "96541616", "GG"],  # kept (in refs)
            ["i3002735", "1", "200", "AA"],  # i-code -> dropped silently
            ["rs1801159", "1", "300", "--"],  # no-call genotype -> malformed_row
            ["rs9999999", "1", "400", "AA"],  # valid but not in refs -> no_rsid_match
        ]
    )
    filtered, diag = filter_genotype(
        genome, pgx_pairs=[_pgx("rs4244285"), _pgx("rs1801159")], clinvar_records=[]
    )
    assert list(filtered["rsid"]) == ["rs4244285"]
    assert diag["total"] == 4
    assert diag["kept"] == 1
    assert diag["dropped"] == 3
    assert diag["drop_reasons"] == {
        "i_code": 1,
        "malformed_row": 1,
        "no_rsid_match": 1,
    }
