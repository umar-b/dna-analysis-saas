"""Pure parse helpers: text -> typed models. No file or network I/O.

Callers read bytes/text from disk (or bundled resources) and pass them here.
Keeping parsing pure lets later slices reuse it for real gold sets and reports.
"""

from __future__ import annotations

import yaml

from dna_analysis.models import GoldEntry, ReportObject


def parse_gold(text: str) -> list[GoldEntry]:
    """Parse gold.yaml text into GoldEntry rows (ADR-0001, ADR-0003)."""
    rows = yaml.safe_load(text) or []
    return [GoldEntry(**row) for row in rows]


def parse_allowlist(text: str) -> set[str]:
    """Parse an allowlist file (one entity per line, '#' comments) into a set."""
    names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            names.add(stripped)
    return names


def parse_report_object(text: str) -> ReportObject:
    """Parse a JSON report object into a ReportObject (ADR-0009)."""
    return ReportObject.model_validate_json(text)
