# CONTEXT — DNA Analysis SaaS (V1 backend prototype)

The V1 backend for a future web-app SaaS that ingests a genome + health-tracker + lab data and produces a structured medical report. V1 is a **modular Python package with a CLI entry point** — no UI yet — exercised on a **mixed synthetic individual** (PGP-published genome + author's Whoop + author's labs) to validate the agent + medical-retrieval architecture before adding the web layer.

The point isn't the engineering — it's the eval. Build the eval first.

## Glossary

| Term | Meaning |
| --- | --- |
| **agent loop** | A Claude Opus 4.7 (1M context) chat session that uses tool calls to look up reference data, then writes a structured medical report. |
| **gold set** | 5–10 variants from the input genome (PGP sample) where the correct PGx answer is independently verifiable via PharmGKB, encoded in `gold.yaml`. The eval grades agent output against this. |
| **PGx** | Pharmacogenomics — gene-drug interactions. Scope is 5–10 high-impact pairs (e.g. CYP2C19/clopidogrel), not comprehensive. |
| **PRS** | Polygenic risk score for a condition. **Punted to V2 — see ADR-0006.** Cannot be graded by the rubric, calibration is ancestry-sensitive. Term retained here because it appears in V2 planning. |
| **filtered genotype** | The ~few hundred clinically-interesting SNPs left after intersecting the input 23andMe-format export with PharmGKB ∪ ClinVar. The other ~600k SNPs are dropped. |
| **report** | `report.md` — the structured markdown output of one CLI run on the input bundle (genome + health + labs). |
| **static refs** | PharmGKB CPIC guidelines, PGS Catalog scoring weights, ClinVar summaries. Downloaded once, **cached via prompt caching** on every run. |
| **ETL** | One-time preprocessing that flattens the raw static-ref dumps into structured tables keyed for tool lookup: `pgx_pairs(rsid, gene, drug, guideline_id, evidence_level, recommendation_text, citation_url, phenotype_table)` and `clinvar_records(rsid, clinical_significance, condition, review_status)`. The **name allowlist** also falls out of this step as a set of drug/gene/condition strings. (V2 adds `pgs_scores` once PRS is in scope.) |
| **hallucinated drug** | An invented drug name or gene name in the report. The single failure mode the eval treats as fatal — zero tolerance. |
| **name allowlist** | The closed set of drug names, gene names, and condition names the agent is permitted to use in the report. Derived from the static refs (drugs from PharmGKB, genes from ClinVar, conditions from PGS Catalog). The hallucination check is exactly: every drug/gene/condition mentioned in the report ∈ name allowlist. |
| **grader** | The thing that scores a `report.md` against `gold.yaml`. Programmatic for (a)(b)(c), manual read for (d). |
| **gold entry** | One row in `gold.yaml`. Granularity is **(RSID, drug) pair**, not per-RSID — matches how CPIC publishes guidelines. ~10 RSIDs × ~3 drugs each → ~25–40 entries. Each entry is independently gradable on (a)(b)(c)(d). |
| **finding** | The structured output of one per-variant Claude call. Fields: `rsid`, `gene`, `genotype`, `drug`, `guideline_id`, `evidence_level` (CPIC A–D), `recommendation_gist`, `citation_url`, `clinically_actionable: bool`, `same_gene_context: list[(rsid, genotype)]` (per ADR-0008). Granularity matches gold entries — one finding per (RSID, drug) pair. |
| **diplotype** | A clinical-genetics term for the *pair* of star alleles a person carries at a pharmacogene (e.g. CYP2C19 \*1/\*2 vs. \*2/\*17). CPIC phenotypes are diplotype-level, not variant-level — so a per-variant call must see same-gene neighbours to interpret correctly (ADR-0008). |
| **unremarkable finding** | A finding with `clinically_actionable: false` — the genotype is the wild-type allele for a CPIC-screened pair. Surfaced in the report as a row in the "screened, unremarkable" appendix table, not as a paragraph. |
| **lab record** | One structured entry extracted from a lab PDF via Claude vision: `{test, value, unit, reference_range, date, flag (high/low/normal)}`. Persisted as `labs_extracted.json` alongside `report.md` so the manual (d) read can spot-check vision against the source PDF. See ADR-0007. Lab values quoted in the report must match `labs_extracted.json` strings verbatim — no paraphrasing. |
| **synthesis call** | The single Claude call (per ADR-0002, ADR-0009) that consumes the aggregated findings dict + `labs_extracted.json` + 90-day Whoop summary and returns a **report object**. Sees everything in one call → preserves cross-section reasoning. |
| **report object** | The typed Pydantic intermediate the synthesis call returns. Shape: `{actionable_findings: [...], lifestyle_observations: [...], lab_observations: [...], unremarkable_screen: [...], caveats: [...]}`. A Jinja template renders the object to `report.md`. Lets the grader read `guideline_id`/`citation_id` from JSON fields directly instead of regex-searching rendered prose. See ADR-0009. |
| **PGP** | Personal Genome Project. The Harvard-led consent-driven open data project that publishes participants' genomes for research and development use. The V1 input genome is sourced from PGP's public genetic data page. |
| **Whoop** | Wearable fitness tracker (the author's tracker — replaces Apple Health from the original ideation per ADR-0012). Central metric is HRV-based recovery; also surfaces strain, sleep performance, RHR. Export is CSV via the Whoop web portal. |
| **Fitbit Air** | Screenless Google Health tracker. Ingest is an extracted Google Health Takeout directory, not a live API. Maps onto the same 90-day summary as Whoop. Daily readiness fills the recovery slot. Day strain stays empty. |
| **mixed synthetic individual** | The V1 test subject: genome from a PGP volunteer, Whoop data and lab PDFs from the project author. The three sources are not the same person; the report's lifestyle/lab synthesis is therefore *stack-validation exercise only*, not personal medical advice. See ADR-0011. |

## Scope

**In.** Modular Python package with a CLI entry point. Module boundaries map to V2 web-app domains (ingest, ETL, agent, grader, report rendering). V1 runs once on a **mixed synthetic individual** (PGP genome + author's Whoop CSV + author's lab PDFs) and produces `report.md` covering PGx flags + lifestyle/genotype correlates + lab observations. Hand-graded against the gold set (PGx only).

**Out.** No web app yet — V2 work. No API, no auth, no deployment. No FHIR / EHR. No fine-tuning. No embeddings or vector DB — the 1M context lets you stuff data directly. No multi-user storage or persistence layer. **PRS / polygenic risk scores punted to V2** (see ADR-0006) — ungradable by this rubric.

## Stack

- Python 3.11+, Anthropic SDK (plain), model `claude-opus-4-7[1m]`.
- `pandas` for 23andMe parsing (raw export is tab-separated: RSID, chr, pos, genotype).
- **Whoop CSV parser** (custom, ~50 lines — Whoop exports a clean CSV from the web portal).
- PDF reading: send PDFs to Claude vision (skip OCR).
- Pydantic for `Finding` and `ReportObject` typed intermediates.
- Jinja for `report.md` rendering.
- **Prompt caching is non-negotiable** for the static refs (see ADRs).

## The agent loop

1. Parse 23andMe → filter to RSIDs in PharmGKB ∪ ClinVar (≈600k → a few hundred). RSID-only intersection per ADR-0004.
2. Parse exactly one wearable export, Whoop CSV or Fitbit Air directory, into a 90-day summary: HRV, recovery or readiness, strain when the device has it, RHR, sleep duration, sleep performance.
3. Read lab PDFs via Claude vision → `labs_extracted.json` per ADR-0007.
4. **Per-variant loop (ADR-0002).** For each filtered RSID, harness calls Claude with `{focal_pair, same_gene_context}` + tools (ADR-0008). Claude returns a `Finding` (ADR-0003).
5. **Synthesis call (ADR-0009).** One Claude call sees the aggregated findings dict + `labs_extracted.json` + 90-day Whoop summary; returns a typed `ReportObject`.
6. Jinja template renders `ReportObject` → `report.md`. Save alongside `labs_extracted.json`.
7. Grader runs (a)(b)(c) programmatically against `gold.yaml`; (d) is read manually.

## Tools the agent has

- `lookup_pharmgkb_pgx(rsid_or_gene_or_drug)` — structured PGx record (ADR-0005).
- `lookup_clinvar(rsid)` — structured ClinVar record.
- `search_pubmed(query, max_results=5)` — last resort, sparing use, free-text.

V2: `lookup_pgs_catalog(condition)` — PRS scoring weights. Out for V1 per ADR-0006.

Out for V1: ClinGen, OMIM, custom embeddings, semantic search.

## Eval rubric

Build before the agent. Without it you produce a confident-sounding report you can't grade.

- Pick 5–10 PGP-sample variants where the answer is independently verifiable on PharmGKB; encode as **gold entries** (per (RSID, drug) pair, ADR-0001) in `gold.yaml`.
- Per-entry grade:
  - (a) did the report surface the variant?
  - (b) did it cite the right PGx guideline?
  - (c) did it hallucinate any drug name or gene?
  - (d) is the wording medically defensible?
- Targets: 80%+ on (a)(b)(d). **Zero** on (c).
- If (c) > 0, that's the only bug worth fixing — hallucinated drug recommendations are the only output that's actively dangerous.

## Order of work

The order is constrained by the eval-first ethos and the module boundaries that V2 will reuse.

- **Build first.** Static-ref ETL → name allowlist → `gold.yaml` schema + entries → grader for (a)(b)(c). This is the bar the agent has to clear.
- **Then.** Ingest modules (23andMe parser, Whoop CSV parser, lab-PDF vision wrapper) and the filter intersection.
- **Then.** Per-variant agent call (tool-use + same-gene context).
- **Then.** Synthesis call → `ReportObject` → Jinja template → `report.md`.
- **Last.** Run end-to-end; grade; iterate; write the limits note.

## Data handling

- **Genome** is from PGP — publicly published with informed consent. Safe to keep locally; gitignored as standard hygiene. Filename should drop the participant's name in any artefact that leaves `data/` (logs, screenshots, commit messages).
- **Whoop CSV** is the author's own data. Treat as PII. Gitignored.
- A Fitbit Air / Google Health export is the user's own data. Treat as PII. Gitignored under `data/`.
- **Lab PDFs** are the author's own data. Treat as PII. Gitignored.
- Reference DB dumps (PharmGKB, ClinVar) are public and may be committed if size allows; otherwise gitignore and fetch via ETL.

## Why this matters

- Validates the agent + medical-retrieval architecture as the foundation V2 will build the web app on.
- Builds the eval-rubric muscle, which matters more than any code written in V1.
- Forces an ADR habit before the architecture has accumulated quiet implicit decisions a web app would inherit.
- Sets a clean module boundary now so V2 can wrap, not rewrite.

## Parked questions

- V2 web-app shape — FastAPI + Next.js, FastHTML, something else? Decide after V1 ships.
- Multi-tenant storage model. No persistence in V1; the V2 design defines this.
- Liability framing. Output to self is fine; output to other users (V2) needs careful framing — punt to a separate session.
- Re-enabling PRS for V2 (ADR-0006 re-entry conditions).
