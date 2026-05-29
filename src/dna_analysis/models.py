"""Shared Pydantic types — the contract every later slice imports from.

These are pure data models. Importing this module performs no I/O and makes
no network calls. ADR references are load-bearing: each type encodes a
documented decision and changing its shape means revisiting that ADR.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EvidenceLevel = Literal["A", "B", "C", "D"]
LabFlag = Literal["high", "low", "normal"]


class Finding(BaseModel):
    """One per-variant Claude call's structured output (ADR-0003).

    Granularity is one finding per (RSID, drug) pair — matches gold-entry
    granularity and how CPIC publishes guidelines. Medical-context-aware
    field set: ``evidence_level`` and ``genotype`` let the synthesis pass
    write defensible prose; ``citation_url`` supports inline citation.

    ``same_gene_context`` carries every other filtered RSID in the same gene
    (ADR-0008) so diplotype-level reasoning is auditable: CPIC phenotypes are
    diplotype-level, not variant-level, so a per-variant call must see its
    same-gene neighbours to interpret the focal pair correctly.
    """

    rsid: str
    gene: str
    genotype: str
    drug: str
    guideline_id: str
    evidence_level: EvidenceLevel
    recommendation_gist: str
    citation_url: str
    clinically_actionable: bool
    same_gene_context: list[tuple[str, str]] = Field(default_factory=list)


class ActionableFindingProse(BaseModel):
    """A rendered actionable finding inside the report object (ADR-0009).

    ``citation_id`` is copied verbatim from tool output and is what the
    grader's (b) check reads directly from JSON instead of regex-searching
    rendered markdown.
    """

    gene: str
    diplotype_label: str
    recommendation_paragraph: str
    citation_id: str
    related_finding_rsids: list[str] = Field(default_factory=list)


class ObservationProse(BaseModel):
    """A lifestyle or lab observation paragraph in the report object (ADR-0009).

    ``related_refs`` cross-references the structured source (a finding RSID, a
    Whoop metric name, or a lab test name) the observation draws on.
    """

    observation_paragraph: str
    related_refs: list[str] = Field(default_factory=list)


class ReportObject(BaseModel):
    """Typed intermediate the synthesis call returns; Jinja renders it (ADR-0009).

    A single Claude call produces this object seeing all findings + labs +
    Whoop summary at once, preserving cross-section reasoning. The template
    renders a fixed section order so the grader's regex/JSON reads stay stable
    across eval iterations. ``unremarkable_screen`` is passed straight through
    from the findings dict and rendered as a deterministic appendix table.
    """

    actionable_findings: list[ActionableFindingProse] = Field(default_factory=list)
    lifestyle_observations: list[ObservationProse] = Field(default_factory=list)
    lab_observations: list[ObservationProse] = Field(default_factory=list)
    unremarkable_screen: list[Finding] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class LabRecord(BaseModel):
    """One lab value extracted from a PDF via Claude vision (ADR-0007).

    ``value`` is a string, not a float, on purpose: ADR-0007's verbatim rule
    requires lab values quoted in the report to match these strings exactly,
    with no rounding or paraphrasing, so the manual (d) read can spot-check
    against the source PDF.
    """

    test: str
    value: str
    unit: str
    reference_range: str
    date: str
    flag: LabFlag


class GoldEntry(BaseModel):
    """One row in ``gold.yaml`` — the expected finding for a (RSID, drug) pair.

    Mirrors the gradable fields of :class:`Finding` (ADR-0003) so the grader
    can compare fields directly. Granularity is (RSID, drug), not per-RSID,
    matching CPIC guideline publication and finding granularity.
    """

    rsid: str
    gene: str
    drug: str
    guideline_id: str
    evidence_level: EvidenceLevel
    clinically_actionable: bool


class PgxPair(BaseModel):
    """One ETL-flattened PGx table row (ADR-0005, ADR-0013).

    Sourced from the CPIC API, keyed by (rsid, drug) — the per-variant agent
    loop looks up by rsid and `Finding` granularity is per-(RSID, drug).
    ``evidence_level`` is the CPIC level (A–D) carried verbatim; kept as a
    plain string rather than the strict A–D literal so the full-catalogue ETL
    does not crash on CPIC's occasional composite levels.
    ``recommendation_text`` is a phenotype → recommendation map and
    ``phenotype_table`` a diplotype → phenotype map (ADR-0013).
    """

    rsid: str
    gene: str
    drug: str
    guideline_id: str  # CPIC guideline accession (clinpgxid, e.g. "PA166251443")
    evidence_level: str  # CPIC level, e.g. "A"
    recommendation_text: dict[str, str] = Field(default_factory=dict)
    citation_url: str = ""
    phenotype_table: dict[str, str] = Field(default_factory=dict)


class ClinvarRecord(BaseModel):
    """One ETL-flattened ClinVar table row (ADR-0005, ADR-0013).

    From ClinVar ``variant_summary.txt``: ``RS# (dbSNP)`` → rsid (rows with
    ``RS# = -1`` are dropped — no rsid), ``ClinicalSignificance``,
    ``PhenotypeList`` → condition, ``ReviewStatus``.
    """

    rsid: str
    clinical_significance: str
    condition: str
    review_status: str


class NameAllowlist(BaseModel):
    """Closed vocabulary derived from the ETL tables (ADR-0001, ADR-0005).

    drugs ← ``pgx_pairs.drug``; genes ← ``pgx_pairs.gene`` ∪ ClinVar gene
    symbols; conditions ← ``clinvar_records.condition``. The grader's (c)
    hallucination check loads this; anything outside it is a hallucination.
    """

    drugs: list[str] = Field(default_factory=list)
    genes: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)

    def as_set(self) -> set[str]:
        """Flatten to the single token set the grader's (c) check consumes."""
        return set(self.drugs) | set(self.genes) | set(self.conditions)


class GoldValidation(BaseModel):
    """Mechanical pre-trust check on the gold set (issue #4, ADR-0001)."""

    total: int
    missing_from_genome: list[str] = Field(default_factory=list)  # rsids not in export
    out_of_allowlist: list[str] = Field(default_factory=list)  # drug/gene not allowed
    actionable_count: int = 0
    unremarkable_count: int = 0

    @property
    def meets_minimum(self) -> bool:
        return self.total >= 25

    @property
    def has_coverage_mix(self) -> bool:
        return self.actionable_count >= 1 and self.unremarkable_count >= 2

    @property
    def ok(self) -> bool:
        return (
            not self.missing_from_genome
            and not self.out_of_allowlist
            and self.meets_minimum
            and self.has_coverage_mix
        )


class NotGraded(BaseModel):
    """Sentinel for metric (d) — medical defensibility (ADR-0001).

    (d) is graded by a human reading ``report.md``; the programmatic grader
    never scores it and returns this instead.
    """

    reason: str = "Metric (d), medical defensibility, is graded manually (ADR-0001)."


class EntryGrade(BaseModel):
    """Per-entry programmatic result for metrics (a) and (b)."""

    rsid: str
    drug: str
    surfaced: bool  # (a) RSID appears in rendered markdown
    cited_guideline: bool  # (b) gold guideline_id appears in report object citations


class HallucinationCheck(BaseModel):
    """Report-level result for metric (c) — zero-tolerance (ADR-0001).

    ``out_of_vocabulary`` lists entity tokens found in the report that are not
    in the name allowlist. Any non-empty list is a fatal hallucination.
    """

    out_of_vocabulary: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.out_of_vocabulary


class GradeResult(BaseModel):
    """Aggregate grader output (ADR-0001): (a)(b) per-entry, (c) report-level, (d) manual."""

    entries: list[EntryGrade] = Field(default_factory=list)
    hallucination: HallucinationCheck = Field(default_factory=HallucinationCheck)
    medical_defensibility: NotGraded = Field(default_factory=NotGraded)

    @property
    def surfaced_count(self) -> int:
        return sum(1 for e in self.entries if e.surfaced)

    @property
    def cited_count(self) -> int:
        return sum(1 for e in self.entries if e.cited_guideline)

    @property
    def total(self) -> int:
        return len(self.entries)
