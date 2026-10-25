"""Local package inventory commands. No activation or script execution."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app_paths import user_data_dir  # noqa: E402
from core.skill_package_store import SkillPackageStore  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Catálogo local de pacotes inativos SKILL.md")
    parser.add_argument("--store", type=Path, default=user_data_dir() / "data/skill_packages")
    commands = parser.add_subparsers(dest="command", required=True)
    importing = commands.add_parser("import")
    importing.add_argument("directory", type=Path)
    commands.add_parser("list")
    versions = commands.add_parser("versions")
    versions.add_argument("name")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("name")
    inspect.add_argument("--version", type=int)
    exporting = commands.add_parser("export")
    exporting.add_argument("name")
    exporting.add_argument("version", type=int)
    exporting.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        store = SkillPackageStore(args.store)
        if args.command == "import":
            result = store.import_directory(args.directory)
        elif args.command == "list":
            result = store.list_packages()
        elif args.command == "versions":
            result = store.versions(args.name)
        elif args.command == "inspect":
            package = store.load(args.name, args.version)
            result = {"metadata": asdict(package.metadata), "instructions": package.instructions,
                      "files": [item.name for item in package.snapshot.files],
                      "manifest": package.snapshot.manifest(), "state": "inactive"}
        else:
            store.export(args.name, args.version, args.destination)
            result = {"exported": str(args.destination)}
        print(json.dumps({"ok": True, "execution_authorized": False, "result": result}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
