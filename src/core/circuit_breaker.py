"""Pausa transitória por operação/alvo; desativação administrativa fica separada."""
from dataclasses import dataclass
import hashlib
import json
from threading import RLock
import time


@dataclass
class CircuitState:
    failures: int = 0
    unverified: int = 0
    until: float = 0
    cooldown: float = 60
    probing: bool = False
    target: str = ""


class CircuitBreaker:
    def __init__(self, clock=time.monotonic, cooldown=60):
        self.clock = clock
        self.cooldown = cooldown
        self.states = {}
        self.lock = RLock()

    @staticmethod
    def key(tool, params):
        action = str(params.get("action") or params.get("operation") or params.get("op") or params.get("ui_action") or "")
        target = {k: params[k] for k in ("hwnd", "pid", "url", "path", "template", "query", "selector") if params.get(k) is not None}
        app = params.get("app") or params.get("app_name") or params.get("name")
        if app is not None:
            target["app"] = str(app).strip().casefold()
        digest = hashlib.sha256(json.dumps(target, sort_keys=True, default=str).encode()).hexdigest()[:24]
        return tool, action, digest

    def blocked(self, tool, params, *, reserve=False):
        key = self.key(tool, params)
        with self.lock:
            state = self.states.get(key)
            if state is None or state.failures < 3:
                return None
            remaining = max(0, state.until - self.clock())
            if remaining or state.probing:
                return {"circuit_breaker": True, "error_code": "CIRCUIT_OPEN",
                        "retry_after_s": round(remaining, 2), "action": key[1],
                        "message": f"Ação {tool}/{key[1]} pausada para este alvo após falhas. "
                                   f"Nova tentativa em {remaining:.0f}s ou após a tentativa em curso. "
                                   "Consulte o estado antes de repetir; outros alvos continuam disponíveis."}
            if reserve:
                state.probing = True
            return None

    def record(self, tool, params, ok):
        with self.lock:
            key = self.key(tool, params)
            if key not in self.states and len(self.states) >= 512:
                # Bound memory without evicting active/open safety state.
                self.states = {k: s for k, s in self.states.items() if s.failures or s.probing}
            state = self.states.setdefault(key, CircuitState(cooldown=self.cooldown))
            state.target = str(params.get('app') or params.get('app_name') or params.get('name')
                               or params.get('url') or params.get('path') or params.get('hwnd') or 'Geral')[:160]
            if ok:
                state.failures = 0
                state.until = 0
                state.cooldown = self.cooldown
            else:
                if state.probing:
                    state.cooldown = min(state.cooldown * 2, 600)
                state.failures += 1
                if state.failures >= 3:
                    state.until = self.clock() + state.cooldown
            state.probing = False

    def observe(self, tool, params, verified):
        with self.lock:
            state = self.states.get(self.key(tool, params))
            if state:
                state.unverified = 0 if verified else state.unverified + 1

    def reset(self, tool=None):
        with self.lock:
            self.states = {k: s for k, s in self.states.items() if s.probing or (tool and k[0] != tool)}

    def snapshot(self):
        with self.lock:
            return [{'tool': key[0], 'action': key[1], 'target': state.target,
                     'failures': state.failures, 'unverified': state.unverified,
                     'retry_after_s': max(0, round(state.until - self.clock())),
                     'state': ('Em recuperação' if state.probing else 'Pausada' if state.until > self.clock()
                               else 'Pode tentar novamente' if state.failures >= 3 else 'Disponível')}
                    for key, state in self.states.items() if state.failures or state.unverified or state.probing]
