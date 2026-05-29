"""Raw-source loading + the ETL build orchestration (ADR-0013).

`build_all` is pure (raw payloads -> typed tables) and unit-tested.
`load_local` reads pre-downloaded fixtures; `fetch_remote` hits the CPIC API
and the ClinVar FTP dump — network, exercised by the live `etl` run, not unit
tests.
"""

from __future__ import annotations

import gzip
import io
import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from dna_analysis.etl.flatten import (
    build_name_allowlist,
    build_pgx_pairs,
    clinvar_gene_symbols,
    flatten_clinvar,
)
from dna_analysis.models import ClinvarRecord, NameAllowlist, PgxPair

CPIC_API = "https://api.cpicpgx.org/v1"
CLINVAR_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"
)
# V1 PGx gene scope (ADR-0013) — the genes the gold set (#4) draws from.
PGX_GENES = [
    "CYP2C19",
    "CYP2C9",
    "CYP3A5",
    "CYP4F2",
    "DPYD",
    "NUDT15",
    "SLCO1B1",
    "TPMT",
    "UGT1A1",
    "VKORC1",
]


@dataclass
class RawSources:
    sequence_location: list[dict] = field(default_factory=list)
    pairs: list[dict] = field(default_factory=list)
    recommendation: list[dict] = field(default_factory=list)
    diplotype: list[dict] = field(default_factory=list)
    clinvar_tsv: str = ""


def build_all(
    raw: RawSources,
) -> tuple[list[PgxPair], list[ClinvarRecord], NameAllowlist]:
    """Pure: raw payloads -> (pgx_pairs, clinvar_records, name_allowlist)."""
    pgx = build_pgx_pairs(
        raw.sequence_location, raw.pairs, raw.recommendation, raw.diplotype
    )
    clinvar = flatten_clinvar(raw.clinvar_tsv)
    allowlist = build_name_allowlist(
        pgx, clinvar, clinvar_genes=clinvar_gene_symbols(raw.clinvar_tsv)
    )
    return pgx, clinvar, allowlist


def load_local(src_dir) -> RawSources:
    """Load raw sources from a directory of pre-downloaded fixtures."""
    src = Path(src_dir)
    cpic = src / "cpic"
    clinvar_files = sorted((src / "clinvar").glob("*.tsv"))
    return RawSources(
        sequence_location=json.loads((cpic / "sequence_location.json").read_text()),
        pairs=json.loads((cpic / "pairs.json").read_text()),
        recommendation=json.loads((cpic / "recommendation.json").read_text()),
        diplotype=json.loads((cpic / "diplotype.json").read_text()),
        clinvar_tsv=clinvar_files[0].read_text() if clinvar_files else "",
    )


def _get_json(url: str) -> list[dict]:
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 (trusted host)
        return json.loads(resp.read().decode("utf-8"))


def fetch_remote() -> RawSources:  # pragma: no cover - network
    """Download fresh CPIC + ClinVar dumps. Network; not unit-tested."""
    genes = ",".join(PGX_GENES)
    seq = _get_json(
        f"{CPIC_API}/sequence_location?genesymbol=in.({genes})"
        "&dbsnpid=not.is.null&select=genesymbol,dbsnpid,name"
    )
    pairs = _get_json(
        f"{CPIC_API}/pair?genesymbol=in.({genes})&guidelineid=not.is.null"
        "&select=genesymbol,drugid,cpiclevel,guidelineid,drug(name),guideline(url,clinpgxid)"
    )
    guideline_ids = sorted({str(p["guidelineid"]) for p in pairs if p.get("guidelineid")})
    rec = _get_json(
        f"{CPIC_API}/recommendation?guidelineid=in.({','.join(guideline_ids)})"
        "&drugrecommendation=not.is.null"
        "&select=guidelineid,drugid,phenotypes,drugrecommendation"
    )
    dip = _get_json(
        f"{CPIC_API}/diplotype?genesymbol=in.({genes})"
        "&select=genesymbol,diplotype,generesult"
    )
    with urllib.request.urlopen(CLINVAR_URL, timeout=600) as resp:  # noqa: S310
        clinvar_tsv = gzip.GzipFile(fileobj=io.BytesIO(resp.read())).read().decode(
            "utf-8", "replace"
        )
    return RawSources(
        sequence_location=seq,
        pairs=pairs,
        recommendation=rec,
        diplotype=dip,
        clinvar_tsv=clinvar_tsv,
    )
