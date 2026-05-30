"""Report rendering (ADR-0009): ReportObject -> report.md via a Jinja template."""

from dna_analysis.report.render import DISCLAIMER, render

__all__ = ["render", "DISCLAIMER"]
