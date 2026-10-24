"""Nyx — core/skills.py (Gerenciador de Skills Versionadas e Reutilizáveis)

Permite ao agente:
1. Armazenar procedimentos declarativos; não os testa, executa ou autoriza.
2. Versionar skills (v1, v2, v3...) com histórico imutável em disco.
3. Auto-rollback após duas falhas informadas; a versão anterior não é necessariamente estável.
4. Exportar catálogo de skills para o LLM planejar ações compostas rapidamente.
"""

from __future__ import annotations

import json
import copy
import logging
import math
import os
import re
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.sandbox_journal import reject_link

log = logging.getLogger(__name__)


@dataclass
class SkillVersion:
    name: str
    version: int
    description: str
    steps: List[Dict[str, Any]]
    created_at: float = field(default_factory=time.time)
    success_count: int = 0
    failure_count: int = 0
    previous_version: int | None = None  # None = legacy history; 0 = no prior active version


class SkillManager:
    """Gerenciador central de Skills com versionamento e auto-rollback."""

    def __init__(self, skills_dir: Path = Path("skills")) -> None:
        self.skills_dir = Path(skills_dir).absolute()
        for path in (self.skills_dir, *self.skills_dir.parents):
            reject_link(path)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, SkillVersion] = {}
        with self._locked():
            pass

    @staticmethod
    def _name(name):
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name):
            raise ValueError("Nome de skill inválido; use até 64 letras ASCII, números, _ ou -.")
        if name.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
            raise ValueError("Nome de skill reservado pelo Windows.")
        return name

    @contextmanager
    def _locked(self):
        for path in (self.skills_dir, *self.skills_dir.parents):
            reject_link(path)
        lock_path = self.skills_dir / ".skills.lock"
        reject_link(lock_path)
        with lock_path.open("a+b") as lease:
            if lease.seek(0, 2) == 0:
                lease.write(b"0")
                lease.flush()
            lease.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._load_all()
            yield

    @staticmethod
    def _read(path):
        reject_link(path.parent)
        reject_link(path)
        with path.open("rb") as stream:
            raw = stream.read(131073)
        if len(raw) > 131072:
            raise ValueError("Skill excede 128 KiB.")
        return json.loads(raw)

    @staticmethod
    def _validate(skill):
        SkillManager._name(skill.name)
        if type(skill.version) is not int or not 1 <= skill.version <= 32:
            raise ValueError("Versão inválida.")
        if skill.previous_version is not None and (type(skill.previous_version) is not int
                                                    or not 0 <= skill.previous_version < skill.version):
            raise ValueError("Antecessor inválido.")
        if not isinstance(skill.description, str) or len(skill.description) > 4000:
            raise ValueError("Descrição inválida.")
        if not isinstance(skill.steps, list) or not 1 <= len(skill.steps) <= 12 or any(not isinstance(step, dict) for step in skill.steps):
            raise ValueError("Etapas declarativas inválidas.")
        if type(skill.created_at) not in (int, float) or not math.isfinite(skill.created_at):
            raise ValueError("Data inválida.")
        if any(type(value) is not int or not 0 <= value <= 1_000_000_000
               for value in (skill.success_count, skill.failure_count)):
            raise ValueError("Contadores inválidos.")

    @staticmethod
    def _write(path, skill, *, immutable=False):
        SkillManager._validate(skill)
        reject_link(path.parent)
        reject_link(path)
        raw = json.dumps(asdict(skill), ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) > 131072:
            raise ValueError("Skill excede 128 KiB.")
        temporary = path if immutable else path.with_name(f".pending-{uuid4().hex}")
        try:
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if not immutable:
                os.replace(temporary, path)
        finally:
            if not immutable and temporary.exists():
                temporary.unlink()

    def _load_all(self) -> None:
        """Carrega a versão ativa de cada skill a partir de current.json."""
        self._cache.clear()
        entries = []
        for entry in self.skills_dir.iterdir():
            entries.append(entry)
            if len(entries) > 128:
                raise ValueError("Catálogo de skills excede o limite de entradas.")
        for skill_folder in entries:
            reject_link(skill_folder)
            if skill_folder.is_dir():
                current_file = skill_folder / "current.json"
                if current_file.exists():
                    try:
                        self._name(skill_folder.name)
                        data = self._read(current_file)
                        skill = SkillVersion(**data)
                        self._validate(skill)
                        if skill.name != skill_folder.name or type(skill.version) is not int or not 1 <= skill.version <= 32:
                            raise ValueError("Identidade da versão inválida.")
                        original = self._read(skill_folder / f"v{skill.version}.json")
                        for key in ("name", "version", "description", "steps", "created_at"):
                            if data[key] != original[key]:
                                raise ValueError("Versão ativa diverge do histórico.")
                        if data.get("previous_version") != original.get("previous_version"):
                            raise ValueError("Antecessor diverge do histórico.")
                        self._cache[skill.name] = skill
                    except Exception as exc:
                        log.warning(f"Falha ao carregar skill '{skill_folder.name}': {exc}")

    def promote_task_to_skill(
        self,
        name: str,
        description: str,
        steps: List[Dict[str, Any]],
    ) -> SkillVersion:
        """Cria ou atualiza uma skill com uma nova versão."""
        clean_name = self._name(name)
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError("Descrição inválida ou acima de 4.000 caracteres.")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 12 or any(not isinstance(step, dict) for step in steps):
            raise ValueError("Uma skill exige de 1 a 12 etapas declarativas.")
        with self._locked():
            return self._promote(clean_name, description, steps)

    def _promote(self, clean_name, description, steps):
        if any(path.name.casefold() == clean_name.casefold() and path.name != clean_name
               for path in self.skills_dir.iterdir()):
            raise ValueError("Nome colide com outra skill por capitalização.")
        skill_dir = self.skills_dir / clean_name
        reject_link(skill_dir)
        if not skill_dir.exists() and sum(path.is_dir() for path in self.skills_dir.iterdir()) >= 64:
            raise ValueError("Catálogo limitado a 64 skills.")
        skill_dir.mkdir(parents=True, exist_ok=True)
        versions = []
        for index, path in enumerate(skill_dir.iterdir()):
            if index >= 64:
                raise ValueError("Pasta da skill excede o limite de entradas.")
            reject_link(path)
            match = re.fullmatch(r"v([1-9][0-9]*)\.json", path.name)
            if match:
                versions.append(int(match[1]))
        new_version_num = max(versions, default=0) + 1
        if new_version_num > 32:
            raise ValueError("Histórico limitado a 32 versões; nenhuma versão foi apagada.")
        existing = self._cache.get(clean_name)
        if (skill_dir / "current.json").exists() and existing is None:
            raise ValueError("Versão ativa inválida; repare o catálogo antes de promover.")

        new_skill = SkillVersion(
            name=clean_name,
            version=new_version_num,
            description=description,
            steps=copy.deepcopy(steps),
            previous_version=existing.version if existing else 0,
        )

        # Salva o arquivo imutável da versão (ex: v1.json)
        v_file = skill_dir / f"v{new_version_num}.json"
        self._write(v_file, new_skill, immutable=True)

        # Atualiza o ponteiro atual
        current_file = skill_dir / "current.json"
        self._write(current_file, new_skill)

        self._cache[clean_name] = new_skill
        log.info(f"Skill '{clean_name}' promovida com sucesso para versão {new_version_num}.")
        return copy.deepcopy(new_skill)

    def get_skill(self, name: str, version: Optional[int] = None) -> Optional[SkillVersion]:
        clean_name = self._name(name)
        with self._locked():
            return copy.deepcopy(self._get_skill(clean_name, version))

    def _get_skill(self, clean_name, version=None):
        if version is None:
            return self._cache.get(clean_name)

        if type(version) is not int or not 1 <= version <= 32:
            raise ValueError("Versão inválida.")
        skill_dir = self.skills_dir / clean_name
        reject_link(skill_dir)
        v_file = skill_dir / f"v{version}.json"
        if v_file.exists():
            try:
                data = self._read(v_file)
                skill = SkillVersion(**data)
                self._validate(skill)
                if skill.name != clean_name or skill.version != version:
                    raise ValueError("Identidade da versão inválida.")
                return skill
            except Exception:
                return None
        return None

    def record_execution_outcome(self, name: str, success: bool) -> bool:
        """Registra sucesso/falha. Em caso de falhas consecutivas, aciona rollback automático."""
        clean_name = self._name(name)
        if type(success) is not bool:
            raise ValueError("Resultado deve ser booleano.")
        with self._locked():
            return self._record(clean_name, success)

    def _record(self, clean_name, success):
        skill = self._cache.get(clean_name)
        if not skill:
            return False

        if success:
            skill.success_count += 1
            skill.failure_count = 0  # Reseta contador de falhas
        else:
            skill.failure_count += 1
            # Se uma nova versão falhar 2 vezes seguidas, executa rollback
            if skill.failure_count >= 2 and skill.version > 1:
                log.warning(f"[Skills] Solicitando rollback da skill '{clean_name}' v{skill.version}.")
                if self._rollback(clean_name):
                    return True

        # Salva estado atualizado
        skill_dir = self.skills_dir / clean_name
        current_file = skill_dir / "current.json"
        self._write(current_file, skill)
        return True

    def rollback(self, name: str) -> bool:
        """Reverte ao antecessor registrado; isso não certifica estabilidade."""
        clean_name = self._name(name)
        with self._locked():
            return self._rollback(clean_name)

    def _rollback(self, clean_name):
        skill = self._cache.get(clean_name)
        if not skill or skill.version <= 1:
            return False

        target_version = skill.version - 1 if skill.previous_version is None else skill.previous_version
        if target_version == 0:
            return False
        previous = self._get_skill(clean_name, version=target_version)
        if not previous:
            return False

        skill_dir = self.skills_dir / clean_name
        current_file = skill_dir / "current.json"
        self._write(current_file, previous)
        self._cache[clean_name] = previous
        log.info(f"Rollback concluído: skill '{clean_name}' agora está na v{target_version}.")
        return True

    def list_skills(self) -> List[Dict[str, Any]]:
        with self._locked():
            return self._list_skills()

    def _list_skills(self):
        return [
            {
                "name": s.name,
                "version": s.version,
                "description": s.description,
                "steps_count": len(s.steps),
                "success_count": s.success_count,
            }
            for s in self._cache.values()
        ]
