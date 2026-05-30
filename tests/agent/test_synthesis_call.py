"""Real-API test for the synthesis call (issue #8, no mocked LLM)."""

import os

import pytest

from dna_analysis.agent.llm import get_client_and_model, load_dotenv
from dna_analysis.agent.synthesis import call
from dna_analysis.models import Finding, NameAllowlist

load_dotenv()
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"), reason="live API test"
)


def _findings():
    return [
        Finding(
            rsid="rs4149056", gene="SLCO1B1", genotype="CT", drug="simvastatin",
            guideline_id="PA166264281", evidence_level="A",
            recommendation_gist="Decreased function; lower dose or alternative.",
            citation_url="https://www.clinpgx.org/guideline/PA166264281",
            clinically_actionable=True,
        ),
        Finding(
            rsid="rs4244285", gene="CYP2C19", genotype="GG", drug="clopidogrel",
            guideline_id="PA166251443", evidence_level="A",
            recommendation_gist="Normal metabolizer; standard dosing.",
            clinically_actionable=False,
        ),
    ]


def test_synthesis_returns_report_object_with_passthrough_unremarkable():
    allowlist = NameAllowlist(
        drugs=["simvastatin", "clopidogrel"], genes=["SLCO1B1", "CYP2C19"], conditions=[]
    )
    client, model, _ = get_client_and_model()
    report = call(_findings(), None, None, allowlist, client, model)
    # actionable finding rendered to prose with a citation
    assert len(report.actionable_findings) >= 1
    assert any(a.citation_id for a in report.actionable_findings)
    # unremarkable screen passed straight through (not model-derived)
    assert [f.rsid for f in report.unremarkable_screen] == ["rs4244285"]
