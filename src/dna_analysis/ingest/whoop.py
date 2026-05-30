"""Whoop CSV ingest (ADR-0012). Reads physiological_cycles.csv -> WhoopSummary.

Drops rows with no recovery score (strap not worn), normalises dates to ISO,
and computes a 90-day summary anchored on the most-recent date IN THE FILE
(not today's date, per ADR-0012).
"""

from __future__ import annotations

import csv
import io
import os
from datetime import date, timedelta

from dna_analysis.models import WhoopSummary

WINDOW_DAYS = 90
_CYCLES_FILE = "physiological_cycles.csv"

# Whoop web-portal column -> WhoopSummary average field.
_METRICS = {
    "Heart rate variability (ms)": "avg_hrv_ms",
    "Recovery score %": "avg_recovery_score",
    "Day Strain": "avg_day_strain",
    "Resting heart rate (bpm)": "avg_resting_hr",
    "Asleep duration (min)": "avg_sleep_duration_min",
    "Sleep performance %": "avg_sleep_performance",
}


def _iso(value: str) -> str:
    """'2026-05-29 01:33:32' (or ISO date) -> '2026-05-29'."""
    return value.strip().split(" ")[0].split("T")[0]


def parse(path: str) -> WhoopSummary:
    """Parse a Whoop export. ``path`` may be the CSV or the export directory."""
    if os.path.isdir(path):
        path = os.path.join(path, _CYCLES_FILE)
    with open(path, encoding="utf-8") as handle:
        return parse_text(handle.read())


def _to_float(value: str):
    value = (value or "").strip()
    try:
        return float(value)
    except ValueError:
        return None


def parse_text(text: str) -> WhoopSummary:
    reader = csv.DictReader(io.StringIO(text))
    rows = [
        row
        for row in reader
        if (row.get("Recovery score %") or "").strip()  # strap worn that day
    ]
    dated = [(date.fromisoformat(_iso(r["Cycle start time"])), r) for r in rows]
    if not dated:
        return WhoopSummary()

    anchor = max(d for d, _ in dated)
    window_start = anchor - timedelta(days=WINDOW_DAYS)
    window = [r for d, r in dated if d > window_start]

    summary = WhoopSummary(
        anchor_date=anchor.isoformat(),
        window_start=window_start.isoformat(),
        window_days=WINDOW_DAYS,
        n_cycles=len(window),
    )
    for column, field in _METRICS.items():
        values = [v for v in (_to_float(r.get(column, "")) for r in window) if v is not None]
        if values:
            setattr(summary, field, round(sum(values) / len(values), 1))
    return summary
