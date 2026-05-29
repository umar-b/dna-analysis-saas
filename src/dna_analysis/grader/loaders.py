"""Pure parse helpers: text -> typed models. No file or network I/O.

Callers read bytes/text from disk (or bundled resources) and pass them here.
Keeping parsing pure lets later slices reuse it for real gold sets and reports.
"""

from __future__ import annotations

import json

import yaml

from dna_analysis.models import GoldEntry, NameAllowlist, ReportObject


def parse_gold(text: str) -> list[GoldEntry]:
    """Parse gold.yaml text into GoldEntry rows (ADR-0001, ADR-0003)."""
    rows = yaml.safe_load(text) or []
    return [GoldEntry(**row) for row in rows]


def parse_report_object(text: str) -> ReportObject:
    """Parse a JSON report object into a ReportObject (ADR-0009)."""
    return ReportObject.model_validate_json(text)


def parse_name_allowlist_json(text: str) -> set[str]:
    """Parse ETL ``name_allowlist.json`` into the flat token set (c) consumes.

    Format ``{drugs: [...], genes: [...], conditions: [...]}`` (ADR-0013);
    the grader's (c) check treats all three as one closed vocabulary.
    """
    return NameAllowlist(**json.loads(text)).as_set()
