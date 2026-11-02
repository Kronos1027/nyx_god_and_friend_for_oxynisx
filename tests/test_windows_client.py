"""Protocol fault injection against an owned trusted helper, not UIA proof."""
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from core.operation_control import OperationControl
from tools.windows_client import AutomationInterrupted, WindowsAutomationClient


@pytest.mark.parametrize('reused', [False, True])
def test_foreground_delegation_targets_only_owned_live_helper(monkeypatch, reused):
    from tools import windows_client
    calls = []
    class Allow:
        def __call__(self, pid):
            calls.append(pid)
            return 1
    monkeypatch.setattr(windows_client, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(windows_client.ctypes, 'WinDLL',
                        lambda *a, **k:SimpleNamespace(AllowSetForegroundWindow=Allow()), raising=False)
    client = WindowsAutomationClient(OperationControl())
    assert not client._allow_worker_foreground()
    client._process = SimpleNamespace(pid=42, poll=lambda:None)
    client._worker_pid = 99
    client._owned_pids = {99:100}
    monkeypatch.setattr(windows_client.psutil, 'Process', lambda pid:SimpleNamespace(
        pid=pid,create_time=lambda:101 if reused else 100,is_running=lambda:True))
    try:
        assert client._allow_worker_foreground() == (not reused)
        client._process = SimpleNamespace(pid=43, poll=lambda:0)
        assert not client._allow_worker_foreground()
        assert calls == ([] if reused else [99])
    finally:
        client._process = None
        client._worker_pid = None
        client._owned_pids = {}


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("verb,params,unknown", [
    ("inspect", {}, False), ("act", {"action": "click_element"}, True)])
def test_hung_helper_is_terminated_without_replay(tmp_path, monkeypatch, cancel, verb, params, unknown):
    helper = tmp_path / "blocked_helper.py"
    helper.write_text("import sys,time,json,os\nprint(json.dumps({'ready':True,'pid':os.getpid()}),flush=True)\n"
                      "sys.stdin.readline()\ntime.sleep(20)\n", encoding="utf-8")
    original = subprocess.Popen
    processes = []
    def start(command, **kwargs):
        process = original([sys.executable, "-u", str(helper)], **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr("tools.windows_client.subprocess.Popen", start)
    control = OperationControl()
    client = WindowsAutomationClient(control, timeout=0.4)
    timer = threading.Timer(0.15, control.stop) if cancel else None
    if timer:
        timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(AutomationInterrupted) as error:
            client.call(verb, params)
        assert error.value.outcome_unknown is unknown
        assert time.monotonic() - started < 2
        assert len(processes) == 1 and processes[0].poll() is not None
    finally:
        client.close()
        if timer:
            timer.cancel()
