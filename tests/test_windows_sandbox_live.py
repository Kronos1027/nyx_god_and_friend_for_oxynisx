"""Opt-in LPAC acceptance. All candidate/probe code runs inside the LPAC.

Only temporary fixture files, a fixture registry key, and an owned TCP listener
are used as forbidden targets. Never read personal files or clipboard contents.
"""

import json
import os
from pathlib import Path
import shutil
import socket
import sys
import time
from uuid import uuid4

import pytest

from core.windows_sandbox import profile, run_lpac

pytestmark = pytest.mark.skipif(
    os.name != "nt" or os.environ.get("NYX_TEST_SANDBOX") != "1",
    reason="real Windows LPAC fixture opt-in",
)


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory):
    base = tmp_path_factory.mktemp("lpac-acceptance")
    staging = base / "isolated"
    runtime, workspace = staging / "python", staging / "work"
    runtime.mkdir(parents=True)
    workspace.mkdir()
    installed = Path(sys.base_prefix)
    for path in installed.iterdir():
        if path.is_file() and path.suffix.lower() in {".exe", ".dll"}:
            shutil.copy2(path, runtime / path.name)
    for name in ("Lib", "DLLs"):
        shutil.copytree(
            installed / name,
            runtime / name,
            ignore=shutil.ignore_patterns(
                "site-packages",
                "__pycache__",
                "test",
                "tests",
                "idlelib",
                "tkinter",
                "ensurepip",
                "turtledemo",
            ),
        )
    with profile(base / "journal") as container:
        container.grant(staging, staging)
        container.grant(staging, workspace, writable=True)

        def run(script, **kwargs):
            return run_lpac(
                container,
                runtime / "python.exe",
                ["-I", "-S", "-X", "utf8", "-c", script],
                workspace,
                diagnostic_registry_read=True,
                **kwargs,
            )

        yield run, base, runtime, workspace


def result_json(result):
    assert result["state"] == "exited", result
    assert result["returncode"] == 0, result
    assert all(result["isolation"].values()), result
    return json.loads(result["output"])


def test_python_can_compute_and_write_only_own_workspace(sandbox):
    run, _, _, workspace = sandbox
    result = run(
        "from pathlib import Path; import json; Path('result.txt').write_text(str(28+68)); print(json.dumps({'sum':28+68}))"
    )
    assert result_json(result) == {"sum": 96}
    assert (workspace / "result.txt").read_text() == "96"


def test_external_fixture_read_write_and_runtime_mutation_denied(sandbox):
    run, base, runtime, _ = sandbox
    outside = base / "outside-private.txt"
    outside.write_text("fixture-private-value")
    targets = [(str(outside), "r"), (str(outside), "w"), (str(runtime / "injected.py"), "w")]
    result = run(f"""
import json
results = []
for path, mode in {targets!r}:
    try:
        with open(path, mode) as stream:
            stream.read() if mode == 'r' else stream.write('forbidden')
        results.append('allowed')
    except OSError as error:
        results.append({{'errno':error.errno, 'type':type(error).__name__}})
print(json.dumps(results))
""")
    assert result_json(result) == [{"errno": 13, "type": "PermissionError"}] * 3
    assert outside.read_text() == "fixture-private-value"
    assert not (runtime / "injected.py").exists()


def test_parent_environment_is_not_inherited(sandbox, monkeypatch):
    run, *_ = sandbox
    monkeypatch.setenv("NYX_PRIVATE_FIXTURE_SECRET", "synthetic-value")
    assert (
        result_json(
            run("import os,json; print(json.dumps(os.getenv('NYX_PRIVATE_FIXTURE_SECRET')))")
        )
        is None
    )


def test_private_registry_fixture_is_denied_with_registry_read_capability(sandbox):
    import winreg
    import win32api
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), 8)
    try:
        user_sid = win32security.ConvertSidToStringSid(
            win32security.GetTokenInformation(token, 1)[0]
        )
    finally:
        token.Close()

    run, *_ = sandbox
    key_path = "Software\\NyxSandboxAcceptance\\" + uuid4().hex
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "fixture", 0, winreg.REG_SZ, "synthetic-private")
    try:
        result = run(f"""
import json, winreg
results = []
for root, path in [(winreg.HKEY_CURRENT_USER, {key_path!r}), (winreg.HKEY_USERS, {str(user_sid + chr(92) + key_path)!r})]:
    try:
        with winreg.OpenKey(root, path) as key:
            value = winreg.QueryValueEx(key, 'fixture')[0]
    except OSError as error:
        value = error.winerror
    results.append(value)
print(json.dumps(results))
""")
        values = result_json(result)
        assert len(values) == 2 and all(value in (2, 5) for value in values)
    finally:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)


def test_loopback_and_external_network_denied(sandbox):
    run, *_ = sandbox
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        port = listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            connection, _ = listener.accept()
            connection.close()
        result = run(f"""
import socket, json
results = []
for address in [('127.0.0.1', {port}), ('203.0.113.1', 9)]:
    try:
        with socket.socket() as connection:
            connection.settimeout(1)
            connection.connect(address)
            results.append('allowed')
    except OSError as error:
        results.append(error.winerror)
print(json.dumps(results))
""")
        assert result_json(result) == [10013, 10013]


def test_access_to_host_process_denied(sandbox):
    run, *_ = sandbox
    result = run(f"""
import _winapi, json
try:
    handle = _winapi.OpenProcess(0x1f0fff, False, {os.getpid()})
    _winapi.CloseHandle(handle)
    value = {{'opened': True}}
except OSError as error:
    value = {{'opened':False, 'error':error.winerror}}
print(json.dumps(value))
""")
    assert result_json(result) == {"opened": False, "error": 5}


def test_timeout_and_cancellation_terminate_owned_process(sandbox):
    import psutil

    run, *_ = sandbox
    result = run("import time; time.sleep(60)", timeout=1)
    assert result["state"] == "timed_out"
    assert result["seconds"] < 3
    assert not psutil.pid_exists(result["pid"])
    started = time.monotonic()
    result = run("import time; time.sleep(60)", cancelled=lambda: time.monotonic() - started > 0.3)
    assert result["state"] == "cancelled"
    assert result["seconds"] < 3
    assert not psutil.pid_exists(result["pid"])


def test_output_and_memory_are_bounded(sandbox):
    run, *_ = sandbox
    output = run("while True: print('x'*1000, flush=True)", output_limit=4096)
    assert output["state"] == "output_limit"
    assert len(output["output"]) == 4096
    memory = run("value = bytearray(300*1024*1024)", memory_mib=64)
    assert memory["returncode"] != 0
    assert "MemoryError" in memory["output"], memory
    assert memory["peak_job_memory"] <= 64 * 1048576


def test_cpu_hard_cap_reduces_real_busy_loop(sandbox, record_property):
    run, *_ = sandbox
    cpus = os.cpu_count() or 1
    if cpus > 32:
        pytest.skip("Single busy-loop measurement requires <=32 logical CPUs")
    result = run("""
import time, json
started = time.monotonic()
cpu = time.process_time()
iterations = 0
while time.monotonic() - started < 1.5:
    iterations += 1
print(json.dumps({'cpu': time.process_time()-cpu, 'wall': time.monotonic()-started,
                  'iterations': iterations}))
""", cpu_percent=1, timeout=10)
    measured = result_json(result)
    assert measured["iterations"] > 0
    assert measured["cpu"] < measured["wall"] * cpus * 0.01 * 1.8 + 0.05, measured
    assert result["limits"]["cpu_percent"] == 1
    assert result["job_user_seconds"] + result["job_kernel_seconds"] > 0
    record_property("cpu_cap_measurement", json.dumps({"logical_cpus": cpus, **measured}))


def test_concurrent_process_limit_and_breakaway_denied(sandbox):
    run, *_ = sandbox
    result = run("""
import subprocess, sys, json
children, errors = [], []
for index in range(6):
    try:
        child = subprocess.Popen([sys.executable, '-I', '-S', '-c', 'import time; time.sleep(3)'])
        children.append(child.pid)
    except OSError as error:
        errors.append(error.winerror)
print(json.dumps({'children': children, 'errors': errors}), flush=True)
""", process_limit=2)
    measured = result_json(result)
    assert len(measured["children"]) == 1, measured
    assert len(measured["errors"]) == 5, measured
    assert result["limits"]["processes"] == 2
    escaped = run("""
import subprocess, sys, json
try:
    child = subprocess.Popen([sys.executable, '-I', '-S', '-c', 'pass'], creationflags=0x01000000)
    child.wait(timeout=2)
    result = {'escaped': True}
except OSError as error:
    result = {'escaped': False, 'error': error.winerror}
print(json.dumps(result))
""")
    assert result_json(escaped) == {"escaped": False, "error": 5}


def test_child_process_does_not_survive_root_exit(sandbox):
    import _winapi

    run, *_ = sandbox
    result = run("""
import subprocess, sys, json
child = subprocess.Popen([sys.executable, '-I', '-S', '-c', 'import time; time.sleep(60)'])
print(json.dumps({'pid': child.pid}), flush=True)
""")
    value = result_json(result)
    try:
        handle = _winapi.OpenProcess(0x100000 | 0x1000, False, value["pid"])
    except OSError as error:
        assert error.winerror == 87  # process object is already gone
    else:
        try:
            assert _winapi.WaitForSingleObject(handle, 0) == 0, "Descendant is still running"
        finally:
            _winapi.CloseHandle(handle)


def test_acl_grants_reject_nested_hardlink_before_mutation(tmp_path):
    from core.windows_sandbox import LPACProfile

    staging = tmp_path / "staging"
    staging.mkdir()
    original = tmp_path / "private.txt"
    original.write_text("outside")
    os.link(original, staging / "linked.txt")
    with profile(tmp_path / "journal") as container:
        with pytest.raises(ValueError, match="Links/reparse"):
            LPACProfile.grant(container, staging, staging)


@pytest.mark.parametrize("mode", ["created", "running"])
def test_supervisor_crash_kills_job_and_next_open_recovers_profile(sandbox, tmp_path, mode):
    import _winapi
    import subprocess
    from core.sandbox_journal import SandboxJournal

    _, _, runtime, _ = sandbox
    workspace = tmp_path / "work"
    workspace.mkdir()
    state, proof = tmp_path / "journal", tmp_path / "proof.json"
    helper = Path(__file__).resolve().parents[1] / "tools" / "sandbox_crash_fixture.py"
    crashed = subprocess.run(
        [sys.executable, str(helper), mode, str(runtime), str(workspace), str(state), str(proof)],
        capture_output=True,
        timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert crashed.returncode == 7, crashed.stderr.decode(errors="replace")
    evidence = json.loads(proof.read_text(encoding="utf-8"))
    pids = [evidence["pid"]]
    if mode == "running":
        ready = json.loads((workspace / "ready.json").read_text())
        assert ready["pid"] == evidence["pid"]
        pids.append(ready["child"])
    else:
        assert not (workspace / "ready.json").exists()
    for pid in pids:
        try:
            handle = _winapi.OpenProcess(0x100000 | 0x1000, False, pid)
        except OSError as error:
            assert error.winerror == 87
        else:
            try:
                assert (
                    _winapi.WaitForSingleObject(handle, 2000) == 0
                ), "Job survived supervisor crash"
            finally:
                _winapi.CloseHandle(handle)
    old_storage = Path(evidence["storage"])
    assert old_storage.exists(), "Profile should remain for crash recovery"
    with SandboxJournal(state) as journal:
        assert journal.pending() == [evidence["profile"]]
    with profile(state) as recovered:
        assert not old_storage.parent.exists()
        assert recovered.journal.pending() == [recovered.name]
    with SandboxJournal(state) as journal:
        assert journal.pending() == []


def test_os_profile_cleanup_does_not_follow_directory_junction(tmp_path):
    import _winapi

    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "preserve.txt"
    sentinel.write_text("owned fixture, preserve")
    with profile(tmp_path / "journal") as container:
        private = container.api.profile_directory(container.name)
        junction = private / "outside-junction"
        _winapi.CreateJunction(str(outside), str(junction))
        assert (junction / "preserve.txt").exists()
    assert sentinel.read_text() == "owned fixture, preserve"
    assert not private.parent.exists()


def test_candidate_cannot_read_or_corrupt_supervisor_journal(sandbox):
    run, base, _, _ = sandbox
    database = base / "journal" / "profiles.sqlite3"
    before = database.read_bytes()
    result = run(f"""
import json
results = []
for mode in ('r', 'w'):
    try:
        with open({str(database)!r}, mode) as stream:
            stream.read() if mode == 'r' else stream.write('corruption')
        results.append('allowed')
    except OSError as error:
        results.append(error.errno)
print(json.dumps(results))
""")
    assert result_json(result) == [13, 13]
    assert database.read_bytes() == before


def test_multifile_project_copy_test_fix_and_export_inside_lpac(sandbox, tmp_path):
    import zipfile
    from core.project_snapshot import ProjectSnapshot

    run, _, _, workspace = sandbox
    source = tmp_path / "source"
    source.mkdir()
    (source / "ops.py").write_text("def add(a, b):\n    return a-b\n")
    (source / "test_ops.py").write_text(
        "import unittest\nfrom ops import add\nclass SumTest(unittest.TestCase):\n"
        "    def test_sum(self):\n        self.assertEqual(add(28, 68), 96)\n"
    )

    def evaluate(directory):
        return run(f"""
import sys, unittest
sys.path.insert(0, {str(directory)!r})
suite = unittest.defaultTestLoader.discover({str(directory)!r}, pattern='test_*.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
""")

    initial = ProjectSnapshot.capture(source)
    first = initial.write_new_directory(workspace / "project-failing")
    failed = evaluate(first)
    assert failed["state"] == "exited" and failed["returncode"] == 1, failed
    assert "AssertionError" in failed["output"]
    # This fixture deliberately supplies the correction; it is not an LLM test.
    (source / "ops.py").write_text("def add(a, b):\n    return a+b\n")
    corrected = ProjectSnapshot.capture(source)
    second = corrected.write_new_directory(workspace / "project-corrected")
    passed = evaluate(second)
    assert passed["state"] == "exited" and passed["returncode"] == 0, passed
    assert "Ran 1 test" in passed["output"] and "OK" in passed["output"]
    result = ProjectSnapshot.capture(second)  # child/job have already terminated
    archive = tmp_path / "result.zip"
    result.export_zip(archive)
    with zipfile.ZipFile(archive) as exported:
        assert set(exported.namelist()) == {"ops.py", "test_ops.py"}
        assert exported.read("ops.py") == (source / "ops.py").read_bytes()
    assert initial.manifest()["sha256"] != result.manifest()["sha256"]
    assert corrected.manifest()["sha256"] == result.manifest()["sha256"]
