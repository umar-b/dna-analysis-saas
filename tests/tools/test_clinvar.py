"""Tests for lookup_clinvar (ADR-0005). Pure, no LLM."""

from dna_analysis.models import ClinvarRecord
from dna_analysis.tools.clinvar import lookup_clinvar


def _recs():
    return [
        ClinvarRecord(
            rsid="rs397704705",
            clinical_significance="Pathogenic/Likely pathogenic",
            condition="Hereditary spastic paraplegia 48",
            review_status="criteria provided, multiple submitters, no conflicts",
        )
    ]


def test_lookup_clinvar_returns_record_with_citation_url():
    out = lookup_clinvar("rs397704705", _recs())
    assert out["clinical_significance"] == "Pathogenic/Likely pathogenic"
    assert out["condition"] == "Hereditary spastic paraplegia 48"
    assert out["review_status"].startswith("criteria provided")
    assert "rs397704705" in out["citation_url"]


def test_lookup_clinvar_absent_returns_empty():
    assert lookup_clinvar("rs999", _recs()) == {}
