"""Measure LPAC supervisor handles in a process without GUI/test-suite workers."""

import json
from pathlib import Path
import sys

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.sandbox_channel import SandboxChannel  # noqa: E402
from core.windows_sandbox import profile, run_lpac  # noqa: E402


def main():
    runtime, workspace, journal = map(Path, sys.argv[1:])
    with profile(journal) as container:
        container.grant(runtime.parent, runtime)
        container.grant(workspace.parent, workspace, writable=True)

        def exercise():
            channel = SandboxChannel()
            channel.send(b"hello\n")
            result = run_lpac(container, runtime / "python.exe",
                              ["-I", "-S", "-c", "print(input(), flush=True)"], workspace,
                              channel=channel, diagnostic_registry_read=True)
            assert result["returncode"] == 0 and result["output"].strip() == "hello", result
            assert channel.closed.is_set() and all(result["isolation"].values())

        exercise()  # Load native libraries before the measured repetition.
        process = psutil.Process()
        counts = [process.num_handles()]
        for _ in range(10):
            exercise()
            counts.append(process.num_handles())
        print(json.dumps({"handle_counts": counts}), flush=True)
        assert max(counts[1:]) <= counts[0], counts


if __name__ == "__main__":
    main()
