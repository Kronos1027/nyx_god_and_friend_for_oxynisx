"""Protocol fault injection against an owned trusted helper, not UIA proof."""
import subprocess
import sys
import threading
import time

import pytest

from core.operation_control import OperationControl
from tools.windows_client import AutomationInterrupted, WindowsAutomationClient


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("verb,params,unknown", [
    ("inspect", {}, False), ("act", {"action": "click_element"}, True)])
def test_hung_helper_is_terminated_without_replay(tmp_path, monkeypatch, cancel, verb, params, unknown):
    helper = tmp_path / "blocked_helper.py"
    helper.write_text("import sys,time\nsys.stdin.readline()\ntime.sleep(20)\n", encoding="utf-8")
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
