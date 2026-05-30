"""Real vision test for lab-PDF extraction (issue #10, no mocked LLM).

Runs against the committed synthetic 2-page lab PDF fixture. Skipped without key.
"""

import os
from pathlib import Path

import pytest

from dna_analysis.agent.llm import get_client_and_model, get_vision_model, load_dotenv

load_dotenv()
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"), reason="live vision API test"
)

from dna_analysis.ingest.labs import extract

PDF = str(Path(__file__).parent / "fixtures" / "lab_report_2page.pdf")


def test_extract_multipage_pdf_to_lab_records():
    client, _, _ = get_client_and_model()
    records = extract([PDF], client, get_vision_model())
    by_test = {r.test.lower(): r for r in records}
    # values span BOTH pages (HbA1c p1, Vitamin D p2) -> multi-page handled
    assert any("hba1c" in t for t in by_test)
    assert any("vitamin d" in t for t in by_test)
    hba1c = next(r for t, r in by_test.items() if "hba1c" in t)
    assert hba1c.value == "5.4"  # verbatim
    assert hba1c.flag in {"high", "low", "normal"}
