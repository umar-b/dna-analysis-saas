"""Real-API integration test for the per-variant call (issue #6, no mocked LLM).

Skipped when no OPENROUTER_API_KEY is available (env or .env).
"""

import os

import pytest

from dna_analysis.agent.llm import get_client_and_model, load_dotenv
from dna_analysis.agent.per_variant import call
from dna_analysis.models import NameAllowlist, PgxPair

load_dotenv()
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="no OPENROUTER_API_KEY — live API test",
)


def _pgx():
    return [
        PgxPair(rsid="rs4244285", gene="CYP2C19", drug="clopidogrel",
                guideline_id="PA166251443", evidence_level="A",
                citation_url="https://www.clinpgx.org/guideline/PA166251443"),
        PgxPair(rsid="rs4244285", gene="CYP2C19", drug="voriconazole",
                guideline_id="PA166251456", evidence_level="A",
                citation_url="https://www.clinpgx.org/guideline/PA166251456"),
    ]


def test_per_variant_call_returns_findings_with_allowlist_strings():
    allowlist = NameAllowlist(
        drugs=["clopidogrel", "voriconazole"], genes=["CYP2C19"], conditions=[]
    )
    client, model, _ = get_client_and_model()
    findings, info = call(
        focal={"rsid": "rs4244285", "gene": "CYP2C19", "genotype": "GG"},
        same_gene_context=[("rs12248560", "CC")],
        pgx_pairs=_pgx(),
        allowlist=allowlist,
        client=client,
        model=model,
    )
    assert len(findings) >= 1
    for f in findings:
        assert f.gene in allowlist.genes  # exact allowlist string
        assert f.drug in allowlist.drugs
        assert f.same_gene_context == [("rs12248560", "CC")]  # harness-stamped
    assert info["calls"] >= 2  # at least a lookup turn + a submit turn
