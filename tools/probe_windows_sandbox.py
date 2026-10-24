"""Trusted LPAC smoke probe. Never falls back to an ordinary process."""

import json
import argparse
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.windows_sandbox import profile, run_lpac  # noqa: E402


def copy_python(runtime):
    """Copy only the installed standard-library runtime for a trusted probe."""
    runtime.mkdir()
    installed = Path(sys.base_prefix)
    for path in installed.iterdir():
        if path.is_file() and path.suffix.lower() in {".exe", ".dll"}:
            shutil.copy2(path, runtime / path.name)
    for name in ("Lib", "DLLs"):
        shutil.copytree(
            installed / name,
            runtime / name,
            ignore=shutil.ignore_patterns(
                "site-packages",
                "__pycache__",
                "test",
                "tests",
                "idlelib",
                "tkinter",
                "ensurepip",
                "turtledemo",
            ),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--system-temp", action="store_true", help="Compare staging on the system temporary volume"
    )
    parser.add_argument(
        "--trace-loader", action="store_true", help="Trace only the owned child's Windows loader"
    )
    parser.add_argument(
        "--registry-read",
        action="store_true",
        help="Diagnostic comparison with the named registryRead capability",
    )
    options = parser.parse_args()
    base = ROOT / "build" / "sandbox-probes"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="nyx-lpac-", dir=None if options.system_temp else base
    ) as directory:
        staging = Path(directory)
        runtime, workspace = staging / "python", staging / "work"
        workspace.mkdir()
        copy_python(runtime)
        with profile() as sandbox:
            trace = None
            if options.trace_loader:
                from lpac_loader_trace import LoaderTrace

                trace = LoaderTrace(sandbox.api)
            sandbox.grant(staging, staging)
            sandbox.grant(staging, workspace, writable=True)
            script = """
import json, sys, os
from pathlib import Path
value = {'message':'LPAC Python started', 'prefix':sys.prefix, 'environment':sorted(os.environ), 'stdout':repr(sys.stdout)}
for descriptor in (1, 2):
    try:
        value[str(descriptor)] = str(os.fstat(descriptor))
        os.write(descriptor, b'LPAC pipe write\\n')
    except Exception as error:
        value[str(descriptor)] = repr(error)
Path('startup-proof.json').write_text(json.dumps(value), encoding='utf-8')
print(json.dumps(value), flush=True)
"""
            result = run_lpac(
                sandbox,
                runtime / "python.exe",
                ["-I", "-S", "-X", "utf8", "-c", script],
                workspace,
                cancelled=trace.pump if trace else lambda: False,
                diagnostic_registry_read=options.registry_read,
            )
            proof = workspace / "startup-proof.json"
            if proof.exists():
                result["startup_proof"] = json.loads(proof.read_text(encoding="utf-8"))
            if trace:
                (base / "loader-trace.txt").write_text("\n".join(trace.lines), encoding="utf-8")
            (base / "smoke-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result))
    return 0 if result["returncode"] == 0 and "LPAC Python started" in result["output"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
