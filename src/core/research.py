"""Persistent idle research with bounded downloads and transactional cancellation."""

from __future__ import annotations

import hashlib
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit
from uuid import uuid4

from core.evolution import EvolutionLab

SOURCES = {
    "Ollama": "https://docs.ollama.com/faq",
    "Python": "https://docs.python.org/3/tutorial/",
    "Windows": "https://learn.microsoft.com/en-us/windows/apps/",
}
HOSTS = frozenset(urlsplit(url).hostname for url in SOURCES.values())


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username
            or parsed.password or parsed.port not in (None, 443) or len(url) > 2000):
        raise ValueError("Use HTTPS nas fontes permitidas: docs.ollama.com, docs.python.org ou learn.microsoft.com")
    return url


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []
        self.main_parts = []
        self.in_main = False

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.in_main = True
        if tag in {"script", "style", "noscript", "head", "nav", "header", "footer"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag == "main":
            self.in_main = False
        if tag in {"script", "style", "noscript", "head", "nav", "header", "footer"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            value = " ".join(data.split())
            self.parts.append(value)
            if self.in_main:
                self.main_parts.append(value)


def fetch_document(url: str) -> tuple[str, str]:
    """No cookies, credentials, JavaScript, subresources or proxy auto-discovery."""
    validate_url(url)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _Redirects())
    request = urllib.request.Request(url, headers={"User-Agent": "NyxResearch/0.1", "Accept": "text/html,text/plain"})
    deadline = time.monotonic() + 15
    with opener.open(request, timeout=6) as response:
        final_url = validate_url(response.geturl())
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "text/plain"}:
            raise ValueError("A fonte não retornou texto ou HTML")
        chunks = []
        size = 0
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError("Leitura ultrapassou o prazo")
            chunk = response.read(16384)
            if not chunk:
                break
            size += len(chunk)
            if size > 512 * 1024:
                raise ValueError("Página excede 512 KiB")
            chunks.append(chunk)
        text = b"".join(chunks).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    if content_type == "text/html":
        parser = _Text()
        parser.feed(text)
        text = "\n".join(parser.main_parts or parser.parts)
    text = text.strip()[:5800]
    if len(text) < 80:
        raise ValueError("Página sem conteúdo suficiente para estudo")
    return final_url, text


class ResearchQueue:
    DAILY_LIMIT = 4
    COOLDOWN = 15 * 60
    LEASE = 90

    def __init__(self, lab: EvolutionLab, clock=time.time):
        self.lab = lab
        self.clock = clock
        with lab.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS research_jobs (
                    id TEXT PRIMARY KEY, topic TEXT NOT NULL, url TEXT NOT NULL,
                    state TEXT NOT NULL, created REAL NOT NULL, started REAL,
                    token TEXT, note_id TEXT, detail TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS research_budget (
                    day TEXT PRIMARY KEY, attempts INTEGER NOT NULL, last_started REAL NOT NULL);
            """)

    def enqueue(self, topic: str, url: str) -> str:
        topic = self.lab._text(topic, 160)
        url = validate_url(self.lab._text(url, 2000))
        with self.lab.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            pending = db.execute("SELECT id FROM research_jobs WHERE url=? AND state IN ('queued','running')", (url,)).fetchone()
            if pending:
                return pending["id"]
            if db.execute("SELECT count(*) FROM research_jobs WHERE state IN ('queued','running')").fetchone()[0] >= 50:
                raise ValueError("Fila cheia: limite de 50 estudos pendentes")
            if db.execute("SELECT count(*) FROM research_jobs").fetchone()[0] >= 2000:
                raise ValueError("Histórico de estudos cheio; revise os registros")
            identity = uuid4().hex
            db.execute("INSERT INTO research_jobs(id,topic,url,state,created) VALUES (?,?,?,'queued',?)",
                       (identity, topic, url, self.clock()))
        return identity

    def seed_curiosity(self) -> None:
        """One initial curriculum derived from the app's actual capabilities."""
        with self.lab.connect() as db:
            exists = db.execute("SELECT 1 FROM research_jobs LIMIT 1").fetchone()
        if not exists:
            for topic, url in SOURCES.items():
                self.enqueue(f"Fundamentos de {topic}", url)

    def list_jobs(self) -> list[dict]:
        with self.lab.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,topic,url,state,note_id,detail FROM research_jobs ORDER BY created DESC LIMIT 50")]

    def cancel(self, identity: str) -> bool:
        with self.lab.connect() as db:
            return db.execute("UPDATE research_jobs SET state='cancelled',token=NULL,detail='Cancelado' "
                              "WHERE id=? AND state IN ('queued','running')", (identity,)).rowcount == 1

    def _claim(self) -> dict | None:
        now = self.clock()
        day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
        with self.lab.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # A stale worker loses its token, so it cannot later commit results.
            db.execute("UPDATE research_jobs SET state='queued',token=NULL,detail='Retomado após interrupção' "
                       "WHERE state='running' AND started<?", (now - self.LEASE,))
            if db.execute("SELECT 1 FROM research_jobs WHERE state='running'").fetchone():
                return None
            budget = db.execute("SELECT attempts FROM research_budget WHERE day=?", (day,)).fetchone()
            last = db.execute("SELECT max(last_started) FROM research_budget").fetchone()[0]
            if (budget and budget[0] >= self.DAILY_LIMIT) or (last is not None and now - last < self.COOLDOWN):
                return None
            row = db.execute("SELECT * FROM research_jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return None
            token = uuid4().hex
            db.execute("UPDATE research_jobs SET state='running',started=?,token=?,detail='Lendo fonte' WHERE id=?",
                       (now, token, row["id"]))
            db.execute("INSERT INTO research_budget VALUES (?,1,?) ON CONFLICT(day) DO UPDATE "
                       "SET attempts=attempts+1,last_started=excluded.last_started", (day, now))
            result = dict(row)
            result["token"] = token
            return result

    def run_one(self, fetcher=fetch_document, cancelled=lambda: False) -> dict | None:
        if cancelled():
            return None
        job = self._claim()
        if job is None:
            return None
        try:
            source, text = fetcher(job["url"])
            validate_url(source)
            text = self.lab._text(text, 6000)
            digest = hashlib.sha256((text + "\n" + source).encode()).hexdigest()
            with self.lab.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT state,token FROM research_jobs WHERE id=?", (job["id"],)).fetchone()
                if current["state"] != "running" or current["token"] != job["token"]:
                    return {"state": "cancelled", "topic": job["topic"]}
                if cancelled():
                    db.execute("UPDATE research_jobs SET state='queued',token=NULL,detail='Adiado para liberar recursos' WHERE id=?", (job["id"],))
                    return {"state": "deferred", "topic": job["topic"]}
                existing = db.execute("SELECT id FROM knowledge WHERE digest=?", (digest,)).fetchone()
                if existing:
                    identity = existing[0]
                else:
                    if db.execute("SELECT count(*) FROM knowledge").fetchone()[0] >= self.lab.MAX_ITEMS:
                        raise ValueError("Memória de pesquisa cheia")
                    identity = uuid4().hex
                    db.execute("INSERT INTO knowledge VALUES (?,?,?,?,?,?)",
                               (identity, job["topic"], text, source, digest, self.clock()))
                db.execute("UPDATE research_jobs SET state='completed',token=NULL,note_id=?,detail='Trecho coletado; ainda não verificado' WHERE id=?",
                           (identity, job["id"]))
            return {"state": "completed", "topic": job["topic"], "note_id": identity, "source": source}
        except Exception as exc:
            with self.lab.connect() as db:
                db.execute("UPDATE research_jobs SET state='failed',token=NULL,detail=? WHERE id=? AND token=?",
                           (str(exc)[:400], job["id"], job["token"]))
            return {"state": "failed", "topic": job["topic"], "error": str(exc)[:400]}
