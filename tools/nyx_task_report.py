"""Print safe local task diagnostics while Nyx runs (no exclusive journal lock).

Example: py -3.11 tools/nyx_task_report.py --db data/task_journal.db
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.task_diagnostics import read_task_diagnostics  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico privado do executor Nyx")
    parser.add_argument("--db", required=True, type=Path, help="Arquivo SQLite do diário")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        report = read_task_diagnostics(args.db, limit=args.limit)
    except (OSError, ValueError, RuntimeError, sqlite3.Error):
        print("Não foi possível consultar o histórico com segurança.", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sqlite3
    raise SystemExit(main())
