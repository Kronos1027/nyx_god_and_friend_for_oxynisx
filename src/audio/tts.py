"""Nyx — audio/tts.py (Síntese de Voz Local com Kokoro ONNX + fallback SAPI5)

Hierarquia de backends:
  1. Kokoro ONNX  — voz pf_dora (feminina, fofa, pt-BR), 82M params, sem GPU
  2. SAPI5        — fallback nativo Windows (Microsoft Maria)

Recursos:
  - Fila de fala com cancelamento imediato (stop_current())
  - Limpeza de markdown/código antes da síntese
  - Thread daemon desacoplada — nunca bloqueia a UI
  - Download automático dos modelos Kokoro na primeira execução
"""

from __future__ import annotations

import logging
import queue
import re
import sys
import threading
from contextlib import contextmanager
from app_paths import user_data_dir

log = logging.getLogger(__name__)

# Caminho base dos modelos (na unidade E: do projeto)
_BASE_DIR = user_data_dir()
_MODELS_DIR = _BASE_DIR / "models" / "kokoro"
_KOKORO_ONNX = _MODELS_DIR / "kokoro-v1.0.onnx"
_KOKORO_VOICES = _MODELS_DIR / "voices-v1.0.bin"

# Voz padrão — pf_dora: feminina, fofa, pt-BR
KOKORO_VOICE = "pf_dora"
KOKORO_LANG = "pt-br"


def _clean_text_for_speech(text: str) -> str:
    """Remove código, links, emojis e símbolos para pronúncia natural."""
    t = re.sub(r"```[\s\S]*?```", "", text)            # blocos de código
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)   # links markdown
    t = re.sub(r"`[^`]*`", "", t)                       # inline code
    t = re.sub(r"(https?://\S+|file:///\S+)", "", t)   # URLs
    t = re.sub(r"[\U00010000-\U0010ffff]", "", t)      # emojis
    t = re.sub(r"[#\(\)\{\}<>\|\\]", "", t)            # símbolos markdown
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _download_kokoro_models() -> bool:
    """Baixa os modelos Kokoro se não existirem. Retorna True em sucesso."""
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    need_onnx = not _KOKORO_ONNX.exists()
    need_voices = not _KOKORO_VOICES.exists()

    if not need_onnx and not need_voices:
        return True

    log.info("Baixando modelos Kokoro TTS (primeira execução)...")
    try:
        import urllib.request

        base_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
        if need_onnx:
            url = f"{base_url}/kokoro-v1.0.onnx"
            log.info(f"Baixando {_KOKORO_ONNX.name}...")
            urllib.request.urlretrieve(url, str(_KOKORO_ONNX))
        if need_voices:
            url = f"{base_url}/voices-v1.0.bin"
            log.info(f"Baixando {_KOKORO_VOICES.name}...")
            urllib.request.urlretrieve(url, str(_KOKORO_VOICES))
        log.info("Modelos Kokoro baixados com sucesso.")
        return True
    except Exception as exc:
        log.warning(f"Falha ao baixar modelos Kokoro: {exc}")
        return False


class _KokoroBackend:
    """Backend Kokoro ONNX — leve, offline, voz pf_dora pt-BR."""

    def __init__(self) -> None:
        self._kokoro = None
        self._available: bool | None = None  # None = não testado ainda

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            if not _download_kokoro_models():
                self._available = False
                return False
            from kokoro_onnx import Kokoro  # type: ignore
            self._kokoro = Kokoro(str(_KOKORO_ONNX), str(_KOKORO_VOICES))
            self._available = True
            log.info("Kokoro TTS iniciado com voz pf_dora (pt-BR).")
        except Exception as exc:
            log.warning(f"Kokoro TTS indisponível: {exc}")
            self._available = False
        return self._available

    def speak(self, text: str, stop_event: threading.Event) -> None:
        """Sintetiza e reproduz via sounddevice (streaming direto, sem arquivo)."""
        try:
            import sounddevice as sd

            samples, sample_rate = self._kokoro.create(
                text, voice=KOKORO_VOICE, speed=1.1, lang=KOKORO_LANG
            )
            if stop_event.is_set():
                return
            # Reprodução direta do array numpy
            sd.play(samples, samplerate=sample_rate, blocking=False)
            while sd.get_stream().active:
                if stop_event.is_set():
                    sd.stop()
                    return
                stop_event.wait(timeout=0.05)
            sd.wait()
        except Exception as exc:
            log.warning(f"Erro no Kokoro speak: {exc}")


class _Sapi5Backend:
    """Backend SAPI5 nativo Windows — fallback silencioso."""

    def speak(self, text: str, stop_event: threading.Event) -> None:
        if sys.platform != "win32":
            return
        try:
            import pythoncom
            import win32com.client  # type: ignore

            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Rate = 1

            voices = speaker.GetVoices()
            for i in range(voices.Count):
                desc = voices.Item(i).GetDescription()
                if "Portuguese" in desc or "Maria" in desc or "Brazil" in desc:
                    speaker.Voice = voices.Item(i)
                    break

            if not stop_event.is_set():
                speaker.Speak(text, 1 | 16)  # async, plain text
                while not speaker.WaitUntilDone(50):
                    if stop_event.is_set():
                        speaker.Speak("", 1 | 2 | 16)  # purge pending speech
                        break
        except Exception as exc:
            log.warning(f"Erro no TTS SAPI5: {exc}")
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass


class TextToSpeech:
    """Motor de síntese de voz com fila e cancelamento imediato.

    Hierarquia: Kokoro ONNX (pf_dora, pt-BR) → SAPI5 (Maria, Windows)
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        # Bound pending speech so bursts of responses cannot grow RAM forever.
        self._queue: queue.Queue[tuple[int, str] | None] = queue.Queue(maxsize=8)
        self._state_lock = threading.RLock()
        self._generation = 0
        self._current_stop = None
        self._idle = threading.Event()
        self._idle.set()
        self._paused = 0
        self._closed = False
        self._kokoro = _KokoroBackend()
        self._sapi5 = _Sapi5Backend()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="nyx-tts"
        )
        self._worker_thread.start()

    def _worker_loop(self) -> None:
        """Loop de consumo da fila de falas."""
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                generation, text = item
                with self._state_lock:
                    if self._closed or self._paused or generation != self._generation:
                        continue
                    stop = threading.Event()
                    self._current_stop = stop
                    self._idle.clear()
                try:
                    self._synthesize(text, stop)
                except Exception:
                    log.exception("Falha na fala; worker continua disponível")
                finally:
                    with self._state_lock:
                        self._current_stop = None
                        self._idle.set()
            finally:
                self._queue.task_done()

    def _synthesize(self, text: str, stop: threading.Event) -> None:
        """Escolhe o backend e sintetiza o texto."""
        if stop.is_set():
            return
        available = self._kokoro.is_available()
        if stop.is_set():
            return
        if available:
            self._kokoro.speak(text, stop)
        elif sys.platform == "win32":
            self._sapi5.speak(text, stop)

    def speak(self, text: str) -> None:
        """Enfileira texto para síntese assíncrona."""
        if not self.enabled or not text:
            return
        clean = _clean_text_for_speech(text[:12000])[:3000]
        if not clean:
            return
        with self._state_lock:
            if self._closed or self._paused:
                return
            item = (self._generation, clean)
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    pass
                self._queue.put_nowait(item)

    def stop_current(self) -> None:
        """Para a fala atual imediatamente e limpa a fila."""
        with self._state_lock:
            self._generation += 1
            if self._current_stop is not None:
                self._current_stop.set()
            while True:
                try:
                    item = self._queue.get_nowait()
                    self._queue.task_done()
                    if item is None:
                        self._queue.put_nowait(None)
                        break
                except queue.Empty:
                    break

    @contextmanager
    def microphone_session(self, timeout: float = 3.0):
        """Suppress new speech and wait for playback to stop before recording."""
        with self._state_lock:
            if self._closed:
                raise RuntimeError("A saída de voz está encerrada.")
            self._paused += 1
            self.stop_current()
        try:
            if not self._idle.wait(timeout):
                raise TimeoutError("A fala ainda está encerrando. Tente o microfone novamente.")
            yield
        finally:
            with self._state_lock:
                self._paused -= 1

    def shutdown(self) -> None:
        """Encerra o worker de forma limpa."""
        with self._state_lock:
            if not self._closed:
                self._closed = True
                self.stop_current()
                self._queue.put_nowait(None)
        self._worker_thread.join(timeout=3.0)
