"""lookup_pharmgkb_pgx tool (ADR-0005). Pure: structured returns over pgx_pairs.

The per-variant agent call invokes this with an rsid, gene, or drug; it returns
the matching PGx records so the model copies fields (guideline_id, citation_url)
rather than inventing them.
"""

from __future__ import annotations

from dna_analysis.models import PgxPair


# Compact fields only. recommendation_text and phenotype_table are large
# nested dicts (phenotype/diplotype maps) and are duplicated across every record
# for a gene — returning them blows past the context window. They are omitted
# from the tool surface; the model writes recommendation_gist itself and infers
# the phenotype from the focal genotype + same-gene context.
_FIELDS = (
    "rsid",
    "gene",
    "drug",
    "guideline_id",
    "evidence_level",
    "citation_url",
)


def lookup_pharmgkb_pgx(query: str, pgx_pairs: list[PgxPair]) -> list[dict]:
    """Return PGx records matching ``query`` on rsid, gene, or drug (case-insensitive)."""
    q = query.strip().lower()
    return [
        {f: getattr(pair, f) for f in _FIELDS}
        for pair in pgx_pairs
        if q in (pair.rsid.lower(), pair.gene.lower(), pair.drug.lower())
    ]
