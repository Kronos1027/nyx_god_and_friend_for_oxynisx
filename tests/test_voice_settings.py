"""Voice preferences: validation, clamping and delivery to the TTS backends."""

import sys
import threading
from types import SimpleNamespace

import pytest

from audio.tts import (
    DEFAULT_SPEED,
    DEFAULT_VOLUME,
    KOKORO_VOICE,
    PT_BR_VOICES,
    TextToSpeech,
    VoiceSettings,
    _Sapi5Backend,
    normalize_speed,
    normalize_voice,
    normalize_volume,
    sapi_rate,
)


def test_voice_names_are_restricted_to_the_installed_pt_br_bundle():
    assert [voice for voice, _ in PT_BR_VOICES] == ["pf_dora", "pm_alex", "pm_santa"]
    assert normalize_voice("pf_dora") == "pf_dora"
    assert normalize_voice(" PM_ALEX ") == "pm_alex"
    assert normalize_voice("af_heart") == KOKORO_VOICE
    assert normalize_voice(None) == KOKORO_VOICE


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0.1, 0.5), (0.7, 0.7), (1.1, 1.1), (5, 2.0), ("abc", DEFAULT_SPEED), (float("nan"), DEFAULT_SPEED)],
)
def test_speed_is_clamped_to_the_kokoro_range(raw, expected):
    assert normalize_speed(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [(-1, 0.0), (0.42, 0.42), (1, 1.0), (9, 1.0), (None, DEFAULT_VOLUME)]
)
def test_volume_is_clamped_between_silence_and_full_scale(raw, expected):
    assert normalize_volume(raw) == expected


def test_voice_settings_normalize_invalid_values_on_construction():
    settings = VoiceSettings(voice="xx_unknown", speed=99, volume=-3)
    assert (settings.voice, settings.speed, settings.volume) == (KOKORO_VOICE, 2.0, 0.0)


@pytest.mark.parametrize(
    ("speed", "expected"), [(0.5, -5), (0.7, -3), (1.0, 0), (1.1, 1), (1.25, 3), (2.0, 10)]
)
def test_sapi_rate_maps_speed_to_the_windows_scale(speed, expected):
    assert sapi_rate(speed) == expected


def test_configure_updates_one_field_and_keeps_the_others():
    tts = TextToSpeech(enabled=False)
    try:
        tts.configure(voice="pm_santa", speed=0.9, volume=0.5)
        tts.configure(volume=0.25)
        assert tts.voice_settings == VoiceSettings("pm_santa", 0.9, 0.25)
    finally:
        tts.shutdown()


def test_configure_rejects_unknown_voice_and_clamps_numbers():
    tts = TextToSpeech(enabled=False)
    try:
        settings = tts.configure(voice="af_heart", speed=3.0, volume=2.0)
        assert settings == VoiceSettings(KOKORO_VOICE, 2.0, 1.0)
    finally:
        tts.shutdown()


def test_synthesis_passes_the_current_settings_to_the_backend(monkeypatch):
    monkeypatch.setattr("audio.tts._KokoroBackend.is_available", lambda self: True)
    tts = TextToSpeech()
    seen, done = [], threading.Event()

    def capture(text, stop, settings):
        seen.append((text, settings))
        done.set()

    tts._kokoro.speak = capture
    try:
        tts.configure(voice="pm_alex", speed=1.3, volume=0.4)
        tts.speak("Teste de voz")
        assert done.wait(2)
    finally:
        tts.shutdown()
    assert seen == [("Teste de voz", VoiceSettings("pm_alex", 1.3, 0.4))]


def test_sapi_backend_applies_volume_and_rate(monkeypatch):
    calls = []
    speaker = SimpleNamespace(
        Rate=None,
        Volume=None,
        GetVoices=lambda: SimpleNamespace(Count=0),
        Speak=lambda *args: calls.append(args),
        WaitUntilDone=lambda milliseconds: True,
    )
    monkeypatch.setitem(
        sys.modules,
        "pythoncom",
        SimpleNamespace(CoInitialize=lambda: None, CoUninitialize=lambda: None),
    )
    client = SimpleNamespace(Dispatch=lambda name: speaker)
    monkeypatch.setitem(sys.modules, "win32com", SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    monkeypatch.setattr("audio.tts.sys.platform", "win32")

    _Sapi5Backend().speak("Olá", threading.Event(), VoiceSettings("pf_dora", 1.25, 0.6))

    assert (speaker.Rate, speaker.Volume) == (3, 60)
    assert calls == [("Olá", 17)]
