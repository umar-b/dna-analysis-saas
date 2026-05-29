"""23andMe genome ingest + RSID filter (ADR-0004).

RSID-only inner join against PharmGKB ∪ ClinVar (no liftover, no chr:pos
fallback in V1). i-codes and no-call genotypes are dropped and counted; the
drop diagnostics feed ADR-0004's escalation trigger.
"""

from __future__ import annotations

import pandas as pd

GENOME_COLUMNS = ["rsid", "chromosome", "position", "genotype"]


class GenomeParseError(ValueError):
    """A structurally malformed line in a 23andMe export (carries line number)."""


def parse(path) -> pd.DataFrame:
    """Parse a 23andMe export file into a DataFrame (rsid, chromosome, position, genotype)."""
    with open(path, encoding="utf-8") as handle:
        return parse_text(handle.read())


def parse_text(text: str) -> pd.DataFrame:
    """Parse 23andMe export text. Strips ``#`` comment lines; a data line that
    is not exactly four tab-separated fields raises GenomeParseError with its
    1-based line number."""
    rows = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 4:
            raise GenomeParseError(
                f"line {line_no}: expected 4 tab-separated fields, got {len(fields)}"
            )
        rows.append(fields)
    return pd.DataFrame(rows, columns=GENOME_COLUMNS)


def filter_genotype(genome_df: pd.DataFrame, pgx_pairs, clinvar_records):
    """RSID-only inner join against PharmGKB ∪ ClinVar (ADR-0004).

    Returns ``(filtered_df, diagnostics)``. ``diagnostics`` records the row
    accounting that feeds ADR-0004's escalation trigger.
    """
    reference_rsids = {p.rsid for p in pgx_pairs} | {c.rsid for c in clinvar_records}
    drop_reasons = {"no_rsid_match": 0, "i_code": 0, "malformed_row": 0}
    keep_index = []
    for idx, rsid, genotype in zip(
        genome_df.index, genome_df["rsid"], genome_df["genotype"]
    ):
        if rsid.startswith("i"):  # 23andMe proprietary i-code (ADR-0004)
            drop_reasons["i_code"] += 1
        elif not _is_valid_genotype(genotype):  # no-call / unusable
            drop_reasons["malformed_row"] += 1
        elif rsid in reference_rsids:
            keep_index.append(idx)
        else:
            drop_reasons["no_rsid_match"] += 1

    filtered = genome_df.loc[keep_index].reset_index(drop=True)
    diagnostics = {
        "total": int(len(genome_df)),
        "kept": int(len(filtered)),
        "dropped": int(len(genome_df) - len(filtered)),
        "drop_reasons": drop_reasons,
    }
    return filtered, diagnostics


_VALID_CALL_CHARS = set("ACGTID")


def _is_valid_genotype(genotype: str) -> bool:
    """A usable SNP/indel call: 1–2 chars, all in {A,C,G,T,I,D}. '--' etc. fail."""
    return (
        bool(genotype)
        and 1 <= len(genotype) <= 2
        and all(ch in _VALID_CALL_CHARS for ch in genotype)
    )
