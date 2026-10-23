"""Contextual invitations persisted across sessions; no spontaneous inference."""

from dataclasses import dataclass
from datetime import datetime
import time

from core.context_awareness import ContextAwarenessEngine


@dataclass(frozen=True)
class InitiativePreferences:
    level: str = "discreet"
    daily_limit: int = 3
    interval_seconds: int = 1800
    start_hour: int = 9
    end_hour: int = 21
    idle_seconds: int = 300

    def __post_init__(self):
        if self.level not in {"off", "discreet", "normal", "chatty"}:
            raise ValueError("Nível de iniciativa inválido")
        if not (0 <= self.daily_limit <= 20 and 300 <= self.interval_seconds <= 86400
                and 0 <= self.start_hour <= 23 and 0 <= self.end_hour <= 23
                and 0 <= self.idle_seconds <= 3600):
            raise ValueError("Limites de iniciativa inválidos")


TEMPLATES = {
    "task_failed": (.90, "A etapa {title} encontrou uma falha. Quer que eu ajude a investigar?"),
    "task_complete": (.65, "A tarefa {title} teve o resultado verificado. Quer revisar o próximo passo?"),
    "research_found": (.70, "O estudo sobre {title} trouxe uma referência. Quer ver a fonte e o trecho encontrado?"),
    "resource_pressure": (.85, "Uma avaliação recente encontrou pressão de memória. Estou adiando atividades opcionais para priorizar seus pedidos."),
    "process_exited": (.85, "O processo autorizado {title} encerrou. Quer investigar o que aconteceu?"),
    "project_changed": (.65, "Há alterações no projeto autorizado {title}. Quer revisar ou preparar um backup?"),
    "download_complete": (.75, "O download gerenciado {title} terminou. Quer conferir o próximo passo?"),
    "deadline": (.95, "O prazo configurado para {title} está se aproximando."),
}


class ProactiveInteractionEngine:
    def __init__(self, context: ContextAwarenessEngine, preferences=None, clock=time.time):
        self.context = context
        self.preferences = preferences or InitiativePreferences()
        self.clock = clock
        self.last_activity = clock()
        self.last_explanation = ""
        self.last_offer_id = None
        self.interests = None

    def activity(self):
        self.last_activity = self.clock()

    def poll(self, *, enabled, busy, focused, now=None, resource_pressure=False):
        prefs = self.preferences
        now = now or datetime.now()
        stamp = self.clock()
        allowed_hour = (prefs.start_hour <= now.hour < prefs.end_hour if prefs.start_hour < prefs.end_hour
                        else now.hour >= prefs.start_hour or now.hour < prefs.end_hour)
        if prefs.start_hour == prefs.end_hour:
            allowed_hour = False
        if (not enabled or prefs.level == "off" or busy or focused or not allowed_hour
                or stamp - self.last_activity < prefs.idle_seconds):
            return None
        preferences = self.interests.records("confirmed_preference") if self.interests is not None and self.interests.enabled else []
        with self.context.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            daily = db.execute("SELECT COUNT(*) FROM initiatives WHERE day=?", (now.date().isoformat(),)).fetchone()[0]
            last = db.execute("SELECT offered,response FROM initiatives ORDER BY id DESC LIMIT 1").fetchone()
            interval = max(prefs.interval_seconds, {"discreet": 3600, "normal": 1800, "chatty": 900}[prefs.level])
            if last and last["response"] in {"declined", "ignored"}:
                interval *= 2
            cap = min(prefs.daily_limit, {"discreet": 1, "normal": 3, "chatty": 6}[prefs.level])
            if daily >= cap or (last and stamp - last["offered"] < interval):
                return None
            events = db.execute("""SELECT e.* FROM context_events e JOIN sensors s ON e.sensor=s.name
                WHERE s.enabled=1 AND offered=0 AND resolved=0 AND expires>? ORDER BY created DESC LIMIT 100""", (stamp,)).fetchall()
            candidates = []
            for event in events:
                if resource_pressure and event["kind"] != "resource_pressure":
                    continue
                utility, _ = TEMPLATES[event["kind"]]
                urgency = 1 if event["kind"] in {"deadline", "resource_pressure"} else .3
                novelty = max(0, 1 - (stamp - event["created"]) / 86400)
                preference = max((record["confidence"] for record in preferences
                                  if record["topic"].casefold() in event["title"].casefold()), default=0)
                score = .5 * utility + .25 * urgency + .15 * novelty + .1 * preference
                if score >= .5:
                    candidates.append((score, event))
            if not candidates:
                return None
            score, event = max(candidates, key=lambda item: item[0])
            message = TEMPLATES[event["kind"]][1].format(title=event["title"])
            labels = {"own_tasks": "tarefas da Nyx", "research": "estudo autorizado", "resources": "recursos do computador"}
            reason = f"Contexto: {event['title']} · sensor autorizado: {labels.get(event['sensor'], event['sensor'])} · relevância {score:.2f}"
            cur = db.execute("INSERT INTO initiatives(event_id,offered,day,message,reason) VALUES (?,?,?,?,?)",
                             (event["id"], stamp, now.date().isoformat(), message, reason))
            db.execute("UPDATE context_events SET offered=1 WHERE id=?", (event["id"],))
            db.execute("DELETE FROM initiatives WHERE offered<?", (stamp - 90 * 86400,))
            self.last_offer_id = cur.lastrowid
            self.last_explanation = reason
            return message

    def respond(self, offer_id, response):
        if response not in {"accepted", "declined", "ignored"}:
            raise ValueError("Resposta à iniciativa inválida")
        with self.context.connect() as db:
            db.execute("UPDATE initiatives SET response=? WHERE id=?", (response, offer_id))

    def history(self):
        with self.context.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM initiatives ORDER BY id DESC LIMIT 100")]
