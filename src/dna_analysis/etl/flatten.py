"""Pure flatteners: raw CPIC/ClinVar payloads -> typed table rows.

No I/O, no network. Callers fetch the bytes and pass them in.
"""

from __future__ import annotations

import csv
import io

from dna_analysis.models import ClinvarRecord, NameAllowlist, PgxPair


def flatten_clinvar(tsv_text: str) -> list[ClinvarRecord]:
    """ClinVar variant_summary.txt -> ClinvarRecord rows (ADR-0013).

    Columns are looked up by name (header tolerates reordering). Rows whose
    ``RS# (dbSNP)`` is -1 carry no rsid and are dropped.
    """
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    records: list[ClinvarRecord] = []
    for row in reader:
        rs = (row.get("RS# (dbSNP)") or "").strip()
        if not rs or rs == "-1":
            continue
        records.append(
            ClinvarRecord(
                rsid=f"rs{rs}",
                clinical_significance=row.get("ClinicalSignificance", "").strip(),
                condition=row.get("PhenotypeList", "").strip(),
                review_status=row.get("ReviewStatus", "").strip(),
            )
        )
    return records


def clinvar_gene_symbols(tsv_text: str) -> set[str]:
    """Gene symbols from ClinVar (for the allowlist's gene union, ADR-0013)."""
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    return {
        (row.get("GeneSymbol") or "").strip()
        for row in reader
        if (row.get("GeneSymbol") or "").strip()
    }


def build_pgx_pairs(
    sequence_location: list[dict],
    pairs: list[dict],
    recommendation: list[dict],
    diplotype: list[dict],
) -> list[PgxPair]:
    """Cross-product CPIC rsids × CPIC drug pairs per gene (ADR-0013).

    One row per (rsid, drug): rsid spine from ``sequence_location``, CPIC
    level / guideline from ``pair``.
    """
    # gene -> ordered unique rsids
    gene_rsids: dict[str, list[str]] = {}
    for loc in sequence_location:
        rs = (loc.get("dbsnpid") or "").strip()
        gene = (loc.get("genesymbol") or "").strip()
        if rs and gene and rs not in gene_rsids.setdefault(gene, []):
            gene_rsids[gene].append(rs)

    # gene -> {diplotype: phenotype}
    gene_phenotypes: dict[str, dict[str, str]] = {}
    for dip in diplotype:
        gene = (dip.get("genesymbol") or "").strip()
        diplo = dip.get("diplotype")
        result = dip.get("generesult")
        if gene and diplo and result:
            gene_phenotypes.setdefault(gene, {})[diplo] = result

    out: list[PgxPair] = []
    for pair in pairs:
        gene = pair["genesymbol"]
        drug = pair["drug"]["name"]
        guideline = pair.get("guideline") or {}
        rec_map = _recommendation_map(
            recommendation, pair.get("guidelineid"), pair.get("drugid"), gene
        )
        for rsid in gene_rsids.get(gene, []):
            out.append(
                PgxPair(
                    rsid=rsid,
                    gene=gene,
                    drug=drug,
                    guideline_id=guideline.get("clinpgxid", ""),
                    evidence_level=pair.get("cpiclevel", ""),
                    recommendation_text=rec_map,
                    citation_url=guideline.get("url", ""),
                    phenotype_table=gene_phenotypes.get(gene, {}),
                )
            )
    return out


def _recommendation_map(
    recommendation: list[dict], guidelineid, drugid, gene: str
) -> dict[str, str]:
    """Phenotype -> CPIC drug recommendation for one (guideline, drug, gene)."""
    out: dict[str, str] = {}
    for rec in recommendation:
        if rec.get("guidelineid") != guidelineid or rec.get("drugid") != drugid:
            continue
        phenotype = (rec.get("phenotypes") or {}).get(gene)
        text = rec.get("drugrecommendation")
        if phenotype and text:
            out[phenotype] = text
    return out


def _sorted_unique(values) -> list[str]:
    return sorted({v.strip() for v in values if v and v.strip()})


def build_name_allowlist(
    pgx_pairs: list[PgxPair],
    clinvar_records: list[ClinvarRecord],
    clinvar_genes: set[str],
) -> NameAllowlist:
    """Derive the closed vocabulary from the ETL tables (ADR-0001, ADR-0013).

    Conditions split on ``;`` and ``|`` (ClinVar PhenotypeList delimiters).
    """
    drugs = _sorted_unique(p.drug for p in pgx_pairs)
    genes = _sorted_unique(
        [p.gene for p in pgx_pairs] + list(clinvar_genes)
    )
    conditions: list[str] = []
    for record in clinvar_records:
        for part in record.condition.replace("|", ";").split(";"):
            conditions.append(part)
    return NameAllowlist(
        drugs=drugs,
        genes=genes,
        conditions=_sorted_unique(conditions),
    )
