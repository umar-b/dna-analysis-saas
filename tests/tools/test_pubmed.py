"""Live integration test for search_pubmed against NCBI E-utilities (issue #7)."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("OFFLINE") == "1", reason="live NCBI E-utilities test"
)

from dna_analysis.tools.pubmed import search_pubmed


def test_search_pubmed_returns_title_abstract_pmid():
    results = search_pubmed("CYP2C19 clopidogrel pharmacogenomics", max_results=3)
    assert 1 <= len(results) <= 3
    first = results[0]
    assert set(first) == {"title", "abstract", "pmid"}
    assert first["pmid"].isdigit()
    assert first["title"]
