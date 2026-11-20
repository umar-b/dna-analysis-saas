"""Fitbit Air ingest. Synthetic Google Health files only — never a real export."""

import json
from pathlib import Path

from dna_analysis.ingest.fitbit import parse


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _export(root: Path) -> None:
    _write(
        root,
        "Physical Activity_GoogleData/Daily Resting Heart Rate/daily_resting_heart_rate.csv",
        "timestamp,beats per minute,data source\n"
        "2026-05-29T00:00:00Z,70,air\n"
        "2026-05-28T00:00:00Z,80,air\n"
        "2026-02-01T00:00:00Z,90,air\n",  # older than 90 days from the anchor
    )
    _write(
        root,
        "Physical Activity_GoogleData/Daily Heart Rate Variability/daily_heart_rate_variability.csv",
        "timestamp,average heart rate variability milliseconds,data source\n"
        "2026-05-29T00:00:00Z,50,air\n"
        "2026-05-28T00:00:00Z,30,air\n"
        "2026-05-27T00:00:00Z,99,air\n",  # no resting HR that day -> ignored
    )
    _write(
        root,
        "Physical Activity_GoogleData/Daily Readiness/daily_readiness.csv",
        "timestamp,score,type,readiness level\n"
        "2026-05-29,80,readiness,good\n"
        "2026-05-28,60,readiness,good\n",
    )
    _write(
        root,
        "Sleep Score/sleep_score.csv",
        "sleep_log_entry_id,timestamp,overall_score,composition_score\n"
        "1,2026-05-29T08:00:00Z,80,70\n"
        "2,2026-05-28T08:00:00Z,60,70\n",
    )
    sleep = [
        {"dateOfSleep": "2026-05-29", "minutesAsleep": 480, "mainSleep": True},
        {"dateOfSleep": "2026-05-29", "minutesAsleep": 20, "mainSleep": False},
        {"dateOfSleep": "2026-05-28", "minutesAsleep": 420, "mainSleep": True},
        {"dateOfSleep": "2026-02-01", "minutesAsleep": 400, "mainSleep": True},
    ]
    _write(root, "Global Export Data/sleep-2026-05-21.json", json.dumps(sleep))


def test_fitbit_fills_the_same_summary_and_skips_strain(tmp_path):
    _export(tmp_path)
    s = parse(str(tmp_path))
    assert s.device == "fitbit_air"
    assert s.anchor_date == "2026-05-29"
    assert s.window_start == "2026-02-28"
    assert s.n_cycles == 2
    assert s.avg_resting_hr == 75.0  # (70+80)/2
    assert s.avg_hrv_ms == 40.0  # (50+30)/2; the 99 has no resting HR
    assert s.avg_recovery_score == 70.0  # readiness (80+60)/2
    assert s.avg_sleep_performance == 70.0
    assert s.avg_sleep_duration_min == 450.0  # main sleep only, (480+420)/2
    assert s.avg_day_strain is None


def test_fitbit_accepts_google_health_wrapper_dir(tmp_path):
    inner = tmp_path / "Google Health"
    _export(inner)
    s = parse(str(tmp_path))
    assert s.device == "fitbit_air"
    assert s.n_cycles == 2


def test_empty_export_returns_zeroed_fitbit_summary(tmp_path):
    s = parse(str(tmp_path))
    assert s.device == "fitbit_air"
    assert s.n_cycles == 0
    assert s.avg_resting_hr is None
    assert s.avg_day_strain is None
