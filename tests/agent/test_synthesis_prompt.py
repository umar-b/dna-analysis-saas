from dna_analysis.agent.synthesis import _system_prompt
from dna_analysis.models import NameAllowlist


def test_prompt_names_device_and_skips_null_metrics():
    text = _system_prompt(NameAllowlist())
    assert "whoop" in text
    assert "fitbit_air" in text
    assert "null" in text
    assert "day strain" in text
