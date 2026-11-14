"""Hypothesis routing uses only bounded, sanitized failure data."""
import pytest

from core.research_triage import propose_followup_research


def test_triage_recommends_causes_to_test_not_automatic_fixes():
    trials = [
        {"reason": "no_verified_write", "denials": 1, "failure_class": None,
         "resources": {"min_system_available_mib": 3000}},
        {"reason": "hash_mismatch", "denials": 0, "failure_class": None,
         "resources": {"min_system_available_mib": 3400}},
    ]
    suggestions = propose_followup_research(trials, {"paired_delta_pp": 10})
    keys = [r["focus"] for r in suggestions]
    assert keys == [
        "R04_memory_headroom", "R06_approval_boundaries",
        "R01_exact_output", "R02_action_planning", "R00_sample_size",
    ]
    assert all("next_experiment" in r for r in suggestions)
    assert all("implemente" not in str(r).lower() for r in suggestions)


def test_no_statistical_claim_from_tiny_good_sample():
    result = propose_followup_research(
        [{"reason": "exact_sha256", "denials": 0,
          "resources": {"min_system_available_mib": 8192}}],
        {"paired_delta_pp": 100},
    )
    assert result == [{
        "focus": "R00_sample_size",
        "evidence": "Amostra exploratória pequena, sem significância estatística demonstrada.",
        "next_experiment": "Ampliar o conjunto retido com seeds e ordem alternada antes de promover mudanças.",
    }]


def test_large_sample_without_gain_invites_latency_comparison():
    trials = [{"reason": "exact_sha256", "denials": 0} for _ in range(40)]
    result = propose_followup_research(trials, {"paired_delta_pp": -5})
    assert result[0]["focus"] == "R03_harness_latency"


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        propose_followup_research(None, {})
    with pytest.raises(ValueError):
        propose_followup_research([], [])
