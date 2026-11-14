"""Opt-in, low-overhead host memory sampling for local experiments.

Measures *system* free memory, not Ollama-exclusive usage. Python RSS excludes
the separate Ollama process. GPU snapshots are sampled separately by the CLI.
No persistent service or always-on thread.
"""
from __future__ import annotations

import os
import threading

MiB = 1024 * 1024
GiB = 1024**3
MIN_AVAILABLE_BYTES = 3 * GiB


def host_memory_sample() -> tuple[int, int]:
    """(system_available_bytes, this_python_process_rss_bytes)."""
    import psutil
    available = psutil.virtual_memory().available
    rss = psutil.Process(os.getpid()).memory_info().rss
    return available, rss


class MemorySampler:
    def __init__(self, sample=host_memory_sample, interval: float = 0.5):
        if not callable(sample) or not 0.1 <= interval <= 10:
            raise ValueError("intervalo de telemetria inválido")
        self.sample = sample
        self.interval = interval
        self.min_available_bytes: int | None = None
        self.peak_python_rss_bytes: int | None = None
        self.sample_count = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def take_sample(self):
        try:
            available, rss = self.sample()
            if any(type(x) is not int or x < 0 for x in (available, rss)):
                return
        except (OSError, ValueError, RuntimeError, ImportError):
            return
        self.sample_count += 1
        self.min_available_bytes = (available if self.min_available_bytes is None
                                    else min(self.min_available_bytes, available))
        self.peak_python_rss_bytes = (rss if self.peak_python_rss_bytes is None
                                      else max(self.peak_python_rss_bytes, rss))

    def _work(self):
        while not self._stop.wait(self.interval):
            self.take_sample()

    def __enter__(self):
        self._stop.clear()
        self.take_sample()
        self._thread = threading.Thread(target=self._work, name="nyx-eval-sample", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 1)
        self.take_sample()

    def report(self) -> dict:
        return {
            "samples": self.sample_count,
            "min_system_available_mib": (
                round(self.min_available_bytes / MiB, 1) if self.min_available_bytes is not None else None
            ),
            "peak_python_rss_mib": (
                round(self.peak_python_rss_bytes / MiB, 1)
                if self.peak_python_rss_bytes is not None else None
            ),
            "notes": "system-wide RAM, not Ollama-exclusive; Python RSS excludes Ollama",
        }


def admit_research(available_bytes: int | None):
    if type(available_bytes) is not int or available_bytes < MIN_AVAILABLE_BYTES:
        raise RuntimeError("Pesquisa adiada: menos de 3 GiB de RAM livre ou telemetria indisponível.")
