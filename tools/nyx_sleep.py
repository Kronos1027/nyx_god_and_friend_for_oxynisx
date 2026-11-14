"""Manual, opt-in lightweight Nyx sleep. Usage from repository root:

    python tools/nyx_sleep.py status
    python tools/nyx_sleep.py enable
    python tools/nyx_sleep.py once
    python tools/nyx_sleep.py cards
    python tools/nyx_sleep.py disable
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.sleep_cycle import SleepCycle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Nyx: consolidação offline e sem modelo")
    parser.add_argument("command", choices=("status", "enable", "disable", "once", "cards"))
    args = parser.parse_args()
    # Match the default MemoryManager location in src/main.py; user data may
    # be redirected by activate_runtime in packaged builds, so use sources here.
    engine = SleepCycle(Path("data") / "nyx_memory.db")
    if args.command in ("enable", "disable"):
        engine.set_enabled(args.command == "enable")
        result = engine.status()
    elif args.command == "status":
        result = engine.status()
    elif args.command == "cards":
        result = engine.cards()
    else:
        try:
            from core.runtime_budget import resource_snapshot
            available = resource_snapshot().ram_available_bytes
        except (ImportError, OSError):
            available = None  # Fail closed if telemetry is unavailable.
        # This explicit CLI command is an idle maintenance request. Don't run
        # concurrently with the desktop app, games, or interactive inference.
        result = engine.run_once(available_ram_bytes=available, idle_seconds=120).__dict__
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
