"""Small validated dependency graphs, independent of model output execution."""
import re


def normalize_tasks(tasks, roles, limit=4):
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= limit:
        raise ValueError(f"Informe de 1 a {limit} subtarefas.")
    normalized = []
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError("Subtarefa inválida.")
        identity = task.get("id", f"task-{index + 1}")
        role, instruction = task.get("role"), task.get("task")
        dependencies = task.get("depends_on", [])
        if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", identity):
            raise ValueError("ID de subtarefa inválido.")
        if not isinstance(role, str) or role not in roles:
            raise ValueError("Papel de subtarefa desconhecido.")
        if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 500:
            raise ValueError("Cada subtarefa deve ter de 1 a 500 caracteres.")
        if not isinstance(dependencies, list) or len(dependencies) > limit or any(not isinstance(d, str) for d in dependencies):
            raise ValueError("depends_on deve listar IDs de subtarefas.")
        normalized.append({"id": identity, "role": role, "task": instruction.strip(),
                           "depends_on": list(dict.fromkeys(dependencies))})
    identities = {task["id"] for task in normalized}
    if len(identities) != len(normalized):
        raise ValueError("IDs de subtarefas duplicados.")
    if any(set(task["depends_on"]) - identities for task in normalized):
        raise ValueError("Dependência aponta para subtarefa inexistente.")
    visited = set()
    while len(visited) < len(normalized):
        ready = {t["id"] for t in normalized if t["id"] not in visited and set(t["depends_on"]) <= visited}
        if not ready:
            raise ValueError("Dependências formam um ciclo.")
        visited.update(ready)
    return normalized
