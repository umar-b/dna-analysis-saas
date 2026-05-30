"""Synthesis call (ADR-0002, ADR-0009): aggregated findings -> typed ReportObject.

One Claude call turns the actionable findings into prose; the unremarkable
screen is passed straight through from the findings dict (not re-derived by the
model). whoop_summary and lab_records are stubbed in this slice (#8); #9/#10
supply real values.
"""

from __future__ import annotations

import json

from dna_analysis.agent.llm import chat_with_retry
from dna_analysis.models import (
    ActionableFindingProse,
    Finding,
    NameAllowlist,
    ObservationProse,
    ReportObject,
)

def _system_prompt(allowlist: NameAllowlist) -> str:
    return (
        "You synthesize a structured medical report from per-variant pharmacogenomic "
        "findings. Respond with ONE JSON object and nothing else, with this shape:\n"
        '{"actionable_findings": [{"gene": str, "diplotype_label": str, '
        '"recommendation_paragraph": str, "citation_id": str, '
        '"related_finding_rsids": [str]}], '
        '"lifestyle_observations": [{"observation_paragraph": str}], '
        '"lab_observations": [{"observation_paragraph": str}], "caveats": [str]}\n'
        "Rules:\n"
        "- One actionable_findings entry per actionable finding: a defensible "
        "recommendation_paragraph, the diplotype_label, and citation_id copied VERBATIM "
        "from the finding's guideline_id.\n"
        "- Use ONLY drug/gene/condition names from the allowlist below; never introduce "
        "a new proper noun.\n"
        "- If a Whoop 90-day summary is provided, write lifestyle_observations that "
        "reference its metrics (HRV, recovery score, day strain, resting heart rate, "
        "sleep duration/performance). If none is provided, return empty "
        "lifestyle_observations and note the gap in caveats.\n"
        "- If lab records are provided, write lab_observations referencing them and "
        "quote every lab value EXACTLY as given — no rounding or paraphrasing "
        "(ADR-0007). If none, return empty lab_observations and note the gap.\n\n"
        f"NAME ALLOWLIST\ndrugs: {', '.join(allowlist.drugs)}\n"
        f"genes: {', '.join(allowlist.genes)}\nconditions: {', '.join(allowlist.conditions)}"
    )


def call(
    findings: list[Finding],
    whoop_summary,
    lab_records,
    allowlist: NameAllowlist,
    client,
    model: str,
    max_turns: int = 3,
) -> ReportObject:
    """Single synthesis call (ADR-0009). unremarkable_screen is passed through."""
    actionable = [f for f in findings if f.clinically_actionable]
    unremarkable = [f for f in findings if not f.clinically_actionable]

    whoop_repr = "none provided"
    if whoop_summary is not None:
        whoop_repr = json.dumps(
            whoop_summary.model_dump()
            if hasattr(whoop_summary, "model_dump")
            else whoop_summary
        )

    if lab_records:
        labs_repr = json.dumps(
            [r.model_dump() if hasattr(r, "model_dump") else r for r in lab_records]
        )
    else:
        labs_repr = "none provided"

    user = (
        "Actionable findings:\n"
        + json.dumps([f.model_dump() for f in actionable], indent=1)
        + f"\n\nWhoop 90-day summary: {whoop_repr}"
        + f"\nLab records: {labs_repr}\n\n"
        "Synthesize the report object."
    )
    messages = [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": _system_prompt(allowlist),
                 "cache_control": {"type": "ephemeral"}}
            ],
        },
        {"role": "user", "content": user},
    ]

    report_args: dict = {}
    for _ in range(max_turns):
        resp = chat_with_retry(
            client,
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=4000,
        )
        content = resp.choices[0].message.content or "{}"
        try:
            report_args = json.loads(content)
            break
        except json.JSONDecodeError as err:
            # ADR-0009: retry with a parse-error feedback turn
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {"role": "user", "content": f"That was not valid JSON ({err}). "
                 "Respond with ONE valid JSON object only."}
            )

    return ReportObject(
        actionable_findings=[
            ActionableFindingProse(
                gene=a.get("gene", ""),
                diplotype_label=a.get("diplotype_label", ""),
                recommendation_paragraph=a.get("recommendation_paragraph", ""),
                citation_id=a.get("citation_id", ""),
                related_finding_rsids=a.get("related_finding_rsids", []) or [],
            )
            for a in report_args.get("actionable_findings", [])
            if isinstance(a, dict)
        ],
        lifestyle_observations=[
            ObservationProse(observation_paragraph=o.get("observation_paragraph", ""))
            for o in report_args.get("lifestyle_observations", [])
            if isinstance(o, dict)
        ],
        lab_observations=[
            ObservationProse(observation_paragraph=o.get("observation_paragraph", ""))
            for o in report_args.get("lab_observations", [])
            if isinstance(o, dict)
        ],
        unremarkable_screen=unremarkable,  # passthrough (ADR-0009)
        caveats=report_args.get("caveats", []),
    )
