"""Hybrid grader (ADR-0001).

Pure function: no I/O, no network. The caller loads gold entries, the rendered
report, the report object, and the name allowlist, then passes them in.
"""

from __future__ import annotations

import re

from dna_analysis.models import (
    EntryGrade,
    GoldEntry,
    GradeResult,
    HallucinationCheck,
    ReportObject,
)

# Gene-symbol-shaped tokens have a clean lexical signature in prose: an
# uppercase run with at least one digit or three uppercase letters
# (CYP2C19, VKORC1, SLCO1B1, MTHFR, TPMT, DPYD, UGT1A1). This is the one
# entity class we can extract from free markdown with a low false-positive
# rate. Drug/condition names in free prose cannot be lexically tagged
# without NLP, so those are checked from structured ReportObject fields
# instead. V1 hallucination check is coarse by design (ADR-0001); later
# slices refine closed-vocabulary enforcement.
_GENE_SYMBOL = re.compile(r"\b[A-Z][A-Z0-9]{2,}\b")

# Structural/domain acronyms that share the gene-symbol lexical shape but are
# report scaffolding or vocabulary, not entity names — excluded from the (c)
# check so the report template and disclaimer don't read as hallucinations.
_STRUCTURAL_TOKENS = {
    "DNA", "RSID", "PGP", "CPIC", "PGX", "PMID", "URL", "HRV", "RHR", "ID", "NSAID",
}


def _out_of_vocabulary(
    report_object: ReportObject,
    rendered_report_md: str,
    name_allowlist: set[str],
) -> list[str]:
    allow_lower = {name.lower() for name in name_allowlist} | {
        t.lower() for t in _STRUCTURAL_TOKENS
    }
    candidates: list[str] = []

    # Gene-symbol-shaped tokens in the rendered markdown.
    candidates.extend(_GENE_SYMBOL.findall(rendered_report_md))

    # Drug/gene names the report designates structurally.
    for finding in report_object.actionable_findings:
        candidates.append(finding.gene)
    for finding in report_object.unremarkable_screen:
        candidates.append(finding.gene)
        candidates.append(finding.drug)

    # Any candidate outside the allowlist is a hallucination, deduped on
    # first appearance (case-insensitive) preserving original casing.
    out: list[str] = []
    seen: set[str] = set()
    for token in candidates:
        if not token:
            continue
        key = token.lower()
        if key in allow_lower or key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


def grade(
    report_object: ReportObject,
    rendered_report_md: str,
    gold: list[GoldEntry],
    name_allowlist: set[str],
) -> GradeResult:
    # (b) reads citation IDs straight from the report object's JSON fields
    # (ADR-0009), not from the rendered markdown.
    cited_ids = {f.citation_id for f in report_object.actionable_findings}

    entries = []
    for entry in gold:
        # (a) did the report surface the variant? substring match on RSID.
        surfaced = entry.rsid in rendered_report_md
        # (b) did it cite the right PGx guideline?
        cited_guideline = entry.guideline_id in cited_ids
        entries.append(
            EntryGrade(
                rsid=entry.rsid,
                drug=entry.drug,
                surfaced=surfaced,
                cited_guideline=cited_guideline,
            )
        )
    # (c) hallucination check — report-level, zero-tolerance (ADR-0001).
    hallucination = HallucinationCheck(
        out_of_vocabulary=_out_of_vocabulary(
            report_object, rendered_report_md, name_allowlist
        )
    )

    return GradeResult(entries=entries, hallucination=hallucination)
