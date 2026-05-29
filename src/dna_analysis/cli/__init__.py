"""CLI entry point (ADR-0010).

File I/O lives here, at the module edge. Importing this module does nothing;
fixtures are read only when a command runs.
"""

from __future__ import annotations

import argparse
from importlib.resources import files

from dna_analysis.grader import grade
from dna_analysis.grader.loaders import (
    parse_gold,
    parse_name_allowlist_json,
    parse_report_object,
)


def _load_fixture(name: str) -> str:
    return (files("dna_analysis.grader") / "fixtures" / name).read_text(encoding="utf-8")


def _grade_stub() -> int:
    """Run the grader against bundled canned fixtures and print results.

    Fixture-based smoke test (issue #2): no real ETL, ingest, or agent — just
    proof the grader runs and prints in the shape later slices expect.
    """
    gold = parse_gold(_load_fixture("gold.yaml"))
    allowlist = parse_name_allowlist_json(_load_fixture("name_allowlist.json"))
    report_object = parse_report_object(_load_fixture("report_object.json"))
    rendered_md = _load_fixture("report.md")

    result = grade(report_object, rendered_md, gold, allowlist)

    print("Per-entry  (a) surfaced / (b) cited guideline")
    for entry in result.entries:
        a = "PASS" if entry.surfaced else "FAIL"
        b = "PASS" if entry.cited_guideline else "FAIL"
        print(f"  {entry.rsid:<11} {entry.drug:<13}  (a) {a}  (b) {b}")

    print()
    print(
        f"Aggregates: surfaced {result.surfaced_count}/{result.total}"
        f"  cited {result.cited_count}/{result.total}"
    )
    if result.hallucination.passed:
        print("(c) hallucination: PASS  (no out-of-vocabulary entities)")
    else:
        print(f"(c) hallucination: FAIL  {result.hallucination.out_of_vocabulary}")
    print(f"(d) {result.medical_defensibility.reason}")
    return 0


def _etl(out_dir: str, from_dir: str | None) -> int:
    """Flatten CPIC + ClinVar into pgx_pairs / clinvar_records / name_allowlist.

    With ``--from`` reads pre-downloaded raw sources (no network); otherwise
    fetches fresh dumps from the CPIC API + ClinVar (ADR-0013).
    """
    from dna_analysis.etl.sources import build_all, fetch_remote, load_local
    from dna_analysis.etl.tables import write_tables

    raw = load_local(from_dir) if from_dir else fetch_remote()
    pgx_pairs, clinvar_records, allowlist = build_all(raw)
    paths = write_tables(out_dir, pgx_pairs, clinvar_records, allowlist)

    print(f"pgx_pairs:        {len(pgx_pairs):>6} rows  -> {paths['pgx_pairs']}")
    print(f"clinvar_records:  {len(clinvar_records):>6} rows  -> {paths['clinvar_records']}")
    print(
        f"name_allowlist:   {len(allowlist.drugs)} drugs, "
        f"{len(allowlist.genes)} genes, {len(allowlist.conditions)} conditions  "
        f"-> {paths['name_allowlist']}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dna-analysis",
        description="V1 backend prototype CLI (ADR-0010).",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "grade-stub",
        help="Run the grader against bundled canned fixtures and print results.",
    )
    etl = subparsers.add_parser(
        "etl",
        help="Flatten CPIC + ClinVar into pgx_pairs / clinvar_records / name_allowlist.",
    )
    etl.add_argument("--out", required=True, help="Output directory for the tables.")
    etl.add_argument(
        "--from",
        dest="from_dir",
        default=None,
        help="Directory of pre-downloaded raw sources (skips network).",
    )

    args = parser.parse_args(argv)
    if args.command == "grade-stub":
        return _grade_stub()
    if args.command == "etl":
        return _etl(args.out, args.from_dir)

    parser.print_help()
    return 0
