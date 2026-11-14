"""Tests for metrics, resource isolation, and deterministic research statistics."""
import json
import pytest

from core.eval_metrics import generation_metrics, summarize_trials
from core.eval_resources import MemorySampler, MIN_AVAILABLE_BYTES, admit_research


def test_ollama_durations_are_nanoseconds_and_rate_is_correct():
    sample = {
        "total_duration": 3_100_000_000,
        "load_duration": 100_000_000,
        "eval_duration": 2_000_000_000,
        "eval_count": 80,
        "prompt_eval_count": 320,
        "prompt_eval_cached_count": 260,
        "secret": "NEVER_EXPOSE",
    }
    result = generation_metrics(sample)
    assert result["total_duration_ns"] == 3_100_000_000
    assert result["output_tokens_per_second"] == 40
    assert result["prompt_eval_count"] == 320
    assert result["prompt_eval_cached_count"] == 260
    assert "secret" not in result
    json.dumps(result)


def test_invalid_numeric_usage_is_not_recorded_as_real_measurement():
    result = generation_metrics({
        "eval_count": True, "eval_duration": -10, "total_duration": "12",
        "prompt_eval_count": 10**22,
    })
    assert result == {"output_tokens_per_second": None}
    assert generation_metrics(None) == {}


def test_paired_harness_comparison_matches_case_and_repeat_only():
    cases = [
        {"case": "a", "repeat": 0, "variant": "baseline", "verified": False, "elapsed_seconds": 5},
        {"case": "a", "repeat": 0, "variant": "goal_gate", "verified": True, "elapsed_seconds": 6},
        {"case": "b", "repeat": 0, "variant": "baseline", "verified": True, "elapsed_seconds": 4},
        {"case": "b", "repeat": 0, "variant": "goal_gate", "verified": True, "elapsed_seconds": 7},
    ]
    s = summarize_trials(cases)
    assert s["matched_pairs"] == 2
    assert s["paired_delta_pp"] == 50
    assert s["variants"]["goal_gate"]["success_rate_pct"] == 100
    assert s["variants"]["baseline"]["success_rate_pct"] == 50
    assert s["interpretation"] == "experimental_small_sample_not_proof"


def test_summary_refuses_missing_or_fake_observations():
    with pytest.raises(ValueError):
        summarize_trials([{"variant": "goal_gate", "verified": "yes"}])
    with pytest.raises(ValueError):
        summarize_trials([{"variant": "unknown", "verified": True}])
    assert summarize_trials([])["paired_delta_pp"] is None


def test_memory_pressure_is_fail_closed():
    for n in (None, 0, MIN_AVAILABLE_BYTES - 1, True):
        with pytest.raises(RuntimeError):
            admit_research(n)
    admit_research(MIN_AVAILABLE_BYTES)


def test_sampler_is_opt_in_and_bounded():
    calls = 0
    def stable_memory():
        nonlocal calls
        calls += 1
        return (4_000_000_000 - calls * 1000, calls * 10000)
    sampler = MemorySampler(sample=stable_memory, interval=2)
    assert sampler.sample_count == 0
    with sampler as monitor:
        assert monitor is sampler
        assert monitor.sample_count >= 1
    assert sampler.sample_count >= 2
    report = sampler.report()
    assert report["peak_python_rss_mib"] is not None
    assert report["min_system_available_mib"] < 4000
    assert "Ollama" in report["notes"]


def test_sampler_tolerates_missing_telemetry():
    def absent():
        raise OSError("data unavailable")
    sampler = MemorySampler(sample=absent)
    with sampler:
        pass
    assert sampler.report()["samples"] == 0
    with pytest.raises(ValueError):
        MemorySampler(interval=0.01)
