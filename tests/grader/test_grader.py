"""Behavioral tests for the hybrid grader (ADR-0001).

Tests exercise grade() through its public signature only. They describe what
the grader scores, not how it tokenizes.
"""

from importlib.resources import files

from dna_analysis.grader import grade
from dna_analysis.grader.loaders import parse_name_allowlist_json
from dna_analysis.models import (
    ActionableFindingProse,
    Finding,
    GoldEntry,
    NotGraded,
    ReportObject,
)


def make_gold(
    rsid="rs4244285",
    gene="CYP2C19",
    drug="clopidogrel",
    guideline_id="CPIC:CYP2C19:clopidogrel",
):
    return GoldEntry(
        rsid=rsid,
        gene=gene,
        drug=drug,
        guideline_id=guideline_id,
        evidence_level="A",
        clinically_actionable=True,
    )


def test_a_surfaced_when_rsid_appears_in_rendered_markdown():
    gold = [make_gold()]
    md = "Your variant rs4244285 in CYP2C19 affects clopidogrel response."
    result = grade(ReportObject(), md, gold, set())
    assert result.entries[0].rsid == "rs4244285"
    assert result.entries[0].surfaced is True


def test_a_not_surfaced_when_rsid_absent():
    gold = [make_gold(rsid="rs1799853")]
    md = "Your variant rs4244285 in CYP2C19 affects clopidogrel response."
    result = grade(ReportObject(), md, gold, set())
    assert result.entries[0].surfaced is False


def test_b_cited_when_guideline_id_in_report_object_citations():
    gold = [make_gold(guideline_id="CPIC:CYP2C19:clopidogrel")]
    report = ReportObject(
        actionable_findings=[
            ActionableFindingProse(
                gene="CYP2C19",
                diplotype_label="CYP2C19 *1/*2",
                recommendation_paragraph="Consider an alternative antiplatelet.",
                citation_id="CPIC:CYP2C19:clopidogrel",
            )
        ]
    )
    result = grade(report, "rs4244285", gold, set())
    assert result.entries[0].cited_guideline is True


def test_b_not_cited_when_guideline_id_missing():
    gold = [make_gold(guideline_id="CPIC:CYP2C19:clopidogrel")]
    report = ReportObject(
        actionable_findings=[
            ActionableFindingProse(
                gene="CYP2C19",
                diplotype_label="CYP2C19 *1/*2",
                recommendation_paragraph="Consider an alternative antiplatelet.",
                citation_id="CPIC:SLCO1B1:simvastatin",  # wrong guideline
            )
        ]
    )
    result = grade(report, "rs4244285", gold, set())
    assert result.entries[0].cited_guideline is False


def test_c_clean_report_has_no_hallucinations():
    gold = [make_gold()]
    allowlist = {"CYP2C19", "clopidogrel"}
    report = ReportObject(
        actionable_findings=[
            ActionableFindingProse(
                gene="CYP2C19",
                diplotype_label="CYP2C19 *1/*2",
                recommendation_paragraph="Consider an alternative antiplatelet.",
                citation_id="CPIC:CYP2C19:clopidogrel",
            )
        ]
    )
    md = "Variant rs4244285 in CYP2C19 reduces clopidogrel activation."
    result = grade(report, md, gold, allowlist)
    assert result.hallucination.out_of_vocabulary == []
    assert result.hallucination.passed is True


def test_c_flags_injected_gene_symbol_not_in_allowlist():
    gold = [make_gold()]
    allowlist = {"CYP2C19", "clopidogrel"}
    md = "Variant rs4244285 in CYP2C19 reduces clopidogrel; we recommend FAKEGENE9."
    result = grade(ReportObject(), md, gold, allowlist)
    assert "FAKEGENE9" in result.hallucination.out_of_vocabulary
    assert result.hallucination.passed is False


def test_c_flags_structured_drug_not_in_allowlist():
    gold = [make_gold()]
    allowlist = {"CYP2C19", "clopidogrel"}
    report = ReportObject(
        unremarkable_screen=[
            Finding(
                rsid="rs1799853",
                gene="CYP2C19",
                genotype="CC",
                drug="madeupazole",  # not in allowlist
                guideline_id="CPIC:CYP2C19:madeupazole",
                evidence_level="A",
                recommendation_gist="normal metabolizer",
                citation_url="https://example.org",
                clinically_actionable=False,
            )
        ]
    )
    result = grade(report, "rs4244285 CYP2C19 clopidogrel", gold, allowlist)
    assert "madeupazole" in result.hallucination.out_of_vocabulary
    assert result.hallucination.passed is False


def test_c_loads_name_allowlist_json_and_rejects_hallucination():
    # (c) now reads the ETL-produced name_allowlist.json (ADR-0013, issue #3)
    text = (files("dna_analysis.grader") / "fixtures" / "name_allowlist.json").read_text()
    allowlist = parse_name_allowlist_json(text)
    assert "clopidogrel" in allowlist and "CYP2C19" in allowlist
    md = "rs4244285 in CYP2C19 affects clopidogrel; we also recommend FAKEDRUG9."
    result = grade(ReportObject(), md, [make_gold()], allowlist)
    assert result.hallucination.passed is False
    assert "FAKEDRUG9" in result.hallucination.out_of_vocabulary


def test_d_is_not_graded_programmatically():
    result = grade(ReportObject(), "", [make_gold()], set())
    assert isinstance(result.medical_defensibility, NotGraded)


def test_aggregate_counts_across_entries():
    gold = [
        make_gold(rsid="rs4244285", guideline_id="g1"),
        make_gold(rsid="rs1799853", guideline_id="g2"),
    ]
    report = ReportObject(
        actionable_findings=[
            ActionableFindingProse(
                gene="CYP2C19",
                diplotype_label="x",
                recommendation_paragraph="y",
                citation_id="g1",
            )
        ]
    )
    # md surfaces only the first rsid; only g1 cited.
    result = grade(report, "rs4244285 present", gold, {"CYP2C19"})
    assert result.total == 2
    assert result.surfaced_count == 1
    assert result.cited_count == 1
