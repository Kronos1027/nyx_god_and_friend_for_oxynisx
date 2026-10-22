"""Nyx — audio/stt.py (Fase 3: Transcrição de Áudio com faster-whisper)

Captura de áudio via sounddevice e transcrição rápida local:
- Suporta modelo configurável (base/small/tiny)
- Reconhece o comando de wake word "Ei Nyx" ou captura direta
- Execução não-bloqueante em thread dedicada
"""

from __future__ import annotations

import logging
import math
import os
import re
from pathlib import Path

from app_paths import user_data_dir

log = logging.getLogger(__name__)


class SpeechToText:
    """Reconhecimento de fala local via faster-whisper."""

    def __init__(
        self,
        model_name: str = "tiny",
        device: str = "auto",
        language: str = "pt",
        download_root: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.language = language

        # Native installations use AppData; development uses the project data root.
        base_dir = user_data_dir()
        self.download_root = download_root or str(base_dir / "models" / "whisper")
        os.environ.setdefault("HF_HOME", str(base_dir / "models" / "hf_cache"))
        Path(self.download_root).mkdir(parents=True, exist_ok=True)

        self._model = None
        self._loaded_device = None
        self._input_device_index = self._find_best_input_device()

    @staticmethod
    def _find_best_input_device() -> int | None:
        """Localiza o melhor dispositivo de microfone (priorizando Fifine ou microfones dedicados)."""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            # 1. Procura por microfone USB de alta qualidade (Fifine, etc.)
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = str(dev.get("name", "")).lower()
                    if "fifine" in name and "output" not in name and "alto-falantes" not in name:
                        log.info(f"Microfone detectado: [{idx}] {dev['name']}")
                        return idx
            # 2. Procura qualquer microfone com entrada ativa
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = str(dev.get("name", "")).lower()
                    if "micro" in name:
                        log.info(f"Microfone detectado: [{idx}] {dev['name']}")
                        return idx
        except Exception as exc:
            log.warning(f"Erro ao consultar dispositivos de áudio: {exc}")
        return None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        dev = "cpu" if self.device == "auto" else self.device
        self._admit_model(dev, loading=True)
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                f"faster-whisper não está disponível: {exc}. Instale as dependências de áudio."
            ) from exc

        # CPU int8 leaves the GPU available to the conversational model and avoids
        # importing PyTorch merely to detect a device for CTranslate2.
        compute = "int8" if dev == "cpu" else "float16"
        options = {"download_root": self.download_root,
                   "cpu_threads": min(4, max(1, (os.cpu_count() or 2) // 2)),
                   "num_workers": 1}

        log.info(f"Carregando faster-whisper ({self.model_name}) em {dev} ({compute})...")
        try:
            self._model = WhisperModel(
                self.model_name,
                device=dev,
                compute_type=compute,
                **options,
            )
        except Exception as exc:
            if dev != "cuda":
                raise
            log.warning(f"Falha ao inicializar no dispositivo {dev}: {exc}. Tentando CPU...")
            self._admit_model("cpu", loading=True)
            self._model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8",
                **options,
            )
            dev = "cpu"
        self._loaded_device = dev
        return self._model

    def _admit_model(self, device: str, *, loading: bool) -> None:
        from core.runtime_budget import GIB, InferencePressureError, resource_snapshot

        if device not in {"cpu", "cuda"}:
            raise ValueError("Dispositivo de voz deve ser auto, cpu ou cuda.")
        snapshot = resource_snapshot()
        # Conservative envelopes, not measured peaks; unknown models require 8 GiB.
        family = self.model_name.removesuffix(".en")
        reserve = {"tiny": 1, "base": 1, "small": 2, "medium": 5}.get(family, 8) * GIB
        required_ram = 2 * GIB + (reserve if loading else 0)
        if snapshot.ram_available_bytes is None or snapshot.ram_available_bytes < required_ram:
            raise InferencePressureError("Memória RAM insuficiente para reconhecimento de voz; libere memória e tente novamente.")
        if device == "cuda":
            required_vram = 4 * GIB + (reserve if loading else 0)
            if snapshot.vram_free_bytes is None or snapshot.vram_free_bytes < required_vram:
                raise InferencePressureError("VRAM insuficiente para reconhecimento de voz sem comprometer a conversa.")

    def record_audio(self, duration_seconds: float = 4.0, sample_rate: int = 16000):
        """Grava áudio do microfone usando sounddevice."""
        if not math.isfinite(duration_seconds) or not 0 < duration_seconds <= 30 or sample_rate != 16000:
            raise ValueError("Grave entre 0 e 30 segundos em 16 kHz.")
        import numpy as np
        import sounddevice as sd

        device_idx = self._input_device_index
        log.info(f"Gravando {duration_seconds}s de áudio (dispositivo={device_idx})...")
        audio = sd.rec(
            int(duration_seconds * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device_idx,
        )
        sd.wait()
        return np.squeeze(audio)

    def transcribe_array(self, audio_array) -> str:
        """Transcreve um numpy array contendo amostras de áudio float32 a 16kHz."""
        import numpy as np
        from core.runtime_budget import INFERENCE_GATE

        if (not isinstance(audio_array, np.ndarray) or audio_array.ndim != 1
                or not 0 < audio_array.size <= 30 * 16000
                or audio_array.dtype.kind != "f" or not np.isfinite(audio_array).all()):
            raise ValueError("Áudio deve ser mono, finito, float, a 16 kHz e ter até 30 segundos.")
        with INFERENCE_GATE.slot(timeout=45):
            if self._model is not None:
                self._admit_model(self._loaded_device, loading=False)
            model = self._ensure_model()
            segments, _ = model.transcribe(
                audio_array.astype(np.float32, copy=False),
                language=self.language,
                beam_size=5,
                vad_filter=True,
            )
            # faster-whisper executes lazily: retain the slot through iteration.
            return " ".join(seg.text.strip() for seg in segments).strip()

    def record_and_transcribe(self, duration_seconds: float = 4.0) -> str:
        """Grava do microfone e transcreve o áudio para texto."""
        audio = self.record_audio(duration_seconds=duration_seconds)
        return self.transcribe_array(audio)

    def process_wake_word(self, text: str) -> tuple[bool, str]:
        """Detecta wake word ('Ei Nyx', 'Hey Nyx', 'Oi Nyx', etc.) e extrai o comando real.

        Variantes aceitas (Whisper às vezes transcreve de formas ligeiramente diferentes):
          - "Ei Nyx", "Hey Nyx", "Oi Nyx", "Olá Nyx", "E Nyx"
          - "Nyx" isolado no início da frase

        Retorna: (has_wake_word, prompt_restante)
        """
        cleaned = text.strip()
        # Padrão amplo: salutação opcional + "Nyx" + separador
        wake_pattern = re.compile(
            r"^(?:(?:ei|hey|oi|ol[aá]|e)[,\s]+)?nyx[,.:!?\s]*",
            re.IGNORECASE,
        )
        match = wake_pattern.match(cleaned)
        if match:
            prompt = cleaned[match.end():].strip()
            return True, prompt
        return False, cleaned
