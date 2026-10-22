import sys
from types import SimpleNamespace

import numpy as np
import pytest

from audio.stt import SpeechToText
from core import runtime_budget as budget


@pytest.fixture
def voice(tmp_path, monkeypatch):
    monkeypatch.setattr(SpeechToText, "_find_best_input_device", lambda self: None)
    monkeypatch.setattr(budget, "resource_snapshot", lambda: budget.ResourceSnapshot(12 * budget.GIB, 12 * budget.GIB, 8 * budget.GIB))
    return SpeechToText(download_root=str(tmp_path))


def test_voice_uses_cpu_int8_and_holds_shared_slot_through_lazy_segments(voice, monkeypatch):
    calls = []
    class Model:
        def __init__(self, name, **kwargs):
            assert budget.INFERENCE_GATE.telemetry()["active"] == 1
            calls.append(kwargs)
        def transcribe(self, audio, **kwargs):
            assert audio.dtype == np.float32
            def segments():
                assert budget.INFERENCE_GATE.telemetry()["active"] == 1
                yield SimpleNamespace(text=" Olá ")
                yield SimpleNamespace(text=" Nyx ")
            return segments(), None
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    assert voice.transcribe_array(np.zeros(16000)) == "Olá Nyx"
    assert voice.transcribe_array(np.zeros(16000)) == "Olá Nyx"
    assert len(calls) == 1
    assert calls[0]["device"] == "cpu"
    assert calls[0]["compute_type"] == "int8"
    assert 1 <= calls[0]["cpu_threads"] <= 4
    assert calls[0]["num_workers"] == 1
    assert budget.INFERENCE_GATE.telemetry()["active"] == 0


def test_low_ram_refuses_before_model_constructor(voice, monkeypatch):
    monkeypatch.setattr(budget, "resource_snapshot", lambda: budget.ResourceSnapshot(budget.GIB, None, None))
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=lambda *a, **k: pytest.fail("model loaded")))
    with pytest.raises(budget.InferencePressureError, match="RAM"):
        voice.transcribe_array(np.zeros(16000, dtype=np.float32))
    assert budget.INFERENCE_GATE.telemetry()["active"] == 0


def test_cached_model_still_requires_headroom(voice, monkeypatch):
    voice._model = SimpleNamespace(transcribe=lambda *a, **k: pytest.fail("transcription started"))
    voice._loaded_device = "cpu"
    monkeypatch.setattr(budget, "resource_snapshot", lambda: budget.ResourceSnapshot(budget.GIB, None, None))
    with pytest.raises(budget.InferencePressureError):
        voice.transcribe_array(np.zeros(16000))


def test_cpu_constructor_failure_is_not_retried(voice, monkeypatch):
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs)
        raise RuntimeError("broken model")
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=fail))
    with pytest.raises(RuntimeError, match="broken model"):
        voice.transcribe_array(np.zeros(16000))
    assert len(calls) == 1
    assert budget.INFERENCE_GATE.telemetry()["active"] == 0


def test_lazy_decoder_failure_releases_slot(voice):
    def segments():
        raise RuntimeError("decoder failure")
        yield
    voice._loaded_device = "cpu"
    voice._model = SimpleNamespace(transcribe=lambda *a, **k: (segments(), None))
    with pytest.raises(RuntimeError, match="decoder failure"):
        voice.transcribe_array(np.zeros(16000))
    assert budget.INFERENCE_GATE.telemetry()["active"] == 0


@pytest.mark.parametrize("audio", [np.zeros((10, 2)), np.zeros(0), np.zeros(480001), np.array([np.nan]), np.array([np.inf]), np.array([1]), "file.wav"])
def test_invalid_audio_is_rejected_without_loading(voice, audio):
    with pytest.raises(ValueError, match="Áudio"):
        voice.transcribe_array(audio)
    assert voice._model is None


@pytest.mark.parametrize("duration,rate", [(31, 16000), (0, 16000), (-1, 16000), (float("nan"), 16000), (4, 48000)])
def test_capture_duration_and_rate_are_bounded(voice, duration, rate):
    with pytest.raises(ValueError):
        voice.record_audio(duration, rate)


def test_explicit_cuda_requires_reserved_vram(voice, monkeypatch):
    voice.device = "cuda"
    monkeypatch.setattr(budget, "resource_snapshot", lambda: budget.ResourceSnapshot(8 * budget.GIB, 12 * budget.GIB, 4 * budget.GIB))
    with pytest.raises(budget.InferencePressureError, match="VRAM"):
        voice.transcribe_array(np.zeros(16000))


def test_cuda_failure_rechecks_ram_before_cpu_fallback(voice, monkeypatch):
    voice.device = "cuda"
    snapshots = iter([budget.ResourceSnapshot(8 * budget.GIB, 12 * budget.GIB, 8 * budget.GIB),
                      budget.ResourceSnapshot(budget.GIB, 12 * budget.GIB, 8 * budget.GIB)])
    monkeypatch.setattr(budget, "resource_snapshot", lambda: next(snapshots))
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs["device"])
        raise RuntimeError("CUDA unavailable")
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=fail))
    with pytest.raises(budget.InferencePressureError, match="RAM"):
        voice.transcribe_array(np.zeros(16000))
    assert calls == ["cuda"]


def test_voice_waits_for_conversation_slot(voice, monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    started = threading.Event()
    gate = budget.InferenceGate()
    monkeypatch.setattr(budget, "INFERENCE_GATE", gate)
    voice._loaded_device = "cpu"
    def transcribe(*args, **kwargs):
        started.set()
        return iter([SimpleNamespace(text="Olá")]), None
    voice._model = SimpleNamespace(transcribe=transcribe)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with gate.slot():
            task = pool.submit(voice.transcribe_array, np.zeros(16000))
            deadline = time.monotonic() + 2
            while not gate.telemetry()["waiting"] and time.monotonic() < deadline:
                time.sleep(0.005)
            assert gate.telemetry()["waiting"] == 1
            assert not started.is_set()
        assert task.result(timeout=2) == "Olá"
