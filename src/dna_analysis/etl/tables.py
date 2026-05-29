"""Write ETL tables to disk as jsonl + json (ADR-0013). I/O at the edge.

Output is deterministic for deterministic input — re-running the ETL on the
same upstream data produces byte-identical files (idempotent).
"""

from __future__ import annotations

import json
from pathlib import Path

from dna_analysis.models import ClinvarRecord, NameAllowlist, PgxPair


def read_tables(etl_dir) -> tuple[list[PgxPair], list[ClinvarRecord]]:
    """Load pgx_pairs.jsonl + clinvar_records.jsonl written by write_tables."""
    out = Path(etl_dir)
    pgx = [
        PgxPair(**json.loads(line))
        for line in (out / "pgx_pairs.jsonl").read_text().splitlines()
        if line.strip()
    ]
    clinvar = [
        ClinvarRecord(**json.loads(line))
        for line in (out / "clinvar_records.jsonl").read_text().splitlines()
        if line.strip()
    ]
    return pgx, clinvar


def _write_jsonl(path: Path, models) -> None:
    lines = [json.dumps(m.model_dump(), sort_keys=True) for m in models]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def write_tables(
    out_dir,
    pgx_pairs: list[PgxPair],
    clinvar_records: list[ClinvarRecord],
    allowlist: NameAllowlist,
) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "pgx_pairs": out / "pgx_pairs.jsonl",
        "clinvar_records": out / "clinvar_records.jsonl",
        "name_allowlist": out / "name_allowlist.json",
    }
    _write_jsonl(paths["pgx_pairs"], pgx_pairs)
    _write_jsonl(paths["clinvar_records"], clinvar_records)
    paths["name_allowlist"].write_text(
        json.dumps(allowlist.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths
