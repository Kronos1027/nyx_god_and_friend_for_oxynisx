"""Push only an encrypted snapshot to the authorized private backup branch.

Uses Git's existing credential manager. Does not read/export credentials or
stage the development tree. Divergent remote history fails without force push.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REMOTE = "https://github.com/Kronos1027/nyx_god_and_friend_for_oxynisx.git"
BRANCH = "nyx-backups"


class CloudBackup:
    def __init__(self, root: Path):
        self.work = Path(root) / "data" / "cloud-backup"

    def _git(self, *args: str) -> str:
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        result = subprocess.run(
            ["git", *args], cwd=self.work, env=env, text=True,
            capture_output=True, timeout=35, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            # Credential manager diagnostics may contain user details; do not forward raw output.
            raise RuntimeError("Git não concluiu o backup. Verifique conexão, credenciais e divergências da branch nyx-backups.")
        return result.stdout.strip()

    def upload(self, snapshot: Path) -> str:
        if snapshot.suffix != ".nyxbackup" or snapshot.stat().st_size > 5 * 1024 * 1024:
            raise ValueError("Nuvem aceita somente backup .nyxbackup criptografado de até 5 MiB")
        # Fernet is ASCII and starts with a version byte encoded in base64.
        if not snapshot.read_bytes().startswith(b"gAAAAA"):
            raise ValueError("Formato de backup criptografado inválido")
        self.work.mkdir(parents=True, exist_ok=True)
        if not (self.work / ".git").exists():
            if any(self.work.iterdir()):
                raise ValueError("Pasta de nuvem existente não é um repositório de backup")
            self._git("init", "--initial-branch=" + BRANCH)
            self._git("remote", "add", "origin", REMOTE)
            if self._git("ls-remote", "--heads", "origin", BRANCH):
                self._git("fetch", "--depth=1", "origin", BRANCH)
                self._git("reset", "--hard", "FETCH_HEAD")
        if self._git("remote", "get-url", "origin") != REMOTE:
            raise ValueError("Destino do backup não corresponde ao repositório autorizado")
        if self._git("branch", "--show-current") != BRANCH:
            raise ValueError("Branch de backup incorreta")
        # Refuse unrelated tracked/staged files, including any accidentally copied key.
        allowed = {"latest.nyxbackup", "README.md"}
        if set(self._git("ls-files").splitlines()) - allowed:
            raise ValueError("Repositório de backup contém arquivos não permitidos")
        shutil.copyfile(snapshot, self.work / "latest.nyxbackup")
        (self.work / "README.md").write_text(
            "# Backup privado Nyx\n\nSnapshot Fernet criptografado. A chave de recuperação está somente no computador de origem. "
            "Guarde uma cópia privada da chave separada deste repositório. "
            "Versões anteriores podem permanecer no histórico Git. Não adicione dados em texto claro.\n", encoding="utf-8")
        self._git("add", "--", "latest.nyxbackup", "README.md")
        if self._git("diff", "--cached", "--name-only"):
            self._git("-c", "user.name=Nyx Backup", "-c", "user.email=nyx@local.invalid", "commit", "-m", "Save encrypted local memory snapshot")
        self._git("push", "origin", "HEAD:refs/heads/" + BRANCH)
        return self._git("rev-parse", "HEAD")
