"""Report rendering (ADR-0009): ReportObject -> report.md (Jinja) or PDF."""

from dna_analysis.report.pdf import render_pdf
from dna_analysis.report.render import DISCLAIMER, render

__all__ = ["render", "render_pdf", "DISCLAIMER"]
