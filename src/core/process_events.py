"""Observe only explicitly selected PIDs; never enumerate or terminate applications."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WatchedProcess:
    pid: int
    created: float
    name: str


class AuthorizedProcessSensor:
    def __init__(self, context):
        self.context = context
        self.watched = {}

    def watch(self, pid: int):
        if not self.context.permissions().get("processes"):
            raise PermissionError("Observação de processos desativada")
        if type(pid) is not int or pid <= 0 or len(self.watched) >= 16:
            raise ValueError("Selecione um PID válido; limite de 16 processos")
        import psutil
        process = psutil.Process(pid)
        entry = WatchedProcess(pid, process.create_time(), process.name()[:80])
        self.watched[pid] = entry
        return entry

    def clear(self):
        self.watched.clear()

    def poll(self, *, under_load=False):
        def collect():
            import psutil
            events = []
            for pid, entry in list(self.watched.items()):
                try:
                    process = psutil.Process(pid)
                    ended = not process.is_running() or process.create_time() != entry.created
                except psutil.NoSuchProcess:
                    ended = True
                except psutil.AccessDenied:
                    continue  # Lack of access is not proof of termination.
                if ended:
                    events.append({"kind": "process_exited", "key": f"{pid}:{entry.created}", "title": entry.name})
                    self.watched.pop(pid, None)
            return events
        return self.context.collect("processes", collect, under_load=under_load)
