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


_D_CHECKLIST = (
    "Manual (d) review checklist (ADR-0001; PGx prose only, ADR-0011):\n"
    "  - Are the recommendation paragraphs medically defensible?\n"
    "  - Do drug/gene/condition names match what PharmGKB would say?\n"
    "  - (Lifestyle/lab sections are stack-validation only — not medically read.)"
)


def _run(
    genome: str,
    etl_dir: str,
    out_dir: str,
    no_agent: bool = False,
    max_variants: int | None = None,
    gold: str | None = None,
) -> int:
    """Ingest a genome, filter to clinically-interesting RSIDs (ADR-0004), then run
    the per-variant agent loop (ADR-0002/0008) and write findings.json. Writes
    filtered_genotype.parquet + filter_diagnostics.json regardless."""
    import json
    from pathlib import Path

    from dna_analysis.etl.tables import read_tables
    from dna_analysis.ingest.genome import GenomeParseError, filter_genotype, parse

    try:
        pgx_pairs, clinvar_records = read_tables(etl_dir)
        genome_df = parse(genome)
    except (FileNotFoundError, GenomeParseError) as err:
        print(f"error: {err}")
        return 1

    filtered, diagnostics = filter_genotype(genome_df, pgx_pairs, clinvar_records)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    filtered.to_parquet(out / "filtered_genotype.parquet")
    (out / "filter_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"filtered_genotype: {diagnostics['kept']} kept / {diagnostics['total']} total"
        f"  ({diagnostics['dropped']} dropped: {diagnostics['drop_reasons']})"
    )

    if no_agent:
        print("(--no-agent: skipped per-variant calls)")
        return 0

    from dna_analysis.agent.llm import get_client_and_model
    from dna_analysis.agent.per_variant import run_all
    from dna_analysis.grader.loaders import parse_name_allowlist_json
    from dna_analysis.models import NameAllowlist

    allowlist = NameAllowlist(
        **json.loads((Path(etl_dir) / "name_allowlist.json").read_text())
    )
    client, model, backend = get_client_and_model()
    findings, info = run_all(
        filtered,
        pgx_pairs,
        allowlist,
        client,
        model,
        clinvar_records=clinvar_records,
        max_variants=max_variants,
    )
    (out / "findings.json").write_text(
        json.dumps([f.model_dump() for f in findings], indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"findings: {len(findings)} from {info['variants']} variants "
        f"({info['calls']} API calls, {backend}/{model}, "
        f"max cache_read={info['cached_tokens']} tokens)"
    )

    # Synthesis -> ReportObject -> report.md (ADR-0009, ADR-0011)
    from dna_analysis.agent.synthesis import call as synth_call
    from dna_analysis.report import render

    report_object = synth_call(findings, None, None, allowlist, client, model)
    (out / "report_object.json").write_text(
        report_object.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    report_md = render(report_object)
    (out / "report.md").write_text(report_md, encoding="utf-8")
    print(
        f"report.md: {len(report_object.actionable_findings)} actionable, "
        f"{len(report_object.unremarkable_screen)} unremarkable"
    )

    # Grade (a)(b)(c) against the gold set (ADR-0001)
    if gold:
        from dna_analysis.grader import grade
        from dna_analysis.grader.loaders import parse_gold

        gold_entries = parse_gold(Path(gold).read_text())
        result = grade(report_object, report_md, gold_entries, allowlist.as_set())
        (out / "grade_result.json").write_text(
            result.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        print("\nGrade (per gold entry):")
        for e in result.entries:
            a = "PASS" if e.surfaced else "FAIL"
            b = "PASS" if e.cited_guideline else "FAIL"
            print(f"  {e.rsid:<11} {e.drug:<14} (a) {a}  (b) {b}")
        c = (
            "PASS"
            if result.hallucination.passed
            else f"FAIL {result.hallucination.out_of_vocabulary}"
        )
        print(
            f"aggregate: (a) {result.surfaced_count}/{result.total}  "
            f"(b) {result.cited_count}/{result.total}  (c) {c}"
        )

    print("\n" + _D_CHECKLIST)
    print(f"\n-> {out}/  (report.md, report_object.json, findings.json"
          + (", grade_result.json)" if gold else ")"))
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
    run = subparsers.add_parser(
        "run",
        help="Ingest a genome + filter to clinically-interesting RSIDs (ADR-0004).",
    )
    run.add_argument("--genome", required=True, help="23andMe-format export path.")
    run.add_argument("--etl-dir", required=True, help="Directory of ETL tables.")
    run.add_argument("--out", required=True, help="Output directory.")
    run.add_argument(
        "--no-agent", action="store_true", help="Ingest + filter only; skip agent."
    )
    run.add_argument(
        "--max-variants", type=int, default=None, help="Cap focal variants (dev cost)."
    )
    run.add_argument("--gold", default=None, help="gold.yaml for grading (a)(b)(c).")

    args = parser.parse_args(argv)
    if args.command == "grade-stub":
        return _grade_stub()
    if args.command == "etl":
        return _etl(args.out, args.from_dir)
    if args.command == "run":
        return _run(
            args.genome, args.etl_dir, args.out, args.no_agent,
            args.max_variants, args.gold,
        )

    parser.print_help()
    return 0
