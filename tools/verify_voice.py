"""Offline smoke test for the synthetic Portuguese voice fixture (no microphone)."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def matches_fixture(text: str) -> bool:
    normalized = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
    tokens = re.findall(r"\w+", normalized)
    return (all(word in tokens for word in ("ola", "minha", "amiga", "quanto", "mais"))
            and any(word in tokens for word in ("vinte", "20"))
            and any(word in tokens for word in ("trinta", "30")))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fixture: Olá, minha amiga. Quanto é vinte mais trinta?")
    parser.add_argument("--audio", type=Path, default=ROOT / "build/previews/voice-fixture.wav")
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    from faster_whisper.audio import decode_audio
    from audio.stt import SpeechToText
    from core.runtime_budget import resource_snapshot

    audio = decode_audio(str(args.audio), sampling_rate=16000)
    stt = SpeechToText(model_name="small", device="cpu", download_root=str(ROOT / "models/whisper"))
    report = {"fixture": "synthetic Portuguese; no microphone", "model": "small", "device": "cpu",
              "audio_seconds": len(audio) / 16000, "before": asdict(resource_snapshot()), "passed": False}
    started = time.monotonic()
    try:
        result = stt.transcribe_array(audio)
        report.update(transcribed=result, passed=matches_fixture(result))
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    report.update(seconds=round(time.monotonic() - started, 2), after=asdict(resource_snapshot()))
    folder = ROOT / "build/previews/voice-attempts"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid4().hex}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    print(path)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
