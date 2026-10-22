import threading
from types import SimpleNamespace
import sys

import pytest

from audio.tts import TextToSpeech, VoiceSettings, _Sapi5Backend


@pytest.fixture
def speech(monkeypatch):
    monkeypatch.setattr("audio.tts._KokoroBackend.is_available", lambda self: True)
    tts = TextToSpeech()
    yield tts
    tts.shutdown()


def test_stop_while_idle_does_not_discard_next_reply(speech):
    spoken = threading.Event()
    speech._kokoro.speak = lambda text, stop, settings: spoken.set()
    speech.stop_current()
    speech.speak("Olá")
    assert spoken.wait(1)


def test_microphone_cancels_playback_and_suppresses_queued_speech(speech):
    started = threading.Event()
    stopped = threading.Event()
    played = []
    def speak(text, stop, settings):
        played.append(text)
        started.set()
        assert stop.wait(2)
        stopped.set()
    speech._kokoro.speak = speak
    speech.speak("Primeira")
    assert started.wait(1)
    speech.speak("Antiga")
    with speech.microphone_session():
        assert stopped.is_set()
        speech.speak("Não falar durante gravação")
        assert speech._queue.empty()
    assert played == ["Primeira"]
    resumed = threading.Event()
    speech._kokoro.speak = lambda text, stop, settings: resumed.set()
    speech.speak("Nova")
    assert resumed.wait(1)


def test_microphone_timeout_never_enters_capture(speech):
    started, release = threading.Event(), threading.Event()
    def uninterruptible(text, stop, settings):
        started.set()
        release.wait(2)
    speech._kokoro.speak = uninterruptible
    speech.speak("Sintetizando")
    assert started.wait(1)
    try:
        with pytest.raises(TimeoutError):
            with speech.microphone_session(timeout=0.01):
                pytest.fail("Capture must not start while playback is active")
        assert speech._paused == 0
    finally:
        release.set()


def test_nested_microphone_sessions_and_exceptions_restore_state(speech):
    with speech.microphone_session():
        with pytest.raises(ValueError):
            with speech.microphone_session():
                raise ValueError("capture failed")
        assert speech._paused == 1
    assert speech._paused == 0


def test_shutdown_is_idempotent_and_rejects_new_speech(speech):
    speech.shutdown()
    speech.shutdown()
    speech.stop_current()
    speech.speak("Late reply")
    assert not speech._worker_thread.is_alive()
    with pytest.raises(RuntimeError):
        with speech.microphone_session():
            pass


def test_synthesis_error_does_not_kill_worker(speech):
    failed, resumed = threading.Event(), threading.Event()
    def fail(text, stop, settings):
        failed.set()
        raise RuntimeError("synthesis failed")
    speech._kokoro.speak = fail
    speech.speak("Teste")
    assert failed.wait(1)
    speech._kokoro.speak = lambda text, stop, settings: resumed.set()
    speech.speak("Nova tentativa")
    assert resumed.wait(1)


def test_speech_length_and_queue_are_bounded(speech):
    started, release = threading.Event(), threading.Event()
    lengths = []
    def speak(text, stop, settings):
        lengths.append(len(text))
        started.set()
        release.wait(2)
    speech._kokoro.speak = speak
    speech.speak("a" * 100000)
    assert started.wait(1)
    for _ in range(100):
        speech.speak("b" * 100000)
    assert speech._queue.qsize() <= 8
    assert lengths == [3000]
    release.set()


def test_sapi_uses_async_plain_text_and_purges_on_cancel(monkeypatch):
    calls = []
    stop = threading.Event()
    def wait(milliseconds):
        assert milliseconds == 50
        stop.set()
        return False
    speaker = SimpleNamespace(GetVoices=lambda: SimpleNamespace(Count=0),
                              Speak=lambda *args: calls.append(args), WaitUntilDone=wait)
    monkeypatch.setitem(sys.modules, "pythoncom", SimpleNamespace(CoInitialize=lambda: None, CoUninitialize=lambda: None))
    client = SimpleNamespace(Dispatch=lambda name: speaker)
    monkeypatch.setitem(sys.modules, "win32com", SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    monkeypatch.setattr("audio.tts.sys.platform", "win32")
    _Sapi5Backend().speak("Olá", stop, VoiceSettings())
    assert calls == [("Olá", 17), ("", 19)]
