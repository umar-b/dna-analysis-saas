"""search_pubmed tool (ADR-0005). Free-text, last-resort; hits NCBI E-utilities.

Unlike the other tools this is not ETL-backed — it queries live. The system
prompt directs the model to use it sparingly.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _get(url: str, timeout: int) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (trusted host)
        return resp.read()


def search_pubmed(query: str, max_results: int = 5, timeout: int = 30) -> list[dict]:
    """Return up to ``max_results`` PubMed hits as {title, abstract, pmid} dicts."""
    esearch = (
        f"{_EUTILS}/esearch.fcgi?db=pubmed&retmode=json"
        f"&retmax={max_results}&term={urllib.parse.quote(query)}"
    )
    import json

    ids = json.loads(_get(esearch, timeout)).get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    efetch = (
        f"{_EUTILS}/efetch.fcgi?db=pubmed&retmode=xml&id={','.join(ids)}"
    )
    root = ET.fromstring(_get(efetch, timeout))
    results: list[dict] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID", default="")
        title = article.findtext(".//ArticleTitle", default="")
        abstract = " ".join(
            (node.text or "") for node in article.findall(".//AbstractText")
        ).strip()
        results.append({"title": title, "abstract": abstract, "pmid": pmid})
    return results
