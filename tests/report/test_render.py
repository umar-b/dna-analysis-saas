"""Tests for report rendering (ADR-0009, ADR-0011). Pure, no LLM."""

from dna_analysis.report import DISCLAIMER, render
from dna_analysis.models import (
    ActionableFindingProse,
    Finding,
    ObservationProse,
    ReportObject,
)


def _report():
    return ReportObject(
        actionable_findings=[
            ActionableFindingProse(
                gene="SLCO1B1",
                diplotype_label="SLCO1B1 *1/*5",
                recommendation_paragraph="Decreased function; consider a lower simvastatin dose.",
                citation_id="PA166264281",
                related_finding_rsids=["rs4149056"],
            )
        ],
        lifestyle_observations=[ObservationProse(observation_paragraph="Lifestyle note.")],
        lab_observations=[ObservationProse(observation_paragraph="Lab note.")],
        unremarkable_screen=[
            Finding(
                rsid="rs4244285",
                gene="CYP2C19",
                genotype="GG",
                drug="clopidogrel",
                guideline_id="PA166251443",
                evidence_level="A",
                recommendation_gist="Normal metabolizer; standard dosing.",
                clinically_actionable=False,
            )
        ],
        caveats=["Cross-gene interactions not assessed."],
    )


def test_render_follows_fixed_section_order():
    md = render(_report())
    order = [
        md.index("## Actionable findings"),
        md.index("## Lifestyle observations"),
        md.index("## Lab observations"),
        md.index("## Caveats"),
        md.index("## Screened, unremarkable"),
    ]
    assert order == sorted(order)


def test_unremarkable_renders_as_table_row_per_finding():
    md = render(_report())
    assert "| RSID | Gene | Drug | Note |" in md
    assert "| rs4244285 | CYP2C19 | clopidogrel | Normal metabolizer; standard dosing. |" in md


def test_disclaimer_footer_present():
    md = render(_report())
    assert DISCLAIMER in md
    assert "not medical advice" in md
