"""lookup_clinvar tool (ADR-0005). Pure: structured returns over clinvar_records.

ClinvarRecord stores no URL, so the citation is derived deterministically from
the rsid (a stable ClinVar query link) for the report's inline citation.
"""

from __future__ import annotations

from dna_analysis.models import ClinvarRecord


def lookup_clinvar(rsid: str, clinvar_records: list[ClinvarRecord]) -> dict:
    """Return the ClinVar record for ``rsid`` (empty dict if absent)."""
    q = rsid.strip().lower()
    for record in clinvar_records:
        if record.rsid.lower() == q:
            return {
                "rsid": record.rsid,
                "clinical_significance": record.clinical_significance,
                "condition": record.condition,
                "review_status": record.review_status,
                "citation_url": f"https://www.ncbi.nlm.nih.gov/clinvar/?term={record.rsid}",
            }
    return {}
