"""Gold-set validation (issue #4, ADR-0001).

The gold set is the eval's ground truth, so it is checked mechanically before
it is trusted: every entry validates against GoldEntry (handled at load), every
rsid is present in the genome export (ADR-0004 — catch infrastructure misses
early), every drug/gene token is in the name allowlist, and the coverage mix
includes actionable + unremarkable entries (ADR-0003).
"""

from __future__ import annotations

from dna_analysis.models import GoldEntry, GoldValidation

MIN_ENTRIES = 25
MIN_UNREMARKABLE = 2


def read_genome_rsids(text: str) -> set[str]:
    """rsids present in a 23andMe-format export (tab: rsid, chr, pos, genotype)."""
    rsids: set[str] = set()
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        rsid = line.split("\t", 1)[0].strip()
        if rsid:
            rsids.add(rsid)
    return rsids


def validate_gold(
    gold: list[GoldEntry],
    genome_rsids: set[str],
    allowlist: set[str],
) -> GoldValidation:
    """Cross-check the gold set against the genome export and name allowlist."""
    missing = sorted({e.rsid for e in gold if e.rsid not in genome_rsids})
    allow_lower = {a.lower() for a in allowlist}
    out_of_allowlist: list[str] = []
    seen: set[str] = set()
    for entry in gold:
        for token in (entry.drug, entry.gene):
            key = token.lower()
            if key not in allow_lower and key not in seen:
                seen.add(key)
                out_of_allowlist.append(token)
    return GoldValidation(
        total=len(gold),
        missing_from_genome=missing,
        out_of_allowlist=out_of_allowlist,
        actionable_count=sum(1 for e in gold if e.clinically_actionable),
        unremarkable_count=sum(1 for e in gold if not e.clinically_actionable),
    )
