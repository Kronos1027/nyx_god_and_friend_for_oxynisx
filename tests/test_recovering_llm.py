import pytest

from core.llm_client import BackendUnavailable, OfflineLLM
from core.recovering_llm import RecoveringLLM


class Available:
    model = "local-test"
    keep_alive = "5m"

    def generate(self, text, **kwargs):
        return text


def test_recovers_on_later_request_and_preserves_keepalive():
    now = [0]
    calls = []
    def factory():
        calls.append(True)
        return Available()
    client = RecoveringLLM(OfflineLLM(unavailable_reason="No RAM"), factory, clock=lambda: now[0])
    client.keep_alive = 0
    client.generate("hello")
    assert not calls
    now[0] = 31
    assert client.generate("hello") == "hello"
    assert client.model == "local-test"
    assert not client.unavailable_reason
    assert client._client.keep_alive == 0
    client.generate("again")
    assert len(calls) == 1


def test_factory_failure_is_throttled():
    now = [0]
    calls = []
    def factory():
        calls.append(True)
        raise RuntimeError("unavailable")
    client = RecoveringLLM(OfflineLLM(unavailable_reason="offline"), factory, clock=lambda: now[0])
    now[0] = 31
    client.generate("hello")
    client.generate("hello")
    assert len(calls) == 1
    assert client.unavailable_reason


def test_generation_is_never_replayed_on_internal_type_error():
    calls = []
    class Broken(Available):
        def generate(self, text, **kwargs):
            calls.append(text)
            raise TypeError("internal bug")
    client = RecoveringLLM(Broken(), Available)
    with pytest.raises(TypeError):
        client.generate("once")
    assert calls == ["once"]


def test_provider_failure_recovers_after_cooldown():
    now = [0]
    class Broken(Available):
        def generate(self, text, **kwargs):
            raise BackendUnavailable("unavailable")
    client = RecoveringLLM(Broken(), Available, clock=lambda: now[0])
    with pytest.raises(BackendUnavailable):
        client.generate("hello")
    assert client.unavailable_reason
    now[0] = 31
    assert client.generate("again") == "again"
