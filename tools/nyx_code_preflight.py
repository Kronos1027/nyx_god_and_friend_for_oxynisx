"""Inspect explicit project files without loading or executing source code.

Usage:
  py -3.11 tools/nyx_code_preflight.py --repo E:\project app.py tests/test_app.py
Exit 0 = every selected file statically parsed; 1 = unsupported formats seen;
exit 2 = malformed/unsafe input or parser failure. Never implies tests passed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tools.code_patch_preflight import (  # noqa: E402
    PatchPreflightError, inspect_existing_files,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Nyx: inspeção estática sem executar código")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("files", nargs="+", help="Caminhos relativos ao projeto")
    args = parser.parse_args(argv)
    try:
        result = inspect_existing_files(args.repo, args.files)
    except (PatchPreflightError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, PatchPreflightError) else "PATH_NOT_READABLE"
        print(json.dumps({"ok": False, "error_code": code,
                          "tests_executed": False}, ensure_ascii=False))
        return 2
    unscanned = sum(item["status"] == "UNSCANNED" for item in result)
    print(json.dumps({
        "ok": unscanned == 0, "tests_executed": False,
        "checked": len(result), "unscanned": unscanned,
        "items": result,
        "note": "Sintaxe analisada sem execução; não comprova comportamento do programa.",
    }, ensure_ascii=False, indent=2))
    return 1 if unscanned else 0


if __name__ == "__main__":
    raise SystemExit(main())
