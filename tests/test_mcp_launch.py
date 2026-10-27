from dataclasses import replace
import threading
import os

import pytest

from core.mcp_launch import MCPApprovalGate, MCPLaunchPlan
from core.project_snapshot import ProjectSnapshot, SnapshotFile
from core.python_runtime_artifact import PythonRuntimeArtifact


def unit_runtime():
    # Non-executable bytes: these fixtures only exercise review/approval policy.
    return PythonRuntimeArtifact(ProjectSnapshot((SnapshotFile("python.exe", b"unit-exe"),
        SnapshotFile("python311.dll", b"unit-dll"), SnapshotFile("Lib/encodings/__init__.py", b"unit-lib"))),
        "unit fixture")


def plan():
    return MCPLaunchPlan("example", ProjectSnapshot((SnapshotFile("main.py", b"print('approved')"),)),
                         "main.py", (("echo", 0),), "owned fixture", unit_runtime())


@pytest.mark.parametrize("change", [
    {"arguments": ("changed",)}, {"tool_levels": (("echo", 2),)}, {"seconds": 61},
    {"memory_mib": 128}, {"origin": "another origin"}, {"server_id": "other"},
    {"snapshot": ProjectSnapshot((SnapshotFile("main.py", b"print('changed')"),))},
    {"runtime": replace(unit_runtime(), origin="different-runtime-origin")},
    {"runtime": PythonRuntimeArtifact(ProjectSnapshot((SnapshotFile("python.exe", b"changed-exe"),
        SnapshotFile("python311.dll", b"unit-dll"), SnapshotFile("Lib/encodings/__init__.py", b"unit-lib"))),
        "unit fixture")},
])
def test_approval_cannot_authorize_a_different_plan(change):
    original, gate = plan(), MCPApprovalGate()
    token = gate.approve(original, original.review()["approval_digest"])
    with pytest.raises(PermissionError):
        gate.consume(replace(original, **change), token)
    with pytest.raises(PermissionError):
        gate.consume(original, token)  # Failed use also invalidates the ticket.


def test_review_mismatch_expiry_revocation_and_new_process_gate():
    original = plan()
    now = [0]
    gate = MCPApprovalGate(clock=lambda: now[0])
    with pytest.raises(ValueError):
        gate.approve(original, "not-reviewed")
    token = gate.approve(original, original.review()["approval_digest"], lifetime=1)
    now[0] = 1
    with pytest.raises(PermissionError):
        gate.consume(original, token)
    token = gate.approve(original, original.review()["approval_digest"])
    assert gate.revoke(token)
    with pytest.raises(PermissionError):
        gate.consume(original, token)
    token = gate.approve(original, original.review()["approval_digest"])
    with pytest.raises(PermissionError):
        MCPApprovalGate().consume(original, token)


def test_only_one_concurrent_consumer_can_claim_approval():
    original, gate = plan(), MCPApprovalGate()
    token = gate.approve(original, original.review()["approval_digest"])
    results = []
    barrier = threading.Barrier(2)

    def consume():
        barrier.wait()
        try:
            gate.consume(original, token)
            results.append(True)
        except PermissionError:
            results.append(False)

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(2)
    assert sorted(results) == [False, True]


def test_launch_rejects_missing_approval_before_any_filesystem_effect(tmp_path):
    from core.mcp_launch import run_approved_mcp
    with pytest.raises(PermissionError):
        run_approved_mcp(None, tmp_path, plan(), MCPApprovalGate(), "missing", None)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="Windows snapshot capture")
def test_capture_excludes_relocated_dependencies_and_derives_client_policy(tmp_path):
    (tmp_path / "main.py").write_text("pass", encoding="utf-8")
    dependencies = tmp_path / ".local-deps"
    dependencies.mkdir()
    (dependencies / "dependency.py").write_text("not server source", encoding="utf-8")
    captured = MCPLaunchPlan.capture(tmp_path, server_id="example", entrypoint="main.py", tool_levels={"echo": 0},
                                     runtime=unit_runtime())
    assert [item.name for item in captured.snapshot.files] == ["main.py"]
    assert ".local-deps" in captured.snapshot.skipped
    config = captured.client_config()
    assert config.server_id == "example" and config.permission_levels == {"echo": 0}


def test_runtime_is_required_and_path_redirects_are_rejected():
    with pytest.raises(ValueError):
        replace(plan(), runtime=None)
    with pytest.raises(ValueError):
        PythonRuntimeArtifact(ProjectSnapshot((SnapshotFile("python.exe", b"incomplete"),)), "fixture")
    runtime = unit_runtime()
    with pytest.raises(ValueError):
        replace(runtime, snapshot=ProjectSnapshot(runtime.snapshot.files + (SnapshotFile("python311._pth", b"C:\\outside"),)))
