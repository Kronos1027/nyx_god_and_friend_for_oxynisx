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
                speaker.Speak(text)
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
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=8)
        self._stop_event = threading.Event()
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
            if item is None:  # sinal de encerramento
                break
            if not self._stop_event.is_set():
                self._synthesize(item)
            self._queue.task_done()

    def _synthesize(self, text: str) -> None:
        """Escolhe o backend e sintetiza o texto."""
        stop = threading.Event()
        # Compartilha o stop_event global com o backend
        # para responder a stop_current()
        self._current_stop = stop

        def _watch_global():
            """Propaga o stop_event global para o stop local."""
            while not self._stop_event.is_set() and not stop.is_set():
                stop.wait(timeout=0.05)
            stop.set()

        watcher = threading.Thread(target=_watch_global, daemon=True)
        watcher.start()

        try:
            if self._kokoro.is_available():
                self._kokoro.speak(text, stop)
            elif sys.platform == "win32":
                self._sapi5.speak(text, stop)
        finally:
            stop.set()
            self._stop_event.clear()

    def speak(self, text: str) -> None:
        """Enfileira texto para síntese assíncrona."""
        if not self.enabled or not text:
            return
        clean = _clean_text_for_speech(text)
        if not clean:
            return
        try:
            self._queue.put_nowait(clean)
        except queue.Full:
            # Keep the newest conversational reply; stale queued speech is less useful.
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(clean)
            except queue.Full:
                log.debug("Fila de TTS permaneceu cheia; fala descartada.")

    def stop_current(self) -> None:
        """Para a fala atual imediatamente e limpa a fila."""
        self._stop_event.set()
        # Esvazia fila
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        """Encerra o worker de forma limpa."""
        self.stop_current()
        self._queue.put(None)
        self._worker_thread.join(timeout=3.0)
