"""Task diagnosis never confuses completed planning with achieved goals."""
import pytest

from core.task_health import task_health


def record(state, *, goal_contract=None, verdict=None, steps=None, **extra):
    return {
        "state": state,
        "steps": steps if steps is not None else [],
        "goal_contract": goal_contract,
        "goal_verdict": verdict,
        **extra,
    }


def verified_step(tool="write_file"):
    return {"tool": tool, "ok": True, "verified": True}


def test_goal_success_requires_finished_state_and_explicit_verified_contract():
    contract = {"kind": "file_bundle", "items": []}  # Pure diagnostics need no path data.
    passed = {"status": "VERIFIED", "reason": "all_files_verified", "kind": "file_bundle"}
    result = task_health(record("PLANNING_FINISHED", goal_contract=contract,
                                verdict=passed, steps=[verified_step()]))
    assert result["status"] == "GOAL_VERIFIED"
    assert result["goal_verified"] is True
    assert result["steps_verified"] == 1
    assert "path" not in repr(result)


def test_model_claim_of_success_without_contract_is_only_a_report():
    result = task_health(record("PLANNING_FINISHED", steps=[verified_step()]))
    assert result["status"] == "NO_GOAL_CONTRACT"
    assert result["goal_verified"] is False


def test_partial_goal_is_unverified_despite_successful_tools():
    result = task_health(record("PLANNING_FINISHED", goal_contract={"kind": "file_bundle"},
                                verdict={"status": "UNVERIFIED", "reason": "verified_1_of_2"},
                                steps=[verified_step()]))
    assert result["status"] == "GOAL_UNVERIFIED"
    assert result["goal_verified"] is False


def test_inflight_never_allows_auto_resume_even_if_older_verdict_passed():
    result = task_health(record("WAITING_REVIEW", uncertain=True, inflight="write_file",
                                goal_contract={"kind": "file_bundle"},
                                verdict={"status": "VERIFIED"}, steps=[verified_step()]))
    assert result["status"] == "NEEDS_MANUAL_REVIEW"
    assert result["requires_manual_review"]
    assert result["can_offer_resume"] is False


def test_paused_can_offer_manual_resume_only_if_no_secrets_or_unknowns():
    clean = record("PAUSED", steps=[verified_step()])
    assert task_health(clean)["can_offer_resume"]
    assert not task_health({**clean, "redacted": True})["can_offer_resume"]
    assert not task_health({**clean, "uncertain": True})["can_offer_resume"]


def test_failed_actions_and_resource_pressure_have_distinct_guidance():
    failed = record("FAILED", steps=[
        {"tool": "read_file", "ok": False, "verified": False},
        {"tool": "read_file", "ok": False, "verified": None},
    ])
    output = task_health(failed)
    assert output["steps_failed"] == 2
    assert output["consecutive_tool_failures"] == 2
    assert output["status"] == "INTERRUPTED"
    paused = task_health(record("RESOURCE_PRESSURE"))
    assert paused["status"] == "RESOURCE_PAUSED"
    assert paused["can_offer_resume"]


@pytest.mark.parametrize("invalid", [
    None, "", [], {"state": "ACT", "steps": "not steps"},
    {"state": "ACT", "steps": [{}] * 49},
])
def test_invalid_diagnostics_fail_safe(invalid):
    with pytest.raises(ValueError):
        task_health(invalid)


def test_task_health_exposes_no_private_args_outputs_or_file_paths():
    secret = "PASSWORD-NEVER-LEAK"
    task = record("FAILED", steps=[{
        "tool": "write_file", "params": {"path": "/user/private.txt", "content": secret},
        "ok": False, "verified": False, "output": f"password={secret}",
    }])
    report = task_health(task)
    assert secret not in repr(report)
    assert "/user/private.txt" not in repr(report)
    assert "password" not in repr(report).lower()


def test_corrupt_contract_kind_does_not_leak_into_diagnostics():
    secret = "PRIVATE-CONTRACT-PATH"
    output = task_health(record("FAILED", goal_contract={"kind": secret}))
    assert output["contract_kind"] is None
    assert secret not in repr(output)
