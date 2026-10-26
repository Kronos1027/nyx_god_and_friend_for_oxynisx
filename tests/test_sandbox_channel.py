import queue
import os
import time

import pytest

from core.sandbox_channel import SandboxChannel


def test_bounded_input_and_one_use_lifecycle():
    channel = SandboxChannel()
    for _ in range(32):
        channel.send(b"x")
    with pytest.raises(queue.Full):
        channel.send(b"overflow")
    assert channel.take_input() == b"x"
    channel.claim()
    with pytest.raises(ValueError):
        channel.claim()
    channel.finish()
    with pytest.raises(RuntimeError):
        channel.send(b"late")


def test_total_input_budget_survives_consumption():
    channel = SandboxChannel()
    for _ in range(64):
        channel.send(b"x" * 16384)
        assert channel.take_input() is not None
    with pytest.raises(ValueError):
        channel.send(b"one more")


def test_output_backpressure_and_message_validation():
    channel = SandboxChannel()
    for _ in range(32):
        assert channel.deliver(b"test")
    assert not channel.deliver(b"overflow")
    assert channel.receive(0) == b"test"
    for invalid in ("text", b"", b"x" * 16385):
        with pytest.raises(ValueError):
            channel.send(invalid)
    for invalid in (-1, 6, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            channel.receive(invalid)


@pytest.mark.skipif(os.name != "nt", reason="Windows overlapped pipe")
def test_broken_pipe_is_not_left_as_a_pending_write():
    import pywintypes
    from core.sandbox_channel import OverlappedInput
    pipe = OverlappedInput()
    channel = SandboxChannel()
    channel.send(b"after reader closed")
    pipe.release_parent_reader()
    started = time.monotonic()
    try:
        with pytest.raises(pywintypes.error):
            pipe.pump(channel)
        assert pipe.pending is None
    finally:
        pipe.close()
    assert time.monotonic() - started < 1
