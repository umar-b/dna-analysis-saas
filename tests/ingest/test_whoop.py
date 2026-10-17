"""Tests for Whoop ingest (issue #9, ADR-0012). Synthetic fixtures only."""

from dna_analysis.ingest.whoop import parse_text

_HEADER = (
    "Cycle start time,Recovery score %,Resting heart rate (bpm),"
    "Heart rate variability (ms),Day Strain,Asleep duration (min),Sleep performance %"
)


def _csv(rows):
    return _HEADER + "\n" + "\n".join(rows) + "\n"


def test_drops_rows_missing_recovery_score():
    text = _csv([
        "2026-05-29 01:00:00,67,76,38,12.5,480,75",
        "2026-05-28 01:00:00,,70,40,10.0,450,80",  # no recovery -> dropped
        "2026-05-27 01:00:00,70,72,42,11.0,470,78",
    ])
    s = parse_text(text)
    assert s.n_cycles == 2  # the empty-recovery row dropped


def test_90_day_window_anchors_on_file_max_date_not_today():
    text = _csv([
        "2026-05-29 01:00:00,67,76,38,12.5,480,75",  # anchor
        "2026-02-01 01:00:00,60,80,30,9.0,400,60",   # >90 days before anchor -> excluded
        "2026-04-01 01:00:00,70,72,42,11.0,470,78",  # within 90 days -> included
    ])
    s = parse_text(text)
    assert s.anchor_date == "2026-05-29"
    assert s.window_start == "2026-02-28"  # 2026-05-29 minus 90 days
    assert s.n_cycles == 2  # the 2026-02-01 cycle excluded


def test_iso_date_normalisation_and_averages():
    text = _csv([
        "2026-05-29 01:33:32,80,70,50,10.0,480,80",
        "2026-05-28 22:10:00,60,80,30,12.0,420,60",
    ])
    s = parse_text(text)
    assert s.anchor_date == "2026-05-29"  # time component stripped
    assert s.avg_recovery_score == 70.0  # (80+60)/2
    assert s.avg_hrv_ms == 40.0  # (50+30)/2


def test_empty_input_returns_zeroed_summary():
    s = parse_text(_HEADER + "\n")
    assert s.n_cycles == 0
    assert s.avg_recovery_score is None


def test_whoop_summary_labels_device():
    text = _csv([
        "2026-05-29 01:33:32,80,70,50,10.0,480,80",
    ])
    s = parse_text(text)
    assert s.device == "whoop"
