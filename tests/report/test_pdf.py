"""Tests for the human-readable PDF report (ADR-0009/0011 output format).

Pure, no LLM: renders a ReportObject to PDF bytes and reads the result back
with pymupdf (already a dep) to assert on observable structure — a plain-
language first page and a technical detail section at the end.
"""

import re

import fitz  # pymupdf

from dna_analysis.models import (
    ActionableFindingProse,
    Finding,
    ObservationProse,
    ReportObject,
)
from dna_analysis.report import render_pdf
from dna_analysis.report.render import DISCLAIMER


def _report():
    return ReportObject(
        actionable_findings=[
            ActionableFindingProse(
                gene="SLCO1B1",
                diplotype_label="SLCO1B1 *1/*5",
                recommendation_paragraph=(
                    "This patient carries a decreased-function SLCO1B1 transporter; "
                    "consider a lower simvastatin dose or an alternative statin with "
                    "creatine kinase monitoring."
                ),
                citation_id="PA166264281",
                related_finding_rsids=["rs4149056"],
            ),
            ActionableFindingProse(
                gene="TPMT",
                diplotype_label="TPMT *2/*2",
                recommendation_paragraph=(
                    "Poor metabolizer; drastically reduce azathioprine and "
                    "mercaptopurine dosing or choose an alternative agent."
                ),
                citation_id="PA166251442",
                related_finding_rsids=["rs1800462"],
            ),
        ],
        lifestyle_observations=[
            ObservationProse(observation_paragraph="Average sleep was only 6.2 hours.")
        ],
        lab_observations=[
            ObservationProse(observation_paragraph="Vitamin D was 20 ng/ml (low).")
        ],
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


def _pages_text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return [page.get_text() for page in doc]


def _norm(text):
    # PDF layout wraps paragraphs, so collapse whitespace before substring checks.
    return re.sub(r"\s+", " ", text)


def test_render_pdf_produces_valid_multipage_pdf():
    pdf = render_pdf(_report())
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf[:5] == b"%PDF-"
    pages = _pages_text(pdf)
    assert len(pages) >= 2  # simple cover + technical detail


def test_first_page_is_plain_language_no_citations():
    pages = _pages_text(render_pdf(_report()))
    first = pages[0]
    # actionable genes surfaced in the plain summary
    assert "SLCO1B1" in first and "TPMT" in first
    # affected medicines named in plain terms (pulled from the recommendations)
    assert "simvastatin" in first.lower()
    # the citation accession is technical — it must NOT clutter the first page
    assert "PA166264281" not in first


def test_detail_section_has_full_prose_citations_and_disclaimer():
    full = _norm("\n".join(_pages_text(render_pdf(_report()))))
    # full recommendation prose appears (not just the plain one-liner)
    assert "creatine kinase monitoring" in full
    # citation accessions live in the technical detail
    assert "PA166264281" in full and "PA166251442" in full
    # unremarkable screen is carried through
    assert "clopidogrel" in full
    # ADR-0011 disclaimer always present
    assert _norm(DISCLAIMER) in full
