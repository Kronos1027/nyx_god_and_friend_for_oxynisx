"""Nyx — audio/stt.py (Fase 3: Transcrição de Áudio com faster-whisper)

Captura de áudio via sounddevice e transcrição rápida local:
- Suporta modelo configurável (base/small/tiny)
- Reconhece o comando de wake word "Ei Nyx" ou captura direta
- Execução não-bloqueante em thread dedicada
"""

from __future__ import annotations

import logging
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
        import os

        self.model_name = model_name
        self.device = device
        self.language = language

        # Garante que cache e downloads fiquem na unidade do projeto (E:),
        # evitando crash por falta de espaço no C:
        base_dir = user_data_dir()
        self.download_root = download_root or str(base_dir / "models" / "whisper")
        os.environ.setdefault("HF_HOME", str(base_dir / "models" / "hf_cache"))
        Path(self.download_root).mkdir(parents=True, exist_ok=True)

        self._model = None
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
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                f"faster-whisper não está disponível: {exc}. Instale as dependências de áudio."
            ) from exc

        # Seleciona dispositivo (CUDA se GPU disponível, senão CPU)
        dev = self.device
        compute = "float16"
        if dev == "auto":
            try:
                import torch

                if torch.cuda.is_available():
                    dev = "cuda"
                    compute = "float16"
                else:
                    dev = "cpu"
                    compute = "int8"
            except Exception:
                dev = "cpu"
                compute = "int8"

        log.info(f"Carregando faster-whisper ({self.model_name}) em {dev} ({compute})...")
        try:
            self._model = WhisperModel(
                self.model_name,
                device=dev,
                compute_type=compute,
                download_root=self.download_root,
            )
        except Exception as exc:
            log.warning(f"Falha ao inicializar no dispositivo {dev}: {exc}. Tentando CPU...")
            self._model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8",
                download_root=self.download_root,
            )
        return self._model

    def record_audio(self, duration_seconds: float = 4.0, sample_rate: int = 16000):
        """Grava áudio do microfone usando sounddevice."""
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
        model = self._ensure_model()
        segments, info = model.transcribe(
            audio_array,
            language=self.language,
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text

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
