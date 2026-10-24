"""Trusted test supervisor: deliberately crashes around its own LPAC launch.

Not a Nyx tool. Candidate code is passed only to the LPAC launcher.
"""

import ctypes as C
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.windows_sandbox import ProcessInfo, profile, run_lpac  # noqa: E402


def main():
    mode, runtime_arg, workspace_arg, state_arg, proof_arg = sys.argv[1:]
    if mode not in {"created", "running"}:
        raise ValueError("Unknown test mode")
    runtime, workspace, state, proof = map(Path, (runtime_arg, workspace_arg, state_arg, proof_arg))
    with profile(state) as container:
        container.grant(runtime.parent, runtime)
        container.grant(workspace.parent, workspace, writable=True)
        original_create, original_resume = container.api.CreateProcessW, container.api.ResumeThread

        def create(*args):
            result = original_create(*args)
            if result:
                info = C.cast(args[-1], C.POINTER(ProcessInfo)).contents
                with proof.open("w", encoding="utf-8") as stream:
                    json.dump(
                        {
                            "pid": info.dwProcessId,
                            "profile": container.name,
                            "storage": str(container.api.profile_directory(container.name)),
                        },
                        stream,
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
                if mode == "created":
                    os._exit(7)  # before control returns to run_lpac
            return result

        def resume(thread):
            result = original_resume(thread)
            if result != 0xFFFFFFFF and mode == "running":
                deadline = time.monotonic() + 8
                while not (workspace / "ready.json").exists():
                    if time.monotonic() > deadline:
                        raise RuntimeError("LPAC fixture did not become ready")
                    time.sleep(0.01)
                os._exit(7)
            return result

        container.api.CreateProcessW, container.api.ResumeThread = create, resume
        run_lpac(
            container,
            runtime / "python.exe",
            [
                "-I",
                "-S",
                "-c",
                """
import os, sys, subprocess, time, json
from pathlib import Path
child = subprocess.Popen([sys.executable, '-I', '-S', '-c', 'import time; time.sleep(60)'], creationflags=0x08000000)
Path('ready.json').write_text(json.dumps({'pid':os.getpid(), 'child':child.pid}))
time.sleep(60)
""",
            ],
            workspace,
            diagnostic_registry_read=True,
        )


if __name__ == "__main__":
    main()
