"""Render a ReportObject to report.md (ADR-0009, ADR-0011).

Fixed section order so the grader's reads stay stable across eval iterations;
the V1 disclaimer footer is emitted unconditionally (ADR-0011).
"""

from __future__ import annotations

from importlib.resources import files

from jinja2 import Environment

from dna_analysis.models import ReportObject

# ADR-0011: every V1 report carries this footer — the report is a mixed
# synthetic individual and is not medical advice for any real person.
DISCLAIMER = (
    "V1 demo — genome from a PGP-published volunteer; lifestyle and lab data "
    "from the project author. This report is not medical advice for any real "
    "person. Used only to exercise the pipeline."
)


def render(report_object: ReportObject, template_path: str | None = None) -> str:
    """Render ``report_object`` to markdown using the Jinja template."""
    if template_path is None:
        template_text = (
            files("dna_analysis.report") / "templates" / "report.md.j2"
        ).read_text(encoding="utf-8")
    else:
        with open(template_path, encoding="utf-8") as handle:
            template_text = handle.read()

    env = Environment(trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    template = env.from_string(template_text)
    return template.render(report=report_object, disclaimer=DISCLAIMER)
