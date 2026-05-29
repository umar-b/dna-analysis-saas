"""ETL module (ADR-0005, ADR-0013).

Flattens CPIC + ClinVar static refs into structured tables and derives the
name allowlist. Pure flatteners live in `flatten`; network fetch and file
writes are at the module edge (`sources`, `tables`).
"""
