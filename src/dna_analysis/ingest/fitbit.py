"""Fitbit Air ingest from an extracted Google Health Takeout.

Fills the same 90-day WearableSummary as the Whoop parser (ADR-0012).
A day counts only when it has a resting heart rate. Day strain stays None.
"""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import date, timedelta

from dna_analysis.models import WearableSummary

WINDOW_DAYS = 90

_RHR = "Physical Activity_GoogleData/Daily Resting Heart Rate/daily_resting_heart_rate.csv"
_HRV = "Physical Activity_GoogleData/Daily Heart Rate Variability/daily_heart_rate_variability.csv"
_READINESS = "Physical Activity_GoogleData/Daily Readiness/daily_readiness.csv"
_SLEEP_SCORE = "Sleep Score/sleep_score.csv"
_SLEEP_DIR = "Global Export Data"


def _export_root(path: str) -> str:
    for rel in (os.path.join("Takeout", "Google Health"), "Google Health"):
        candidate = os.path.join(path, rel)
        if os.path.isdir(candidate):
            return candidate
    return path


def _iso(value: str) -> str:
    return value.strip().split(" ")[0].split("T")[0]


def _to_float(value: str):
    value = (value or "").strip()
    try:
        return float(value)
    except ValueError:
        return None


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 1)


def _load_column(path: str, column: str) -> dict[date, list[float]]:
    grouped: dict[date, list[float]] = defaultdict(list)
    if not os.path.isfile(path):
        return grouped
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_day = row.get("timestamp") or ""
            value = _to_float(row.get(column, ""))
            if not raw_day.strip() or value is None:
                continue
            grouped[date.fromisoformat(_iso(raw_day))].append(value)
    return grouped


def _load_sleep_minutes(root: str) -> dict[date, float]:
    """Longest main-sleep minutesAsleep per date. Naps (mainSleep false) are dropped."""
    best: dict[date, float] = {}
    folder = os.path.join(root, _SLEEP_DIR)
    if not os.path.isdir(folder):
        return best
    for name in sorted(os.listdir(folder)):
        if not (name.startswith("sleep-") and name.endswith(".json")):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            continue
        for row in payload:
            if not isinstance(row, dict) or not row.get("mainSleep"):
                continue
            raw_day = row.get("dateOfSleep") or ""
            minutes = row.get("minutesAsleep")
            if not str(raw_day).strip() or not isinstance(minutes, (int, float)):
                continue
            day = date.fromisoformat(_iso(str(raw_day)))
            best[day] = max(best.get(day, 0.0), float(minutes))
    return best


def _day_means(grouped: dict[date, list[float]]) -> dict[date, float]:
    return {day: _mean(values) for day, values in grouped.items() if values}


def parse(path: str) -> WearableSummary:
    """Parse an extracted Fitbit / Google Health export directory."""
    root = _export_root(path)
    resting = _day_means(_load_column(os.path.join(root, _RHR), "beats per minute"))
    if not resting:
        return WearableSummary(device="fitbit_air")

    hrv = _day_means(
        _load_column(
            os.path.join(root, _HRV),
            "average heart rate variability milliseconds",
        )
    )
    readiness = _day_means(_load_column(os.path.join(root, _READINESS), "score"))
    sleep_score = _day_means(_load_column(os.path.join(root, _SLEEP_SCORE), "overall_score"))
    sleep_minutes = _load_sleep_minutes(root)

    anchor = max(resting)
    window_start = anchor - timedelta(days=WINDOW_DAYS)
    worn = [day for day in resting if window_start < day <= anchor]

    def avg(series: dict[date, float]):
        values = [series[day] for day in worn if day in series]
        return _mean(values) if values else None

    return WearableSummary(
        device="fitbit_air",
        anchor_date=anchor.isoformat(),
        window_start=window_start.isoformat(),
        window_days=WINDOW_DAYS,
        n_cycles=len(worn),
        avg_hrv_ms=avg(hrv),
        avg_recovery_score=avg(readiness),
        avg_day_strain=None,
        avg_resting_hr=avg(resting),
        avg_sleep_duration_min=avg(sleep_minutes),
        avg_sleep_performance=avg(sleep_score),
    )
