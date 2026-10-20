"""Nyx — core/skills.py (Gerenciador de Skills Versionadas e Reutilizáveis)

Permite ao agente:
1. Promover tarefas de múltiplos passos bem-sucedidas e verificadas a "Skills".
2. Versionar skills (v1, v2, v3...) com histórico imutável em disco.
3. Auto-rollback: se uma versão recente falhar em produção, reverte automaticamente para a versão anterior estável.
4. Exportar catálogo de skills para o LLM planejar ações compostas rapidamente.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

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


class SkillManager:
    """Gerenciador central de Skills com versionamento e auto-rollback."""

    def __init__(self, skills_dir: Path = Path("skills")) -> None:
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, SkillVersion] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Carrega a versão ativa de cada skill a partir de current.json."""
        for skill_folder in self.skills_dir.iterdir():
            if skill_folder.is_dir():
                current_file = skill_folder / "current.json"
                if current_file.exists():
                    try:
                        data = json.loads(current_file.read_text(encoding="utf-8"))
                        skill = SkillVersion(**data)
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
        clean_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name).strip("_")
        skill_dir = self.skills_dir / clean_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        existing = self._cache.get(clean_name)
        new_version_num = (existing.version + 1) if existing else 1

        new_skill = SkillVersion(
            name=clean_name,
            version=new_version_num,
            description=description,
            steps=steps,
        )

        # Salva o arquivo imutável da versão (ex: v1.json)
        v_file = skill_dir / f"v{new_version_num}.json"
        v_file.write_text(json.dumps(asdict(new_skill), indent=2, ensure_ascii=False), encoding="utf-8")

        # Atualiza o ponteiro atual
        current_file = skill_dir / "current.json"
        current_file.write_text(json.dumps(asdict(new_skill), indent=2, ensure_ascii=False), encoding="utf-8")

        self._cache[clean_name] = new_skill
        log.info(f"Skill '{clean_name}' promovida com sucesso para versão {new_version_num}.")
        return new_skill

    def get_skill(self, name: str, version: Optional[int] = None) -> Optional[SkillVersion]:
        clean_name = name.strip()
        if version is None:
            return self._cache.get(clean_name)

        skill_dir = self.skills_dir / clean_name
        v_file = skill_dir / f"v{version}.json"
        if v_file.exists():
            try:
                data = json.loads(v_file.read_text(encoding="utf-8"))
                return SkillVersion(**data)
            except Exception:
                return None
        return None

    def record_execution_outcome(self, name: str, success: bool) -> bool:
        """Registra sucesso/falha. Em caso de falhas consecutivas, aciona rollback automático."""
        clean_name = name.strip()
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
                log.warning(f"[Skills] Acionando auto-rollback da skill '{clean_name}' v{skill.version} -> v{skill.version - 1}!")
                return self.rollback(clean_name)

        # Salva estado atualizado
        skill_dir = self.skills_dir / clean_name
        current_file = skill_dir / "current.json"
        current_file.write_text(json.dumps(asdict(skill), indent=2, ensure_ascii=False), encoding="utf-8")
        return True

    def rollback(self, name: str) -> bool:
        """Reverte a versão ativa para a versão anterior estável."""
        clean_name = name.strip()
        skill = self._cache.get(clean_name)
        if not skill or skill.version <= 1:
            return False

        target_version = skill.version - 1
        previous = self.get_skill(clean_name, version=target_version)
        if not previous:
            return False

        skill_dir = self.skills_dir / clean_name
        current_file = skill_dir / "current.json"
        current_file.write_text(json.dumps(asdict(previous), indent=2, ensure_ascii=False), encoding="utf-8")
        self._cache[clean_name] = previous
        log.info(f"Rollback concluído: skill '{clean_name}' agora está na v{target_version}.")
        return True

    def list_skills(self) -> List[Dict[str, Any]]:
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
