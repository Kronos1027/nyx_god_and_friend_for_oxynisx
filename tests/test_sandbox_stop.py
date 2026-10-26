"""Unit coverage for races between job enumeration and OpenProcess."""

import os

import pytest

from core.windows_sandbox import stop_job

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows API errors")


@pytest.mark.parametrize("code", [87, 5])
def test_exited_pid_is_tolerated_but_access_denied_is_not(monkeypatch, code):
    import pywintypes
    import win32api
    import win32job

    terminated = []
    job = object()

    def query(_job, kind):
        if kind == win32job.JobObjectExtendedLimitInformation:
            return {"BasicLimitInformation": {"LimitFlags": 0}}
        return [12345]

    def open_process(*_args):
        raise pywintypes.error(code, "OpenProcess", "fixture")

    monkeypatch.setattr(win32job, "QueryInformationJobObject", query)
    monkeypatch.setattr(win32job, "SetInformationJobObject", lambda *_: None)
    monkeypatch.setattr(win32job, "TerminateJobObject", lambda *args: terminated.append(args))
    monkeypatch.setattr(win32api, "OpenProcess", open_process)
    if code == 87:
        stop_job(job, 124)
    else:
        with pytest.raises(pywintypes.error) as failure:
            stop_job(job, 124)
        assert failure.value.winerror == 5
    assert terminated and all(args == (job, 124) for args in terminated)
