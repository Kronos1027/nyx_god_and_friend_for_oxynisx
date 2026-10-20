"""Publish a clean allowlisted source snapshot, without local Git history/data."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "https://github.com/Kronos1027/nyx_god_and_friend_for_oxynisx.git"
EXTENSIONS = {".py", ".md", ".txt", ".ps1", ".gbnf", ".toml", ".yml", ".spec"}
ROOT_FILES = (".gitignore", "README.md", "STATUS.md", "LIMITACOES.md", "pyproject.toml",
              "requirements.txt", "requirements-windows.txt", "requirements-build.txt", "run_nyx.ps1")


def source_manifest() -> list[Path]:
    files = [ROOT / name for name in ROOT_FILES]
    for folder in ("src", "tests", "docs", "tools", "packaging", ".github"):
        files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix in EXTENSIONS)
    files += [ROOT / "assets/README.md", ROOT / "assets/oxynisx/spritesheet.png"]
    selected = []
    for path in sorted(set(files)):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if not path.resolve().is_relative_to(ROOT) or path.is_symlink():
            raise ValueError("Fonte fora do projeto")
        if path.suffix != ".png":
            text = path.read_text(encoding="utf-8-sig")
            if re.search(r"(?:sk-proj-|ghp_|github_pat_)[A-Za-z0-9_]{20,}", text):
                raise ValueError(f"Possível credencial em {path.relative_to(ROOT)}; publicação interrompida")
        selected.append(path)
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    selected = source_manifest()
    print(f"Allowlisted files: {len(selected)}; no databases, keys, logs, models or local Git history")
    if not args.push:
        return
    destination = ROOT / "build" / "source-publication"
    if destination.exists():
        raise ValueError("Publicação anterior existe; revise antes de reutilizar")
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")

    def git(*parts, cwd=ROOT):
        result = subprocess.run(["git", *parts], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError("Git falhou; publicação preservada para inspeção, sem force push")
        return result.stdout.strip()

    destination.parent.mkdir(parents=True, exist_ok=True)
    git("clone", "--depth=1", "--branch=main", "--single-branch", REMOTE, str(destination))
    for source in selected:
        target = destination / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    git("add", "--all", cwd=destination)
    staged = git("diff", "--cached", "--name-only", cwd=destination).splitlines()
    allowed = {p.relative_to(ROOT).as_posix() for p in selected}
    if set(staged) - allowed:
        raise ValueError("Arquivo não autorizado no stage")
    git("-c", "user.name=Nyx Development", "-c", "user.email=nyx@local.invalid", "commit", "-m",
        "Add native workspace, Oxynisx, resource budgets and evidence-based learning foundation", cwd=destination)
    git("push", "origin", "HEAD:refs/heads/main", cwd=destination)
    print("Published source commit:", git("rev-parse", "HEAD", cwd=destination))


if __name__ == "__main__":
    main()
