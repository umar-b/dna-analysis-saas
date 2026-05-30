"""Lab-PDF vision ingest (ADR-0007). One vision call per PDF -> LabRecords.

PDF pages are rendered to images and sent to a vision model (claude-3.5-haiku
has no vision, so a cheap vision model is used — ADR-0014). Lab values are kept
as verbatim strings (ADR-0007 mitigation 3): the synthesis prompt requires the
report to quote them exactly, and the manual (d) read spot-checks against the
source PDF via the persisted labs_extracted.json.
"""

from __future__ import annotations

import base64
import json

import fitz  # pymupdf

from dna_analysis.agent.llm import chat_with_retry
from dna_analysis.models import LabRecord

_VALID_FLAGS = {"high", "low", "normal"}
_PROMPT = (
    "Extract EVERY lab test from these report page images. Respond with ONE JSON "
    'object: {"records": [{"test": str, "value": str, "unit": str, '
    '"reference_range": str, "date": str, "flag": "high"|"low"|"normal"}]}. '
    "Copy each value VERBATIM (no rounding). Use the collection date from the "
    "header. flag reflects whether the value is high/low/normal vs its range."
)


def _page_images(path: str, dpi: int = 120) -> list[str]:
    doc = fitz.open(path)
    return [
        base64.b64encode(page.get_pixmap(dpi=dpi).tobytes("png")).decode()
        for page in doc
    ]


def _to_records(data: dict) -> list[LabRecord]:
    records: list[LabRecord] = []
    for rec in data.get("records", []):
        if not isinstance(rec, dict):
            continue
        flag = str(rec.get("flag", "")).strip().lower()
        records.append(
            LabRecord(
                test=str(rec.get("test", "")),
                value=str(rec.get("value", "")),
                unit=str(rec.get("unit", "")),
                reference_range=str(rec.get("reference_range", "")),
                date=str(rec.get("date", "")),
                flag=flag if flag in _VALID_FLAGS else "normal",
            )
        )
    return records


def extract(paths: list[str], client, vision_model: str) -> list[LabRecord]:
    """One vision call per PDF (handles multi-page) -> LabRecords (ADR-0007)."""
    records: list[LabRecord] = []
    for path in paths:
        content = [{"type": "text", "text": _PROMPT}]
        for b64 in _page_images(path):
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            )
        resp = chat_with_retry(
            client,
            model=vision_model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            # A multi-page panel emits dozens of records; 2000 truncated mid-JSON
            # (finish_reason=length) -> parse failure -> 0 records. Size for a full
            # 6-page report.
            max_tokens=8000,
        )
        try:
            data = json.loads(resp.choices[0].message.content or "{}")
        except json.JSONDecodeError:
            data = {}
        records.extend(_to_records(data))
    return records
