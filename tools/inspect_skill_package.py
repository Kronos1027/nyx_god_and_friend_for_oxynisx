"""Inspect an explicitly selected local Agent Skills folder without executing it."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.skill_package import SkillPackage  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Valida e inspeciona um pacote SKILL.md local; não executa scripts.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--export", type=Path, help="ZIP novo; nunca sobrescreve arquivo existente")
    args = parser.parse_args()
    try:
        package = SkillPackage.capture(args.directory)
        manifest = package.snapshot.manifest()
        if args.export:
            package.export_zip(args.export)
        print(json.dumps({"valid_structure": True, "metadata": asdict(package.metadata),
                          "sha256": manifest["sha256"], "bytes": manifest["bytes"],
                          "files": [item.name for item in package.snapshot.files],
                          "excluded": list(package.snapshot.skipped),
                          "execution_authorized": False, "functional_tests_run": False,
                          "exported": str(args.export) if args.export else None}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"valid_structure": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
