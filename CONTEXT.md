# CONTEXT — n-of-1 Health Agent (weekend MVP)

A weekend spike: a Claude Code-style agent loop over your own 23andMe + Apple Health + lab PDFs, producing a personal markdown health report. **Not a product. Not for other users.** A working notebook by Sunday night plus an eval rubric that says whether the agent's output is trustworthy enough to act on.

The point isn't the engineering — it's the eval. Build the eval first.

## Glossary

| Term | Meaning |
| --- | --- |
| **agent loop** | A Claude Opus 4.7 (1M context) chat session that uses tool calls to look up reference data, then writes a structured medical report. |
| **gold set** | 5–10 of *your own* variants where the correct PGx answer is known in advance, encoded in `gold.yaml`. The eval grades agent output against this. |
| **PGx** | Pharmacogenomics — gene-drug interactions. Scope is 5–10 high-impact pairs (e.g. CYP2C19/clopidogrel), not comprehensive. |
| **PRS** | Polygenic risk score for a condition. Scope is 3–5 conditions you care about, not 50. |
| **filtered genotype** | The ~few hundred clinically-interesting SNPs left after intersecting your 23andMe raw export with PharmGKB ∪ ClinVar. The other ~600k SNPs are dropped. |
| **report** | `report.md` — the structured markdown output of one agent run on yourself. |
| **static refs** | PharmGKB CPIC guidelines, PGS Catalog scoring weights, ClinVar summaries. Downloaded once, **cached via prompt caching** on every run. |
| **hallucinated drug** | An invented drug name or gene name in the report. The single failure mode the eval treats as fatal — zero tolerance. |

## Scope

**In.** One Python notebook or script. Single user (you), single run, on your laptop. Inputs: 23andMe `.txt`, Apple Health export, 1–2 lab PDFs. Output: `report.md`. Hand-graded against the gold set.

**Out.** No web app, API, auth, deployment. No FHIR / EHR. No fine-tuning. No embeddings or vector DB — the 1M context lets you stuff data directly. No product thinking (UX, pricing, positioning) this weekend.

## Stack

- Python 3.11+, Anthropic SDK, model `claude-opus-4-7[1m]`
- `pandas` for 23andMe parsing (raw export is tab-separated: RSID, chr, pos, genotype)
- OSS Apple Health export parser (e.g. `apple-health-export` on PyPI)
- PDF reading: send PDFs to Claude vision (skip OCR)
- **Prompt caching is non-negotiable** for the static refs

## The agent loop

1. Parse 23andMe → filter to RSIDs in PharmGKB ∪ ClinVar (≈600k → a few hundred).
2. Parse Apple Health → 90-day summary: HRV, RHR, sleep duration + variability, activity.
3. Read lab PDFs via Claude vision → structured JSON (test name, value, range, flag).
4. Build the agent prompt: medical-reasoning agent, filtered genotype + 90-day health + labs follow, produce structured report covering PGx flags, PRS-based risk for chosen conditions, and lifestyle/genotype correlates. **Cite every claim.**
5. Run agent loop with tool use.
6. Save `report.md`.

## Tools the agent has

- `lookup_pharmgkb_pgx(rsid_or_gene_or_drug)` — CPIC guideline text
- `lookup_pgs_catalog(condition)` — PRS scoring weights
- `lookup_clinvar(rsid)` — clinical significance + condition
- `search_pubmed(query, max_results=5)` — last resort, sparing use

Out for V1: ClinGen, OMIM, custom embeddings, semantic search.

## Eval rubric — the actual hard part

Build before the agent. Without it you produce a confident-sounding report you can't grade.

- Pick 5–10 of your own variants with known answers; manually look them up on PharmGKB; encode in `gold.yaml`.
- Per-variant grade:
  - (a) did it surface the variant?
  - (b) did it cite the right PGx guideline?
  - (c) did it hallucinate any drug name or gene?
  - (d) is the wording medically defensible?
- Targets: 80%+ on (a), (b), (d). **Zero** on (c).
- If (c) > 0, that's the only bug worth fixing this weekend — hallucinated drug recommendations are the only output that's actively dangerous.

## Day-by-day

- **Sat AM.** Gather data; parse 23andMe + Apple Health; filter to clinically-interesting SNPs.
- **Sat PM.** Wire the four tools. Hand-look-up the gold set; write `gold.yaml`.
- **Sun AM.** Claude agent loop with tool use + prompt caching. Run once on yourself.
- **Sun PM.** Grade vs. gold set. Iterate prompt + tool descriptions until eval passes. Write a one-page note on limits.

## Data handling

Raw genome and Apple Health data is PII. **`data/` is gitignored** — raw exports never go to GitHub even though the repo is private. Reference DB dumps (PharmGKB, PGS Catalog, ClinVar) are public and can be committed.

## Why this matters

- Validates the agent + medical-retrieval architecture on real data.
- Creates a personal artifact (you actually know your own PGx now).
- Builds the eval-rubric muscle, which matters more than any code written this weekend.
- Compounds with the bigger BME bet — same agent loop later points at EEG patterns instead of variants.

## Parked questions

- Right downstream form factor — notebook, CLI, chat UI? Decide once eval passes.
- Where does the liability cliff sit? Output to self is fine; output to others needs careful framing.
- Does the same architecture work on someone else's data, or only your own?
