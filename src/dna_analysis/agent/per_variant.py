"""Per-variant agent call + same-gene grouping (ADR-0002, ADR-0008).

The harness groups the filtered genotype by gene and, for each focal rsid, hands
the per-variant call its same-gene neighbours so the model can reason about the
diplotype (CPIC phenotypes are diplotype-level, not variant-level).
"""

from __future__ import annotations

import json

import pandas as pd

from dna_analysis.agent.llm import cached_tokens
from dna_analysis.models import Finding, NameAllowlist, PgxPair
from dna_analysis.tools.pharmgkb import lookup_pharmgkb_pgx

_FINDING_PROPS = {
    "rsid": {"type": "string"},
    "gene": {"type": "string"},
    "genotype": {"type": "string"},
    "drug": {"type": "string", "description": "lowercase CPIC drug name, from the allowlist"},
    "guideline_id": {"type": "string", "description": "copied verbatim from tool output"},
    "evidence_level": {"type": "string", "enum": ["A", "B", "C", "D"]},
    "recommendation_gist": {"type": "string"},
    "citation_url": {"type": "string"},
    "clinically_actionable": {"type": "boolean"},
}

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_pharmgkb_pgx",
            "description": "Look up structured PGx records by rsid, gene, or drug.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_findings",
            "description": "Submit one Finding per (rsid, drug) for the focal variant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": _FINDING_PROPS,
                            "required": list(_FINDING_PROPS),
                        },
                    }
                },
                "required": ["findings"],
            },
        },
    },
]


def rsid_to_gene(pgx_pairs: list[PgxPair]) -> dict[str, str]:
    """Map each rsid to its gene, from the pgx_pairs table."""
    return {p.rsid: p.gene for p in pgx_pairs}


def build_same_gene_context(
    filtered_df: pd.DataFrame, gene_of: dict[str, str]
) -> dict[str, list[tuple[str, str]]]:
    """For each filtered rsid, its same-gene neighbours as (rsid, genotype) (ADR-0008).

    rsids with no known gene (not in ``gene_of``) get an empty neighbour list.
    """
    rows = list(zip(filtered_df["rsid"], filtered_df["genotype"]))
    by_gene: dict[str, list[tuple[str, str]]] = {}
    for rsid, genotype in rows:
        gene = gene_of.get(rsid)
        if gene is not None:
            by_gene.setdefault(gene, []).append((rsid, genotype))

    context: dict[str, list[tuple[str, str]]] = {}
    for rsid, _genotype in rows:
        gene = gene_of.get(rsid)
        neighbours = by_gene.get(gene, []) if gene is not None else []
        context[rsid] = [(r, g) for (r, g) in neighbours if r != rsid]
    return context


def build_system_prompt(pgx_pairs: list[PgxPair], allowlist: NameAllowlist) -> str:
    """Stable per-run reference + instructions — the cached prefix (ADR-0002, ADR-0014).

    Carries the closed-vocabulary allowlist and a compact PGx reference so the
    prefix is stable across every per-variant call and large enough to cache.
    """
    # dedup gene/drug/guideline reference rows (stable, compact)
    seen, ref_lines = set(), []
    for p in pgx_pairs:
        key = (p.gene, p.drug)
        if key not in seen:
            seen.add(key)
            ref_lines.append(
                f"{p.gene}\t{p.drug}\t{p.guideline_id}\t{p.evidence_level}"
            )
    ref_lines.sort()
    return (
        "You are a clinical pharmacogenomics curator producing a structured Finding "
        "for ONE focal variant. Rules:\n"
        "- Call lookup_pharmgkb_pgx with the focal rsid to retrieve the PGx records, "
        "then call submit_findings with ONE finding per (rsid, drug) pair returned.\n"
        "- Copy guideline_id and citation_url VERBATIM from the tool output; never invent them.\n"
        "- Use ONLY drug and gene names that appear in the name allowlist below. If you "
        "would need a name outside it, abstain rather than introduce a new proper noun.\n"
        "- evidence_level is the CPIC level (A-D) from the tool.\n"
        "- clinically_actionable: true only if the focal diplotype (focal genotype + "
        "same-gene context) yields a NON-standard CPIC recommendation; false for "
        "normal/wild-type (standard dosing -> unremarkable screen).\n"
        "- recommendation_gist: one defensible sentence.\n\n"
        "NAME ALLOWLIST\n"
        f"drugs: {', '.join(allowlist.drugs)}\n"
        f"genes: {', '.join(allowlist.genes)}\n"
        f"conditions: {', '.join(allowlist.conditions)}\n\n"
        "PGx REFERENCE (gene\tdrug\tguideline_id\tcpic_level)\n" + "\n".join(ref_lines)
    )


def run_all(
    filtered_df: pd.DataFrame,
    pgx_pairs: list[PgxPair],
    allowlist: NameAllowlist,
    client,
    model: str,
    max_variants: int | None = None,
) -> tuple[list[Finding], dict]:
    """Iterate filtered focal rsids (grouped by gene) and collect all Findings."""
    gene_of = rsid_to_gene(pgx_pairs)
    context = build_same_gene_context(filtered_df, gene_of)
    rows = [
        (rsid, genotype)
        for rsid, genotype in zip(filtered_df["rsid"], filtered_df["genotype"])
        if rsid in gene_of
    ]
    rows.sort(key=lambda rg: (gene_of[rg[0]], rg[0]))  # group same-gene; warm cache
    if max_variants is not None:
        rows = rows[:max_variants]

    findings: list[Finding] = []
    info = {"cached_tokens": 0, "calls": 0, "variants": len(rows)}
    for rsid, genotype in rows:
        focal = {"rsid": rsid, "gene": gene_of[rsid], "genotype": genotype}
        got, call_info = call(
            focal, context.get(rsid, []), pgx_pairs, allowlist, client, model
        )
        findings.extend(got)
        info["cached_tokens"] = max(info["cached_tokens"], call_info["cached_tokens"])
        info["calls"] += call_info["calls"]
    return findings, info


def call(
    focal: dict,
    same_gene_context: list[tuple[str, str]],
    pgx_pairs: list[PgxPair],
    allowlist: NameAllowlist,
    client,
    model: str,
    max_turns: int = 5,
) -> tuple[list[Finding], dict]:
    """One per-variant agent call (ADR-0002, ADR-0008). Returns (findings, info).

    ``same_gene_context`` is harness-supplied and stamped onto every returned
    Finding — coverage of that field is a property of the harness, not the model.
    """
    system_prompt = build_system_prompt(pgx_pairs, allowlist)
    user = (
        f"Focal variant: rsid={focal['rsid']} gene={focal['gene']} "
        f"genotype={focal['genotype']}\n"
        f"Same-gene context (rsid, genotype): {same_gene_context or 'none'}\n"
        "Produce one Finding per CPIC drug for this variant."
    )
    messages = [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        },
        {"role": "user", "content": user},
    ]

    info = {"cached_tokens": 0, "calls": 0}
    for _ in range(max_turns):
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=_TOOLS, max_tokens=2000
        )
        info["calls"] += 1
        info["cached_tokens"] = max(info["cached_tokens"], cached_tokens(resp.usage))
        msg = resp.choices[0].message
        if not msg.tool_calls:
            break
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            if tc.function.name == "lookup_pharmgkb_pgx":
                result = lookup_pharmgkb_pgx(args.get("query", ""), pgx_pairs)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)}
                )
            elif tc.function.name == "submit_findings":
                findings = []
                for f in args.get("findings", []):
                    if isinstance(f, str):  # haiku sometimes nests a JSON string
                        try:
                            f = json.loads(f)
                        except json.JSONDecodeError:
                            continue
                    if not isinstance(f, dict) or "gene" not in f or "drug" not in f:
                        continue
                    findings.append(
                        Finding(
                            rsid=f.get("rsid", focal["rsid"]),
                            gene=f["gene"],
                            genotype=f.get("genotype", focal["genotype"]),
                            drug=f["drug"],
                            guideline_id=f["guideline_id"],
                            evidence_level=f["evidence_level"],
                            recommendation_gist=f.get("recommendation_gist", ""),
                            citation_url=f.get("citation_url", ""),
                            clinically_actionable=bool(f.get("clinically_actionable", False)),
                            same_gene_context=list(same_gene_context),
                        )
                    )
                return findings, info
    return [], info
