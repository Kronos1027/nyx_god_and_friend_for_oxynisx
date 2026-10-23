import subprocess
import sys

import pytest

from core.context_awareness import ContextAwarenessEngine
from core.process_events import AuthorizedProcessSensor


def test_real_authorized_process_exit_produces_single_event(tmp_path):
    clock = [100.0]
    context = ContextAwarenessEngine(tmp_path / "context.db", clock=lambda: clock[0])
    context.set_permission("processes", True)
    sensor = AuthorizedProcessSensor(context)
    # Trusted fixed fixture; not code supplied by the user or a candidate model.
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        entry = sensor.watch(process.pid)
        assert entry.pid == process.pid
        assert sensor.poll() == []
        process.terminate()
        process.wait(timeout=5)
        clock[0] += 6
        events = sensor.poll()
        assert len(events) == 1
        clock[0] += 6
        assert sensor.poll() == []
        with context.connect() as db:
            row = db.execute("SELECT * FROM context_events").fetchone()
        assert row["kind"] == "process_exited"
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_disabled_sensor_never_accesses_process_api(tmp_path, monkeypatch):
    import psutil
    context = ContextAwarenessEngine(tmp_path / "context.db")
    sensor = AuthorizedProcessSensor(context)
    def forbidden(*args):
        pytest.fail("Process API accessed without permission")
    monkeypatch.setattr(psutil, "Process", forbidden)
    with pytest.raises(PermissionError):
        sensor.watch(1)
    assert sensor.poll() == []
